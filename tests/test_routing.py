import copy
import io
import json
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import main as main_module
from app.bedrock import decide
from app.main import app
from app.routing import CASES, ROUTER_MODEL, Task, exclusion, load_catalog, workflow_payload
from app.routing_policy import candidate_pool, load_rankings, model_payload


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("BEDROCK_ENABLED", raising=False)
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


def body(**overrides):
    return {
        "task": {"text": CASES[0]["task"]},
        "provider": "decider",
        "mode": "replay",
        "stage": "workflow",
        "catalog_version": load_catalog()["version"],
        "ranking_version": load_rankings()["version"],
        **overrides,
    }


def pool(kind="customer_support", task=None, rankings=None, catalog=None):
    return candidate_pool(
        catalog or load_catalog(),
        rankings or load_rankings(),
        task or Task(text="test"),
        kind,
        exclusion,
    )


def test_auth_required():
    with TestClient(app) as client:
        assert client.get("/api/routing/catalog").status_code == 401
        assert client.post("/api/routing/decision", json=body()).status_code == 401
        assert client.post("/api/routing/execute", json={}).status_code == 401


def test_catalog_preserves_every_model_and_payment_comparator(client):
    data = client.get("/api/routing/catalog").json()
    assert len(data["cases"]) == 4
    assert data["models"] == load_catalog()["models"]
    assert data["router_model"] == "us.openai.gpt-6-sol"
    assert data["reasoning_effort"] == "low"
    assert "capabilities" not in data
    assert data["rankings"]["entries"]
    assert (
        client.get("/api/crypto/catalog").json()["bedrock_models"][0]["id"]
        == "us.openai.gpt-6.1-sol"
    )


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_replay_two_steps_have_no_inference_timing(client, case):
    payloads = []
    for provider in ("decider", "jev", "bedrock"):
        flow = client.post(
            "/api/routing/decision", json=body(task={"text": case["task"]}, provider=provider)
        ).json()
        assert flow["stage"] == "workflow" and flow["selected_model"] is None
        response = client.post(
            "/api/routing/decision",
            json=body(
                task={"text": case["task"]},
                provider=provider,
                stage="model",
                workflow=flow["choice"],
            ),
        )
        assert response.status_code == 200
        model = response.json()
        for result in [flow, model]:
            assert result["source"] == "rule_replay"
            assert result["timings"] is None and result["usage"] is None
            assert result["route_total_ms"] is None
        assert model["selected_model"]
        assert model["selection"]["selected_candidate_id"] == model["choice"]
        assert json.loads(flow["model_input"]["state"]) == {"request": case["task"]}
        assert json.loads(model["model_input"]["state"])["request"] == case["task"]
        payloads.append((flow["input_hash"], model["input_hash"]))
    assert len(set(payloads)) == 1


def test_old_manual_hints_stale_snapshots_and_forged_fields_rejected(client):
    for field in ("catalog_version", "ranking_version"):
        assert (
            client.post("/api/routing/decision", json=body(**{field: "stale"})).status_code == 409
        )
    for extra in ({"stage": "strategy"}, {"strategy": "quality"}, {"model_id": "https://attacker"}):
        assert client.post("/api/routing/decision", json=body(**extra)).status_code == 422
    for extra in ({"capability": "text"}, {"priority": "speed"}):
        assert (
            client.post(
                "/api/routing/decision", json=body(task={"text": "test", **extra})
            ).status_code
            == 422
        )
    assert client.post("/api/routing/decision", json=body(task={"text": "  "})).status_code == 422


def test_workflow_input_contains_no_preselected_answers_or_rankings():
    task = Task(text="Please explain my order status.")
    payload = workflow_payload(task)
    assert json.loads(payload["state"]) == {"request": task.text}
    assert workflow_payload(task.model_copy(update={"allow_cross_region": False})) == payload
    assert 2 <= len(payload["questions"]["action"]["criteria"]) <= 24


def test_workflow_must_be_selected_before_model(client):
    assert client.post("/api/routing/decision", json=body(stage="model")).status_code == 422
    assert client.post("/api/routing/decision", json=body(workflow="coding")).status_code == 422


def test_candidates_do_not_select_a_winner_or_enforce_price_quality_thresholds():
    data, ranks = load_catalog(), load_rankings()
    baseline = pool(catalog=data, rankings=ranks)
    assert "selected_model" not in baseline
    ids = [r["model"]["id"] for r in baseline["candidates"]]
    assert ids == sorted(ids)
    assert len(ids) > 5
    for model in data["models"]:
        model["name"] = "FASTEST CHEAPEST BEST Micro"
    for entry in ranks["entries"].values():
        if entry["source"] != "mteb":
            entry["metrics"]["quality"] = 0
            entry["metrics"]["input_price"] = None
    modified = pool(catalog=data, rankings=ranks)
    assert [r["model"]["id"] for r in modified["candidates"]] == ids
    assert all(
        "EMBEDDING" in r["model"]["output_modalities"] for r in pool("embedding")["candidates"]
    )
    regional = pool(task=Task(text="test", allow_cross_region=False))
    assert all(r["model"]["destination_regions"] == ["us-east-1"] for r in regional["candidates"])
    model = copy.deepcopy(data["models"][0])
    model["account_available"] = False
    assert exclusion(model, Task(text="x")) == "账户可用性未确认"


def test_missing_evidence_and_unmatched_models_are_explicit(client):
    ranks = load_rankings()
    ranks["entries"] = {}
    result = pool(rankings=ranks)
    assert not result["candidates"]
    assert len(result["excluded"]) == len(load_catalog()["models"])
    assert (
        client.post("/api/routing/decision", json=body(stage="model", workflow="video")).status_code
        == 422
    )


def test_second_real_model_output_wins_even_when_not_ranked_first(client, monkeypatch):
    from app import routing

    rows = pool()["candidates"]
    chosen = min(rows, key=lambda r: r["benchmark"]["metrics"]["quality"])
    calls = []

    async def infer(request, context, payload):
        calls.append(payload)
        return {
            "choice": "customer_support" if request.stage == "workflow" else chosen["candidate_id"],
            "model": "real-adapter-stub",
            "usage": {"input_tokens": 1},
            "timings": {"backend_total_ms": 10},
        }

    monkeypatch.setattr(routing, "infer", infer)
    flow = client.post("/api/routing/decision", json=body(mode="live")).json()
    response = client.post(
        "/api/routing/decision", json=body(mode="live", stage="model", workflow=flow["choice"])
    )
    assert response.status_code == 200
    result = response.json()
    assert result["selected_model"]["id"] == chosen["model"]["id"]
    assert result["source"] == "live" and len(calls) == 2
    state = json.loads(calls[1]["state"])
    assert state["request"] == body()["task"]["text"]
    assert state["selected_workflow"]["id"] == flow["choice"]
    assert len(calls[1]["questions"]["action"]["criteria"]) == len(rows)
    other = model_payload(Task(**body()["task"]), "coding", pool("coding"), load_rankings())
    assert other != calls[1]


def test_snapshot_mapping_does_not_alias_capacity_variants_or_mix_benchmarks():
    data, ranks = load_catalog(), load_rankings()
    assert set(ranks["entries"]) <= {m["id"] for m in data["models"]}
    assert {r["source"] for r in ranks["entries"].values()} == {ranks["profile"]["id"], "mteb"}
    mteb = [r for r in ranks["entries"].values() if r["source"] == "mteb"]
    assert len({r["dataset_revision"] for r in mteb}) == 1
    for row in mteb:
        assert row["metrics"]["retrieval"] == pytest.approx(sum(row["subsets"].values()) / 2 * 100)


def test_gpt6_uses_low_effort_and_routing_role():
    payload = workflow_payload(Task(text="Order status?"))
    runtime = MagicMock()
    runtime.converse.return_value = {
        "output": {"message": {"content": [{"text": '{"choice":"customer_support"}'}]}},
        "stopReason": "end_turn",
        "usage": {"inputTokens": 500, "outputTokens": 8},
    }
    assert (
        decide(runtime, ROUTER_MODEL, payload, purpose="model routing")["choice"]
        == "customer_support"
    )
    args = runtime.converse.call_args.kwargs
    assert args["modelId"] == ROUTER_MODEL
    assert args["additionalModelRequestFields"] == {"reasoning": {"effort": "low"}}
    assert json.loads(args["messages"][0]["content"][0]["text"]) == payload
    with pytest.raises(ValueError):
        decide(runtime, ROUTER_MODEL, payload)


def test_failed_router_never_replaced_with_replay(client, monkeypatch):
    async def failed(*args, **kwargs):
        raise HTTPException(504, "explicit failed model")

    monkeypatch.setattr(main_module, "live_decision", failed)
    response = client.post("/api/routing/decision", json=body(mode="live"))
    assert response.status_code == 504 and "choice" not in response.json()


def test_invalid_live_label_is_not_repaired(client, monkeypatch):
    from app import routing

    async def invalid(*args):
        return {"choice": "made_up_task"}

    monkeypatch.setattr(routing, "infer", invalid)
    assert client.post("/api/routing/decision", json=body(mode="live")).status_code == 502


def execution_body(kind):
    return {
        "task": {"text": "USDC 未到账"},
        "workflow": kind,
        "model_id": pool(kind)["candidates"][0]["model"]["id"],
        "catalog_version": load_catalog()["version"],
        "ranking_version": load_rankings()["version"],
    }


def test_target_execution_rechecks_candidate_membership_and_uses_mapped_effort(client):
    app.state.bedrock = MagicMock()
    app.state.bedrock.converse.return_value = {
        "output": {"message": {"content": [{"text": "Actual task response"}]}},
        "stopReason": "max_tokens",
        "usage": {"inputTokens": 12, "outputTokens": 4096},
    }
    payload = execution_body("customer_support")
    response = client.post("/api/routing/execute", json=payload)
    assert response.status_code == 200
    assert (
        response.json()["text"] == "Actual task response" and response.json()["complete"] is False
    )
    args = app.state.bedrock.converse.call_args.kwargs
    assert args["inferenceConfig"]["maxTokens"] == 4096
    assert (
        args["additionalModelRequestFields"]
        == pool()["candidates"][0]["benchmark"]["request_fields"]
    )
    payload["model_id"] = "https://attacker.example"
    assert client.post("/api/routing/execute", json=payload).status_code == 422


def test_embedding_execution_returns_real_dimensions(client):
    app.state.bedrock = MagicMock()
    stream = io.BytesIO(json.dumps({"embeddings": [[0.1] * 32]}).encode())
    app.state.bedrock.invoke_model.return_value = {"body": stream}
    response = client.post("/api/routing/execute", json=execution_body("embedding"))
    assert response.status_code == 200
    result = response.json()
    assert result["dimensions"] == 32 and len(result["vector_preview"]) == 12
    assert stream.closed and result["complete"]


def test_reasoning_only_budget_exhaustion_is_not_a_completed_answer(client):
    app.state.bedrock = MagicMock()
    app.state.bedrock.converse.return_value = {
        "output": {
            "message": {"content": [{"reasoningContent": {"reasoningText": {"text": "internal"}}}]}
        },
        "stopReason": "max_tokens",
        "usage": {"inputTokens": 97, "outputTokens": 4096},
    }
    response = client.post("/api/routing/execute", json=execution_body("coding"))
    assert response.status_code == 200
    result = response.json()
    assert not result["complete"] and not result["has_final_text"]
    assert result["stop_reason"] == "max_tokens"
    assert result["usage"]["outputTokens"] == 4096
    assert "4096" in result["text"]
    assert "internal" not in result["text"]


def test_aa_import_uses_official_api_and_preserves_missing_metrics(tmp_path, monkeypatch):
    from scripts import refresh_routing_rankings as refresh

    key = tmp_path / "key.txt"
    key.write_text("test-secret-only")
    calls = []

    def fetch(url, headers):
        calls.append((url, headers))
        return json.dumps(
            {
                "data": [
                    {
                        "id": "stable-test-uuid",
                        "slug": "gpt-6-sol-low",
                        "name": "GPT-6 Sol (Low)",
                        "evaluations": {"artificial_analysis_intelligence_index": 34.0},
                        "pricing": {"price_1m_input_tokens": 2, "price_1m_output_tokens": 10},
                        "median_output_tokens_per_second": 100,
                    }
                ]
            }
        ).encode()

    monkeypatch.setattr(refresh, "fetch", fetch)
    rows, profile = refresh.artificial_analysis(
        {"artificial_analysis": {"openai.gpt-6-sol": "gpt-6-sol-low"}}, key, []
    )
    row = rows["openai.gpt-6-sol"]
    assert calls == [
        ("https://artificialanalysis.ai/api/v2/data/llms/models", {"x-api-key": "test-secret-only"})
    ]
    assert row["metrics"]["coding"] is None
    assert row["metrics"]["ttft_seconds"] is None
    assert row["request_fields"] == {"reasoning": {"effort": "low"}}
    assert row["source_id"] == "stable-test-uuid"
    assert "test-secret" not in json.dumps(rows)
    assert profile["id"] == "artificial_analysis"
    with pytest.raises(ValueError):
        refresh.number(float("nan"))
    with pytest.raises(ValueError):
        refresh.artificial_analysis({}, None, [])
