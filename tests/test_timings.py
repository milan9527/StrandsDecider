import asyncio
import copy
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main as api_module
from app.examples import EXAMPLES
from app.main import app


@pytest.fixture
def client():
    with TestClient(app, headers={"X-Decider-Client": "web"}) as client:
        assert (
            client.post(
                "/api/auth/login",
                json={
                    "username": "tester",
                    "password": "test-password-with-entropy",
                },
            ).status_code
            == 200
        )
        yield client


def payload():
    example = EXAMPLES[0]
    return {
        "mode": "live",
        "measure_decisions": True,
        "state": example["state"],
        "questions": copy.deepcopy(example["questions"]),
    }


def reply(questions, *, model="timed-model", metrics=True):
    data = {
        "model": model,
        "answers": {key: copy.deepcopy(EXAMPLES[0]["answers"][key]) for key in questions},
    }
    if metrics:
        data.update(latency_ms=20, usage={"input_tokens": 100, "output_tokens": len(questions)})
    return httpx.Response(200, json=data, request=httpx.Request("POST", "http://model"))


def test_individual_timings_measure_each_request_and_include_queue_in_total(client, monkeypatch):
    clock = [10.0]
    durations = dict(zip(EXAMPLES[0]["questions"], [0.1, 0.2, 0.4], strict=True))
    calls = []

    @asynccontextmanager
    async def queued_slot(lock):
        clock[0] += 0.3
        yield

    async def model(*args, **kwargs):
        body = kwargs["json"]
        assert body["state"] == EXAMPLES[0]["state"]
        assert len(body["questions"]) == 1
        key = next(iter(body["questions"]))
        calls.append(key)
        clock[0] += durations[key]
        return reply(body["questions"])

    monkeypatch.setattr(api_module, "perf_counter", lambda: clock[0])
    monkeypatch.setattr(api_module, "decision_slot", queued_slot)
    monkeypatch.setattr(app.state.client, "post", model)
    response = client.post("/api/decide", json=payload())
    assert response.status_code == 200
    data = response.json()
    assert calls == list(EXAMPLES[0]["questions"])
    assert data["answers"] == EXAMPLES[0]["answers"]
    assert data["latency_ms"] == 60
    assert data["usage"] == {"input_tokens": 300, "output_tokens": 3}
    assert data["timings"] == {
        "execution": "individual",
        "decisions_ms": {key: elapsed * 1000 for key, elapsed in durations.items()},
        "queue_ms": 300.0,
        "processing_ms": 700.0,
        "backend_total_ms": 1000.0,
    }
    assert data["round_trip_ms"] == 700


def test_default_batch_mode_keeps_one_call_without_apportioning_time(client, monkeypatch):
    mock = AsyncMock(return_value=reply(EXAMPLES[0]["questions"]))
    monkeypatch.setattr(app.state.client, "post", mock)
    body = payload()
    body.pop("measure_decisions")
    response = client.post("/api/decide", json=body)
    assert response.status_code == 200
    assert mock.call_count == 1
    assert response.json()["timings"]["execution"] == "batch"
    assert response.json()["timings"]["decisions_ms"] is None


def test_failed_question_does_not_return_partial_answers_or_continue(client, monkeypatch):
    keys = list(EXAMPLES[0]["questions"])
    mock = AsyncMock(
        side_effect=[
            reply({keys[0]: EXAMPLES[0]["questions"][keys[0]]}),
            httpx.Response(500, request=httpx.Request("POST", "http://model")),
        ]
    )
    monkeypatch.setattr(app.state.client, "post", mock)
    response = client.post("/api/decide", json=payload())
    assert response.status_code == 503 and "answers" not in response.json()
    assert mock.call_count == 2
    assert not app.state.lock.locked()


def test_entire_run_shares_one_timeout_budget(client, monkeypatch):
    calls = []

    async def slow_model(*args, **kwargs):
        calls.append(kwargs["json"])
        await asyncio.sleep(0.04)
        return reply(kwargs["json"]["questions"])

    monkeypatch.setattr(app.state.client, "post", slow_model)
    monkeypatch.setattr(app.state, "model_timeout", 0.07)
    response = client.post("/api/decide", json=payload())
    assert response.status_code == 504
    assert "总时间限制" in response.json()["detail"]
    assert len(calls) < 3
    assert "answers" not in response.json()
    assert not app.state.lock.locked()


def test_missing_upstream_metrics_are_not_invented(client, monkeypatch):
    async def model(*args, **kwargs):
        return reply(kwargs["json"]["questions"], metrics=False)

    monkeypatch.setattr(app.state.client, "post", model)
    response = client.post("/api/decide", json=payload())
    assert response.status_code == 200
    data = response.json()
    assert data["latency_ms"] is None and data["usage"] is None
    assert set(data["timings"]["decisions_ms"]) == set(EXAMPLES[0]["questions"])


def test_changed_model_identity_fails_closed(client, monkeypatch):
    keys = list(EXAMPLES[0]["questions"])
    mock = AsyncMock(
        side_effect=[
            reply({keys[0]: {}}, model="first-model"),
            reply({keys[1]: {}}, model="another-model"),
        ]
    )
    monkeypatch.setattr(app.state.client, "post", mock)
    response = client.post("/api/decide", json=payload())
    assert response.status_code == 502 and "answers" not in response.json()
    assert mock.call_count == 2


@pytest.mark.parametrize("endpoint", ["decide", "guard"])
def test_examples_never_claim_inference_timings(client, endpoint):
    body = (
        {**payload(), "mode": "example", "example_id": EXAMPLES[0]["id"]}
        if endpoint == "decide"
        else {"message": "What's the weather?", "location": "Seattle", "measure_decisions": True}
    )
    response = client.post(f"/api/{endpoint}", json=body)
    assert response.status_code == 200
    assert response.json()["timings"] == {"execution": "example", "decisions_ms": None}
    assert response.json()["latency_ms"] is None


def test_guard_measures_both_checks(client, monkeypatch):
    async def model(*args, **kwargs):
        key = next(iter(kwargs["json"]["questions"]))
        return httpx.Response(
            200,
            request=httpx.Request("POST", "http://model"),
            json={
                "model": "timed-model",
                "latency_ms": 12,
                "answers": {
                    key: {"type": "noul", "noul": 0.95 if key == "args_grounded" else 0.03}
                },
            },
        )

    monkeypatch.setattr(app.state.client, "post", model)
    response = client.post(
        "/api/guard",
        json={
            "mode": "live",
            "measure_decisions": True,
            "message": "What's the weather in Seattle?",
            "location": "Seattle",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert set(data["timings"]["decisions_ms"]) == {"args_grounded", "premature"}
    assert data["policy"]["action"] == "Proceed"
    assert data["tool_executed"] is False


def test_concurrent_runs_keep_their_questions_together(monkeypatch):
    async def scenario():
        calls = []
        active = peak = 0

        async def model(*args, **kwargs):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            body = kwargs["json"]
            calls.append(body["state"])
            await asyncio.sleep(0.01)
            active -= 1
            return reply(body["questions"])

        async with app.router.lifespan_context(app):
            monkeypatch.setattr(app.state.client, "post", model)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
                headers={"X-Decider-Client": "web"},
            ) as client:
                assert (
                    await client.post(
                        "/api/auth/login",
                        json={
                            "username": "tester",
                            "password": "test-password-with-entropy",
                        },
                    )
                ).status_code == 200
                responses = await asyncio.gather(
                    client.post("/api/decide", json={**payload(), "state": "run-a"}),
                    client.post("/api/decide", json={**payload(), "state": "run-b"}),
                )
        assert all(r.status_code == 200 for r in responses)
        assert peak == 1
        assert calls in (["run-a"] * 3 + ["run-b"] * 3, ["run-b"] * 3 + ["run-a"] * 3)

    asyncio.run(scenario())
