import asyncio
import copy
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.examples import EXAMPLES
from app.main import app
from app.policy import review


@pytest.fixture
def client():
    with TestClient(app) as client:
        client.headers["X-Decider-Client"] = "web"
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


def payload(example=EXAMPLES[0], mode="example"):
    return {
        "mode": mode,
        "example_id": example["id"],
        "state": example["state"],
        "questions": copy.deepcopy(example["questions"]),
    }


def upstream_reply(example=EXAMPLES[0]):
    return {
        "model": "strands-decider-2B-hobson-v19",
        "answers": copy.deepcopy(example["answers"]),
        "usage": {"input_tokens": 100, "output_tokens": len(example["answers"])},
        "latency_ms": 123.45,
    }


def mock_upstream(monkeypatch, *, data=None, status=200, error=None):
    mock = AsyncMock(
        side_effect=error,
        return_value=httpx.Response(
            status, json=data, request=httpx.Request("POST", "http://decider/v1/systemone")
        ),
    )
    monkeypatch.setattr(app.state.client, "post", mock)
    return mock


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda x: x["id"])
def test_examples_are_explicit_fixtures_without_fake_timings(client, example):
    response = client.post("/api/decide", json=payload(example))
    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "example"
    assert data["model"] == "illustrative-fixture"
    assert data["latency_ms"] is None and data["usage"] is None
    assert set(data["answers"]) == set(example["questions"])


@pytest.mark.parametrize("field", ["state", "questions", "example_id"])
def test_edited_examples_never_get_canned_predictions(client, field):
    body = payload()
    if field == "questions":
        body[field]["department"]["criteria"]["billing"] = "Different meaning"
    else:
        body[field] = "custom input"
    assert client.post("/api/decide", json=body).status_code == 409


def test_live_preserves_official_types_and_confidence(client, monkeypatch):
    mock = mock_upstream(monkeypatch, data=upstream_reply())
    body = payload(mode="live")
    response = client.post("/api/decide", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "live"
    assert data["answers"] == EXAMPLES[0]["answers"]
    assert data["latency_ms"] == 123.45
    assert data["round_trip_ms"] >= 0
    assert mock.call_args.kwargs["json"] == {
        "state": body["state"],
        "questions": body["questions"],
    }


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d["answers"].pop("department"),
        lambda d: d["answers"]["is_urgent"].update(noul=1.3),
        lambda d: d["answers"]["department"].update(choice="invented"),
        lambda d: d["answers"]["department"].update(confidence="high"),
        lambda d: d["answers"]["department"]["probabilities"].update(billing=0),
        lambda d: d["answers"]["frustration"].update(score=99),
        lambda d: d["answers"]["frustration"].update(legend={"0": "Other scale"}),
    ],
)
def test_invalid_upstream_results_fail_closed(client, monkeypatch, mutation):
    data = upstream_reply()
    mutation(data)
    mock_upstream(monkeypatch, data=data)
    assert client.post("/api/decide", json=payload(mode="live")).status_code == 502


@pytest.mark.parametrize(
    ("error", "status"),
    [(httpx.ConnectError("offline"), 503), (httpx.ReadTimeout("too slow"), 504)],
)
def test_real_failures_never_fall_back_to_fixtures(client, monkeypatch, error, status):
    mock_upstream(monkeypatch, error=error)
    response = client.post("/api/decide", json=payload(mode="live"))
    assert response.status_code == status
    assert "answers" not in response.json()


def test_upstream_window_rejection_is_reported(client, monkeypatch):
    mock_upstream(monkeypatch, status=422, data={"detail": "window exceeded"})
    assert client.post("/api/decide", json=payload(mode="live")).status_code == 422


@pytest.mark.parametrize(
    "question",
    [
        {"type": "choice", "instructions": "Choose", "criteria": {"only": None}},
        {"type": "score", "instructions": "Rate", "criteria": ["Low", "Low"]},
        {"type": "noul", "instructions": "Yes?", "criteria": {"unknown": "Something"}},
        {"type": "noul", "instructions": "  "},
    ],
)
def test_bad_question_schemas_rejected(client, question):
    body = payload()
    body["questions"] = {"bad": question}
    assert client.post("/api/decide", json=body).status_code == 422


@pytest.mark.parametrize(
    ("message", "action"),
    [("What's the weather?", "Guide"), ("What's the weather in Seattle?", "Proceed")],
)
def test_guard_example_branches(client, message, action):
    response = client.post(
        "/api/guard", json={"message": message, "location": "Seattle", "threshold": 0.45}
    )
    assert response.status_code == 200
    assert response.json()["policy"]["action"] == action
    assert response.json()["tool_executed"] is False


@pytest.mark.parametrize(
    ("grounded", "premature", "action"),
    [(0.449, 0, "Guide"), (0.45, 0.449, "Proceed"), (1, 0.45, "Guide")],
)
def test_guard_policy_boundary(grounded, premature, action):
    answers = {"args_grounded": {"noul": grounded}, "premature": {"noul": premature}}
    assert review(answers, 0.45)["action"] == action


def test_guard_rejects_custom_fixture_and_out_of_range_threshold(client):
    assert (
        client.post(
            "/api/guard", json={"message": "Weather in Paris?", "location": "Paris"}
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/guard",
            json={"message": "What's the weather?", "location": "Seattle", "threshold": 1},
        ).status_code
        == 422
    )


def test_live_requests_are_serialized(monkeypatch):
    async def scenario():
        active = peak = 0

        async def upstream(*args, **kwargs):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.02)
            active -= 1
            return httpx.Response(
                200, json=upstream_reply(), request=httpx.Request("POST", "http://decider")
            )

        async with app.router.lifespan_context(app):
            monkeypatch.setattr(app.state.client, "post", upstream)
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
                    *[client.post("/api/decide", json=payload(mode="live")) for _ in range(3)]
                )
        assert all(r.status_code == 200 for r in responses)
        assert peak == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("connected", [True, False])
def test_readiness_only_allows_traffic_after_model_is_ready(client, monkeypatch, connected):
    data = {"status": "ok", "model": "strands-decider-2B-hobson-v19"} if connected else {}
    monkeypatch.setattr(
        app.state.client,
        "get",
        AsyncMock(
            return_value=httpx.Response(
                200, json=data, request=httpx.Request("GET", "http://decider/health")
            )
        ),
    )
    assert client.get("/api/live").status_code == 200
    response = client.get("/api/ready")
    assert response.status_code == (200 if connected else 503)
