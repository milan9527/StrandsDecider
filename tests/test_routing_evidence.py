import copy
import json
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import routing
from app.main import app
from app.routing import Task, exclusion, load_catalog
from app.routing_evidence import EVIDENCE_VERSION, optimized_payload
from app.routing_policy import candidate_pool, load_rankings, model_payload


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("BEDROCK_ENABLED", raising=False)
    with TestClient(app, headers={"X-Decider-Client": "web"}) as c:
        assert (
            c.post(
                "/api/auth/login",
                json={
                    "username": "tester",
                    "password": "test-password-with-entropy",
                },
            ).status_code
            == 200
        )
        yield c


def body(**overrides):
    return {
        "task": {"text": "将中英文工单转换为检索向量"},
        "stage": "model",
        "workflow": "embedding",
        "provider": "decider",
        "mode": "live",
        "strategy": "optimized",
        "evidence_version": EVIDENCE_VERSION,
        "catalog_version": load_catalog()["version"],
        "ranking_version": load_rankings()["version"],
        **overrides,
    }


def pool(workflow):
    return candidate_pool(load_catalog(), load_rankings(), Task(text="任务"), workflow, exclusion)


@pytest.mark.parametrize("workflow", ["customer_support", "coding", "reasoning", "embedding"])
def test_same_candidates_same_order_no_program_recommendation(workflow):
    task, ranks, candidates = Task(text="只有任务，不带优先级"), load_rankings(), pool(workflow)
    original = model_payload(task, workflow, candidates, ranks)
    optimized = optimized_payload(task, workflow, candidates, ranks)
    assert list(original["questions"]["action"]["criteria"]) == list(
        optimized["questions"]["action"]["criteria"]
    )
    assert json.loads(optimized["state"])["request"] == task.text
    assert json.loads(optimized["state"])["execution_limits"]["text_output_token_cap"] == 4096
    assert original != optimized
    for field in ("selected_candidate_id", "winner", "quality_band", "eligible", "floors"):
        assert field not in json.dumps(optimized)


def test_language_evidence_is_split_without_a_preselected_answer():
    candidates = pool("embedding")
    payload = optimized_payload(Task(text="中英文索引"), "embedding", candidates, load_rankings())
    descriptions = payload["questions"]["action"]["criteria"]
    english = next(
        r for r in candidates["candidates"] if r["model"]["id"] == "cohere.embed-english-v3"
    )
    assert "English retrieval 57.124/100" in descriptions[english["candidate_id"]]
    assert "Chinese retrieval 4.178/100" in descriptions[english["candidate_id"]]
    assert len(descriptions) == 3  # Weak candidates remain selectable.


@pytest.mark.parametrize("provider", ["decider", "jev", "bedrock"])
@pytest.mark.parametrize("strategy", ["original", "optimized"])
def test_each_model_really_selects_and_even_weak_choice_is_preserved(
    client, monkeypatch, provider, strategy
):
    calls = []
    english = next(
        r for r in pool("embedding")["candidates"] if r["model"]["id"] == "cohere.embed-english-v3"
    )

    async def infer(request_body, request, payload):
        calls.append((request_body.provider, payload))
        return {
            "choice": english["candidate_id"],
            "model": "real-provider-mock",
            "timings": {"backend_total_ms": 55},
            "usage": {"input_tokens": 200},
        }

    monkeypatch.setattr(routing, "infer", infer)
    response = client.post("/api/routing/decision", json=body(provider=provider, strategy=strategy))
    assert response.status_code == 200
    result = response.json()
    assert len(calls) == 1 and calls[0][0] == provider
    assert result["source"] == "live" and result["strategy"] == strategy
    assert result["selected_model"]["id"] == "cohere.embed-english-v3"
    assert result["model_input"] == calls[0][1] and result["usage"] is not None
    assert "task_ranking" not in result


def test_missing_evidence_does_not_remove_candidate_or_invent_zero():
    candidates = copy.deepcopy(pool("coding"))
    row = candidates["candidates"][0]
    row["benchmark"]["category_scores"] = {}
    row["benchmark"]["metrics"]["input_price"] = None
    payload = optimized_payload(Task(text="代码"), "coding", candidates, load_rankings())
    text = payload["questions"]["action"]["criteria"][row["candidate_id"]]
    assert "Coding unknown" in text and "0/100" not in text
    assert "Reference input price" not in text
    assert len(payload["questions"]["action"]["criteria"]) == len(candidates["candidates"])


def test_even_single_live_candidate_calls_model(client, monkeypatch):
    candidates = pool("embedding")
    candidates["candidates"] = candidates["candidates"][:1]
    monkeypatch.setattr(routing, "candidate_pool", lambda *args: candidates)
    called = []

    async def infer(*args):
        called.append(True)
        return {
            "choice": candidates["candidates"][0]["candidate_id"],
            "timings": {"backend_total_ms": 10},
        }

    monkeypatch.setattr(routing, "infer", infer)
    response = client.post("/api/routing/decision", json=body())
    assert response.json()["source"] == "live" and called == [True]


def test_failure_is_not_replaced_by_program_choice(client, monkeypatch):
    async def fail(*args):
        raise HTTPException(504, "model timeout")

    monkeypatch.setattr(routing, "infer", fail)
    response = client.post("/api/routing/decision", json=body())
    assert response.status_code == 504 and "choice" not in response.json()


def test_removed_program_endpoint_and_stale_evidence(client):
    assert client.post("/api/routing/rank", json={}).status_code == 410
    assert (
        client.post(
            "/api/routing/decision", json=body(evidence_version="task-ranking-v1")
        ).status_code
        == 409
    )
    assert (
        client.post("/api/routing/decision", json={**body(), "priority": "cheap"}).status_code
        == 422
    )


def test_execution_allows_models_choice_without_rank_override(client):
    # A low-code-score model is still allowed if the model chose it.
    model = pool("coding")["candidates"][0]["model"]
    app.state.bedrock = MagicMock()
    app.state.bedrock.converse.return_value = {
        "output": {"message": {"content": [{"text": "actual output"}]}},
        "stopReason": "end_turn",
        "usage": {"inputTokens": 30, "outputTokens": 40},
    }
    payload = {
        k: v for k, v in body(workflow="coding").items() if k not in ("stage", "provider", "mode")
    }
    payload["model_id"] = model["id"]
    response = client.post("/api/routing/execute", json=payload)
    assert response.status_code == 200 and response.json()["model_id"] == model["id"]
    assert app.state.bedrock.converse.call_args.kwargs["inferenceConfig"] == {"maxTokens": 4096}
    payload["model_id"] = "not-a-candidate"
    assert client.post("/api/routing/execute", json=payload).status_code == 422
