import io
import json
from unittest.mock import MagicMock

import boto3
import pytest
from botocore.exceptions import ClientError
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient
from moto import mock_aws

from app.gpu_state import GpuState, TransitionConflict
from app.main import app
from deployment.sagemaker_controller import reconcile
from deployment.sagemaker_infrastructure import template
from deployment.sagemaker_server import create_gateway


@pytest.fixture
def store():
    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")
        client.create_table(
            TableName="gpu-state",
            BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
        )
        state = GpuState(client, "gpu-state")
        state.get()
        state.update("SET provider=:provider", {":provider": "sagemaker"})
        yield state


def client(status=None):
    sm = MagicMock()
    if status:
        sm.describe_endpoint.return_value = {
            "EndpointStatus": status,
            "ProductionVariants": [{"CurrentInstanceCount": 1}],
        }
    else:
        sm.describe_endpoint.side_effect = ClientError(
            {"Error": {"Code": "ValidationException", "Message": "Could not find endpoint demo"}},
            "DescribeEndpoint",
        )
    return sm


def tick(store, sm, now):
    return reconcile(store, sm, endpoint_name="demo", endpoint_config="config", now=now)


def test_create_is_bounded_to_one_fixed_endpoint_and_adopts_existing_creation(store):
    store.start(now=100)
    sm = client()
    assert tick(store, sm, 101)["action"] == "creating"
    sm.create_endpoint.assert_called_once_with(
        EndpointName="demo",
        EndpointConfigName="config",
        Tags=[{"Key": "Project", "Value": "StrandsDecider"}],
    )
    sm = client("Creating")
    assert tick(store, sm, 102)["action"] == "starting"
    sm.create_endpoint.assert_not_called()
    assert "endpoint" not in store.get()


def test_hosting_config_uses_names_not_cloudformation_arn_refs():
    resources = template()["Resources"]
    variant = resources["EndpointConfig"]["Properties"]["ProductionVariants"][0]
    assert variant["ModelName"] == {"Fn::GetAtt": ["Model", "ModelName"]}
    env = resources["Controller"]["Properties"]["Environment"]["Variables"]
    assert env["ENDPOINT_CONFIG"] == {"Fn::GetAtt": ["EndpointConfig", "EndpointConfigName"]}
    assert variant["InitialInstanceCount"] == 1
    assert resources["Model"]["Properties"]["EnableNetworkIsolation"] is True
    statements = resources["ControllerRole"]["Properties"]["Policies"][0]["PolicyDocument"][
        "Statement"
    ]
    create_policy = next(p for p in statements if p["Action"] == "sagemaker:CreateEndpoint")
    assert {"Fn::GetAtt": ["EndpointConfig", "EndpointConfigArn"]} in create_policy["Resource"]


def test_unknown_describe_failure_never_creates_another_endpoint(store):
    store.start(now=100)
    sm = client()
    sm.describe_endpoint.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "denied"}}, "DescribeEndpoint"
    )
    with pytest.raises(ClientError):
        tick(store, sm, 101)
    sm.create_endpoint.assert_not_called()


def test_ready_uses_signed_runtime_uri_and_polling_does_not_extend_idle(store):
    store.start(now=100)
    assert tick(store, client("InService"), 101)["action"] == "ready"
    assert store.get()["endpoint"] == "sagemaker://demo"
    assert store.get()["last_activity"] == 101
    tick(store, client("InService"), 102)
    assert store.get()["last_activity"] == 101


def test_stop_waits_for_inference_then_deletes_endpoint_and_keeps_disk_metadata(store):
    store.start(now=100)
    tick(store, client("InService"), 101)
    store.update("SET instance_id=:id", {":id": "retained-ec2"})
    token, _ = store.acquire(100, now=102)
    store.stop(now=103)
    sm = client("InService")
    assert tick(store, sm, 104)["action"] == "waiting_for_inference"
    sm.delete_endpoint.assert_not_called()
    store.release(token, now=105)
    assert tick(store, sm, 106)["action"] == "deleting"
    sm.delete_endpoint.assert_called_once_with(EndpointName="demo")
    deleting = client("Deleting")
    tick(store, deleting, 107)
    deleting.delete_endpoint.assert_not_called()
    assert tick(store, client(), 108)["action"] == "stopped"
    assert store.get()["instance_id"] == "retained-ec2"
    assert store.get()["instance_count"] == 0


def test_failed_allocation_preserves_reason_and_cleans_failed_endpoint(store):
    store.start(now=100)
    sm = client("Failed")
    sm.describe_endpoint.return_value["FailureReason"] = "Insufficient capacity for ml.g6.xlarge"
    assert tick(store, sm, 101)["action"] == "deleting_failed_endpoint"
    sm.delete_endpoint.assert_called_once()
    assert tick(store, client(), 102)["action"] == "error"
    assert "Insufficient capacity" in store.get()["last_error_message"]
    assert store.get()["desired"] == "stopped"
    assert "last_error_message" not in store.start(now=103)


def test_quota_rejection_is_exposed_without_unbounded_retry(store):
    store.start(now=100)
    sm = client()
    sm.create_endpoint.side_effect = ClientError(
        {"Error": {"Code": "ResourceLimitExceeded", "Message": "GPU quota exceeded"}},
        "CreateEndpoint",
    )
    assert tick(store, sm, 101)["action"] == "error"
    assert store.get()["last_error_message"] == "GPU quota exceeded"
    assert store.get()["desired"] == "stopped"


def test_idle_and_startup_timeout_delete_compute(store):
    store.start(now=100)
    tick(store, client("InService"), 101)
    sm = client("InService")
    assert tick(store, sm, 1901)["action"] == "deleting"
    assert store.get()["stop_reason"] == "idle"
    tick(store, client(), 1902)
    store.start(now=2000)
    assert tick(store, client("Creating"), 3200)["action"] == "deleting"
    assert store.get()["stop_reason"] == "startup_timeout"
    assert tick(store, client(), 3201)["action"] == "error"


def test_timeout_keeps_stop_request_when_aws_cannot_cancel_creation(store):
    store.start(now=100)
    sm = client("Creating")
    sm.delete_endpoint.side_effect = ClientError(
        {
            "Error": {
                "Code": "ValidationException",
                "Message": 'Cannot update in-progress endpoint "arn:aws:sagemaker:demo".',
            }
        },
        "DeleteEndpoint",
    )
    assert tick(store, sm, 1300)["action"] == "waiting_for_creation_before_delete"
    assert store.get()["desired"] == "stopped"
    assert store.get()["phase"] == "stopping"
    assert store.get()["stop_reason"] == "startup_timeout"
    assert "endpoint" not in store.get()
    assert tick(store, sm, 1360)["action"] == "waiting_for_creation_before_delete"
    sm.create_endpoint.assert_not_called()
    with pytest.raises(TransitionConflict):
        store.start(now=1361)
    # Even if AWS finishes successfully later, the queued stop must win.
    ready = client("InService")
    assert tick(store, ready, 1420)["action"] == "deleting"
    ready.delete_endpoint.assert_called_once_with(EndpointName="demo")
    assert store.get()["phase"] == "stopping"
    assert tick(store, client(), 1480)["action"] == "error"


def test_concurrent_stop_prevents_creation(store):
    store.start(now=100)
    original = store.update

    def stop_then_update(expression, values, **kwargs):
        original("SET desired=:off, requested_at=:now", {":off": "stopped", ":now": 102})
        return original(expression, values, **kwargs)

    store.update = stop_then_update
    sm = client()
    with pytest.raises(TransitionConflict):
        tick(store, sm, 101)
    sm.create_endpoint.assert_not_called()


def test_gateway_translates_sagemaker_contract_without_changing_decider_payload():
    model = FastAPI()
    received = []

    @model.get("/health")
    def health():
        return {"status": "ok", "model": "v19", "device": "cuda"}

    @model.post("/v1/systemone")
    def decide(payload: dict):
        received.append(payload)
        return Response(
            '{"detail":"context too long"}', status_code=422, media_type="application/json"
        )

    with TestClient(create_gateway(model)) as web:
        assert web.get("/ping").json()["device"] == "cuda"
        assert web.post("/invocations", json={"operation": "health"}).json()["model"] == "v19"
        payload = {"state": "long", "questions": {"ok": {"type": "noul"}}}
        assert web.post("/invocations", json=payload).status_code == 422
        assert received == [payload]
        assert web.post("/invocations", content=b"{bad").status_code == 422


def test_api_invokes_sagemaker_and_preserves_real_individual_timings():
    runtime = MagicMock()
    bodies = []

    def invoke(**kwargs):
        assert kwargs["EndpointName"] == "demo"
        payload = json.loads(kwargs["Body"])
        bodies.append(payload)
        answer = {
            "model": "strands-decider-2B-hobson-v19",
            "answers": {k: {"type": "noul", "noul": 0.9} for k in payload["questions"]},
            "latency_ms": 1.0,
        }
        return {"Body": io.BytesIO(json.dumps(answer).encode())}

    runtime.invoke_endpoint.side_effect = invoke
    with TestClient(app) as web:
        web.headers["X-Decider-Client"] = "web"
        assert (
            web.post(
                "/api/auth/login",
                json={"username": "tester", "password": "test-password-with-entropy"},
            ).status_code
            == 200
        )
        app.state.sagemaker = runtime
        app.state.upstream = "sagemaker://demo"
        payload = {
            "mode": "live",
            "measure_decisions": True,
            "state": "test",
            "questions": {
                "a": {"type": "noul", "instructions": "Is this a test?"},
                "b": {"type": "noul", "instructions": "Is the input short?"},
            },
        }
        response = web.post("/api/decide", json=payload)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["source"] == "live"
        assert set(data["timings"]["decisions_ms"]) == {"a", "b"}
        assert len(bodies) == 2
        runtime.invoke_endpoint.side_effect = ClientError(
            {"Error": {"Code": "ModelError", "Message": "rejected"}, "OriginalStatusCode": 422},
            "InvokeEndpoint",
        )
        assert web.post("/api/decide", json=payload).status_code == 422
