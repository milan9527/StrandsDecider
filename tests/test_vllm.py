import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.main import app, live_decision
from deployment.infrastructure import template

MODEL = "strands-decider-2B-hobson-v19-vllm"
PAYLOAD = {
    "state": "The transfer is confirmed.",
    "questions": {"confirmed": {"type": "noul", "instructions": "Is it confirmed?"}},
}
REPLY = {
    "model": MODEL,
    "answers": {"confirmed": {"type": "noul", "noul": 0.9}},
    "usage": {"input_tokens": 20, "output_tokens": 1},
    "latency_ms": 10,
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("GPU_PROVIDER", "vllm")
    monkeypatch.setenv("GPU_STATE_TABLE", "original-gpu-must-not-be-used")
    monkeypatch.setenv("STRANDS_DECIDER_URL", "http://vllm.internal:8100")
    monkeypatch.setenv("DECIDER_API_KEY", "test-server-side-secret")
    monkeypatch.setenv("VLLM_INSTANCE_ID", "i-vllm")
    with TestClient(app) as client:
        client.headers["X-Decider-Client"] = "web"
        assert client.post("/api/auth/login", json={
            "username": "tester", "password": "test-password-with-entropy",
        }).status_code == 200
        yield client


def response(status=200, data=REPLY):
    return httpx.Response(
        status, json=data,
        request=httpx.Request("POST", "http://vllm.internal:8100/v1/systemone"),
    )


def test_vllm_uses_private_endpoint_and_server_only_key(client, monkeypatch):
    mock = AsyncMock(return_value=response())
    monkeypatch.setattr(app.state.client, "post", mock)
    result = client.post("/api/decide", json={"mode": "live", **PAYLOAD})
    assert result.status_code == 200, result.text
    assert result.json()["model"] == MODEL
    assert result.json()["answers"] == REPLY["answers"]
    assert app.state.gpu is None
    assert mock.call_args.args == ("http://vllm.internal:8100/v1/systemone",)
    assert mock.call_args.kwargs["json"] == PAYLOAD
    assert mock.call_args.kwargs["headers"] == {"Authorization": "Bearer test-server-side-secret"}
    assert "test-server-side-secret" not in result.text


def test_vllm_status_does_not_control_original_gpu(client, monkeypatch):
    monkeypatch.setattr(app.state.client, "get", AsyncMock(return_value=response(data={
        "status": "ok", "engine": "vllm", "model": MODEL, "pending_requests": 1,
    })))
    state = client.get("/api/gpu").json()
    assert state["provider"] == "vllm" and state["instance_id"] == "i-vllm"
    assert state["phase"] == "ready" and state["busy"]
    assert state["disk_gib"] == 160
    assert not state["can_manage"] and not state["idle_auto_stop"]
    assert client.post("/api/gpu/start").status_code == 409
    assert client.post("/api/gpu/stop").status_code == 409


def test_vllm_outage_preserves_api_readiness_and_disables_ready_indicator(client, monkeypatch):
    monkeypatch.setattr(app.state.client, "get", AsyncMock(side_effect=httpx.ConnectError("down")))
    assert client.get("/api/health").json()["connected"] is False
    assert client.get("/api/gpu").json()["phase"] == "error"
    assert client.get("/api/ready").status_code == 200


def test_vllm_rejects_health_from_original_engine(client, monkeypatch):
    monkeypatch.setattr(app.state.client, "get", AsyncMock(return_value=response(data={
        "status": "ok", "model": "strands-decider-2B-hobson-v19", "device": "cuda",
    })))
    assert client.get("/api/health").json()["connected"] is False


def test_vllm_overload_is_not_retried_or_hidden_as_connection_failure(client, monkeypatch):
    mock = AsyncMock(return_value=response(status=429, data={"detail": "Queue full"}))
    monkeypatch.setattr(app.state.client, "post", mock)
    result = client.post("/api/decide", json={"mode": "live", **PAYLOAD})
    assert result.status_code == 429
    assert mock.await_count == 1


def test_vllm_concurrent_requests_do_not_share_the_original_serial_lease(client, monkeypatch):
    assert isinstance(app.state.lock, asyncio.Semaphore)

    async def run():
        both_entered = asyncio.Event()
        entered = 0

        async def upstream(*args, **kwargs):
            nonlocal entered
            entered += 1
            if entered == 2:
                both_entered.set()
            await asyncio.wait_for(both_entered.wait(), timeout=1)
            return response()

        monkeypatch.setattr(app.state.client, "post", upstream)
        requests = [Request({"type": "http", "app": SimpleNamespace(state=app.state)}) for _ in range(2)]
        replies = await asyncio.gather(*(live_decision(r, PAYLOAD) for r in requests))
        assert entered == 2 and all(r["model"] == MODEL for r in replies)

    asyncio.run(run())


def test_vllm_requires_a_key_at_startup(monkeypatch):
    monkeypatch.setenv("GPU_PROVIDER", "vllm")
    monkeypatch.delenv("DECIDER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="server-side DECIDER_API_KEY"), TestClient(app):
        pass


def test_vllm_network_and_secret_are_private_and_scoped():
    resources = template()["Resources"]
    ingress = resources["VllmApiIngress"]["Properties"]
    assert ingress["FromPort"] == ingress["ToPort"] == 8100
    assert "CidrIp" not in ingress
    assert ingress["SourceSecurityGroupId"] == {"Ref": "TaskSecurityGroup"}
    container = resources["TaskDefinition"]["Properties"]["ContainerDefinitions"][0]
    assert "api_key::" in str(container["Secrets"])
    assert "DECIDER_API_KEY" not in str(container["Environment"])
    assert resources["VllmSecretPolicy"]["Properties"]["Roles"] == [{"Ref": "ExecutionRole"}]
    assert resources["SecretsManagerEndpoint"]["Properties"]["PrivateDnsEnabled"]
    assert resources["VllmRoute"]["Properties"]["DestinationCidrBlock"] == {
        "Fn::Sub": "${VllmPrivateIp}/32"
    }
