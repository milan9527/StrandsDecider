import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.ac_control import (
    ACRuns, CASES, GPT_MODEL, RunRequest, expected_for, gpt_decide, payload_for, score, selections,
)
from app.main import app
from deployment.jev_proxy import valid_request


def test_frozen_inputs_all_78_cases_and_both_orders():
    originals = json.loads(Path(
        "validation/ac_control/runs/2026-11-01-liquid-lora-v1/historical-cases.json"
    ).read_text())
    for case in originals:
        request = payload_for(case["case_id"], case["order"])
        assert request == case["payload"]
        assert valid_request({**request, "model": "jev-latest"})
        assert set(request) == {"state", "questions"}
    assert len(CASES) == 78


def test_omit_zero_missing_wrong_value_and_unanswered_are_distinct():
    expected = {"power": "omit", "light": "0", "temp": "23", "fan": "omit"}
    result = score(expected, {"power": "0", "light": "omit", "temp": "24"})
    assert result["fields"] == {
        "power": "extra", "light": "missing", "temp": "wrong_value", "fan": "unanswered",
    }
    assert not result["correct"] and result["matched"] == 0


def test_gpt_uses_exact_benchmark_transport_and_invalid_outputs_fail():
    payload = payload_for("M01")
    reference = expected_for("M01")
    client = MagicMock()
    client.converse.return_value = {
        "stopReason": "end_turn",
        "output": {"message": {"content": [{"text": json.dumps({"answers": reference})}]}},
    }
    assert selections(gpt_decide(client, payload), payload) == reference
    call = client.converse.call_args.kwargs
    assert call["modelId"] == GPT_MODEL
    assert call["additionalModelRequestFields"] == {"reasoning": {"effort": "low"}}
    assert call["inferenceConfig"] == {"maxTokens": 8192}
    assert json.loads(call["messages"][0]["content"][0]["text"]) == payload
    client.converse.return_value["stopReason"] = "max_tokens"
    with pytest.raises(ValueError):
        gpt_decide(client, payload)
    for bad in ({"answers": {}}, {"answers": {**reference, "t_power": "unknown"}}):
        with pytest.raises(ValueError):
            selections(bad, payload)


def test_three_layouts_are_serial_same_inputs_and_owner_isolation():
    async def check():
        runs = ACRuns()
        request = SimpleNamespace(state=SimpleNamespace(user={"username": "alice"}))
        in_flight, peak, calls = 0, 0, []

        async def infer(_, provider, payload):
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            calls.append((provider, copy.deepcopy(payload)))
            await asyncio.sleep(0.001)
            in_flight -= 1
            return {"model": provider, "answers": {
                k: {"choice": expected_for("M01")[k]} for k in payload["questions"]}}

        runs.infer = infer
        job = runs.start(request, RunRequest(case_ids=["M01"], mode="all", field="t_temp"))
        with pytest.raises(HTTPException) as conflict:
            runs.start(request, RunRequest(case_ids=["S01"]))
        assert conflict.value.status_code == 409
        with pytest.raises(HTTPException) as denied:
            runs.owned(job["id"], "bob")
        assert denied.value.status_code == 404
        await asyncio.gather(*list(runs.tasks))
        result = runs.public(runs.owned(job["id"], "alice"))
        assert peak == 1 and len(calls) == 96
        assert result["completed"] == 9
        assert all(r["score"]["correct"] and r["status"] == "done" for r in result["records"])
        assert [len(r["calls"]) for r in result["records"]] == [1]*3 + [30]*3 + [1]*3
        assert all(p["state"] == payload_for("M01")["state"] for _, p in calls)
        assert all(r["elapsed_ms"] >= sum(c["elapsed_ms"] for c in r["calls"])
                   for r in result["records"])
    asyncio.run(check())


def test_interface_failure_keeps_missing_fields_and_continues_other_models():
    async def check():
        runs = ACRuns()
        request = SimpleNamespace(state=SimpleNamespace(user={"username": "alice"}))
        counts = {}
        async def infer(_, provider, payload):
            counts[provider] = counts.get(provider, 0) + 1
            if provider == "jev":
                raise ValueError("synthetic interface error")
            return {"model": provider, "answers": {k: expected_for("S01")[k] for k in payload["questions"]}}
        runs.infer = infer
        started = runs.start(request, RunRequest(case_ids=["S01"], mode="serial30"))
        await asyncio.gather(*list(runs.tasks))
        records = runs.jobs[started["id"]]["records"]
        assert counts == {"liquid_lora": 30, "jev": 1, "gpt": 30}
        assert records[1]["status"] == "error"
        assert set(records[1]["score"]["fields"].values()) == {"unanswered"}
        assert records[0]["score"]["correct"] and records[2]["score"]["correct"]
    asyncio.run(check())


def test_cancel_waits_for_current_request_and_never_submits_the_next():
    async def check():
        runs = ACRuns()
        request = SimpleNamespace(state=SimpleNamespace(user={"username": "alice"}))
        entered, release = asyncio.Event(), asyncio.Event()
        async def infer(_, provider, payload):
            entered.set()
            await release.wait()
            return {"model": provider, "answers": {k: "omit" for k in payload["questions"]}}
        runs.infer = infer
        created = runs.start(request, RunRequest(case_ids=["M01"], mode="serial30"))
        await entered.wait()
        job = runs.jobs[created["id"]]
        job["cancel_requested"] = True
        release.set()
        await asyncio.gather(*list(runs.tasks))
        assert job["status"] == "cancelled"
        assert sum(len(r["calls"]) for r in job["records"]) == 1
        assert all(r["status"] == "cancelled" for r in job["records"])
    asyncio.run(check())


def test_authenticated_routes_reject_invalid_fields_and_case_ids():
    with TestClient(app) as client:
        assert client.get("/api/ac-control/catalog").status_code == 401
        client.headers["X-Decider-Client"] = "web"
        assert client.post("/api/auth/login", json={
            "username": "tester", "password": "test-password-with-entropy"}).status_code == 200
        assert len(client.get("/api/ac-control/catalog").json()["cases"]) == 78
        for body in ({"case_ids": ["unknown"]}, {"case_ids": ["S01", "S01"]},
                     {"case_ids": ["S01"], "field": "unknown"}, {"case_ids": ["S01"], "mode": "invalid"}):
            assert client.post("/api/ac-control/runs", json=body).status_code == 422


def test_lora_bridge_authenticates_and_pins_checkpoint(monkeypatch):
    from deployment.open_models import ac_lora_gateway as bridge
    monkeypatch.setenv("AC_LORA_TOKEN", "test-only-gateway-key")
    wrong_adapter = False
    paths = []
    async def upstream(request):
        paths.append(request.url.path)
        if request.url.path == "/health":
            return httpx.Response(200, json={
                "ready": True, "selected": {"sha256": "wrong" if wrong_adapter else bridge.ADAPTER}})
        assert request.url.path == "/lora"
        return httpx.Response(200, json={"answers": expected_for("M09")})
    with TestClient(bridge.app) as client:
        bridge.app.state.client = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
        assert client.get("/health").status_code == 401
        client.headers["Authorization"] = "Bearer test-only-gateway-key"
        response = client.post("/v1/systemone", json=payload_for("M09"))
        assert response.status_code == 200
        assert response.json()["adapter_sha256"] == bridge.ADAPTER
        assert paths == ["/health", "/lora"]
        wrong_adapter = True
        assert client.post("/v1/systemone", json=payload_for("M09")).status_code == 503
        assert paths == ["/health", "/lora", "/health"]
        assert client.post("/v1/systemone", json={"state": "x", "questions": {}}).status_code == 422
