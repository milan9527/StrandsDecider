import copy
import io
import json
from decimal import Decimal
from unittest.mock import MagicMock

import httpx
import pytest
from botocore.exceptions import ConnectionClosedError, ConnectTimeoutError, ReadTimeoutError
from fastapi.testclient import TestClient

from app.crypto import OPTIONS, Snapshot, payload_for, reference
from app.jev import ENDPOINT, JevClient, JevError, create_client
from app.main import app
from deployment import jev_proxy
from deployment.infrastructure import template


def reply(payload, choice, **extra):
    criteria = payload["questions"]["action"]["criteria"]
    return {
        "model": "jev-1.13.0",
        "answers": {
            "action": {
                "type": "choice",
                "choice": choice,
                "probabilities": {k: float(k == choice) for k in criteria},
                "confidence": 1.0,
            }
        },
        "usage": {"input_tokens": 120, "output_tokens": 14},
        **extra,
    }


def direct_client(handler):
    client = JevClient(api_key="test-secret-not-for-output")
    client.http.close()
    client.http = httpx.Client(
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "Bearer test-secret-not-for-output"},
    )
    return client


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("BEDROCK_ENABLED", raising=False)
    with TestClient(app, headers={"X-Decider-Client": "web"}) as c:
        assert (
            c.post(
                "/api/auth/login",
                json={"username": "tester", "password": "test-password-with-entropy"},
            ).status_code
            == 200
        )
        yield c


def test_jev_sends_identical_business_payload_and_preserves_version():
    payload = payload_for(
        Snapshot(scenario="pending", message="未到账", expected=129, received=129, confirmations=3),
        "approve",
    )
    original = copy.deepcopy(payload)

    def handler(request):
        assert str(request.url) == ENDPOINT
        assert request.headers["authorization"] == "Bearer test-secret-not-for-output"
        assert json.loads(request.content) == {**payload, "model": "jev-latest"}
        return httpx.Response(200, json=reply(payload, "approved", provider_debug="ignored"))

    c = direct_client(handler)
    try:
        result = c.decide(payload)
        assert result["choice"] == "approved"
        assert result["model"] == "jev-1.13.0"
        assert result["confidence"] == 1.0
        assert result["usage"]["input_tokens"] == 120
        assert result["model_reported_ms"] is None
        assert "provider_debug" not in result
        assert payload == original
    finally:
        c.close()


@pytest.mark.parametrize(
    ("status", "expected"),
    [(401, 503), (403, 503), (429, 429), (504, 504), (422, 422), (500, 503), (302, 503)],
)
def test_provider_errors_are_sanitized_without_retry(status, expected):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status, text="test-secret-not-for-output", headers={"Location": "https://evil.example"}
        )

    c = direct_client(handler)
    try:
        with pytest.raises(JevError) as error:
            c.decide({})
        assert error.value.status_code == expected
        assert "test-secret" not in str(error.value)
        assert len(calls) == 1
    finally:
        c.close()


@pytest.mark.parametrize(
    "failure", ["invalid_choice", "missing_candidate", "nan", "bad_usage", "malformed", "timeout"]
)
def test_malformed_jev_output_and_timeout_are_not_decisions(failure):
    payload = payload_for(
        Snapshot(scenario="pending", message="未到账", expected=129, received=129, confirmations=3),
        "approve",
    )
    data = reply(payload, "approved")
    if failure == "invalid_choice":
        data["answers"]["action"]["choice"] = "invented"
    elif failure == "missing_candidate":
        del data["answers"]["action"]["probabilities"]["await_approval"]
    elif failure == "nan":
        data["answers"]["action"]["confidence"] = float("nan")
    elif failure == "bad_usage":
        data["usage"]["input_tokens"] = -1

    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("upstream secret", request=request)
        return httpx.Response(
            200, content=b"broken" if failure == "malformed" else json.dumps(data).encode()
        )

    c = direct_client(handler)
    try:
        with pytest.raises(JevError) as error:
            c.decide(payload)
        assert error.value.status_code == (504 if failure == "timeout" else 502)
        assert "upstream secret" not in str(error.value)
    finally:
        c.close()


def test_all_scenarios_profiles_and_stages_use_same_jev_payload(client):
    cases = client.get("/api/crypto/catalog").json()["cases"]
    captured = []

    def handler(request):
        body = json.loads(request.content)
        payload = {k: body[k] for k in ("state", "questions")}
        captured.append(payload)
        choice = next(iter(payload["questions"]["action"]["criteria"]))
        return httpx.Response(200, json=reply(payload, choice))

    app.state.jev = direct_client(handler)
    for case in cases:
        for profile in ("baseline", "optimized"):
            for stage in OPTIONS:
                response = client.post(
                    "/api/crypto/decision",
                    json={
                        "snapshot": case["snapshot"],
                        "stage": stage,
                        "provider": "jev",
                        "input_profile": profile,
                    },
                )
                assert response.status_code == 200
                result = response.json()
                expected = payload_for(Snapshot(**case["snapshot"]), stage, input_profile=profile)
                assert captured[-1] == result["model_input"] == expected
                assert result["source"] == "live"
                assert result["model"] == "jev-1.13.0"
                assert result["timings"]["backend_total_ms"] > 0
                assert result["timings"]["model_reported_ms"] is None
                assert "test-secret" not in response.text
    assert len(captured) == 40


def test_jev_unconfigured_replay_and_auth(client):
    cat = client.get("/api/crypto/catalog").json()
    assert cat["jev_configured"] is False
    assert cat["jev_model"] == "jev-latest"
    body = {"snapshot": cat["cases"][0]["snapshot"], "stage": "approve", "provider": "jev"}
    assert client.post("/api/crypto/decision", json=body).status_code == 503
    replay = client.post("/api/crypto/decision", json={**body, "mode": "replay"}).json()
    assert replay["timings"] is None and replay["source"] == "rule_replay"
    assert replay["usage"] is None and replay["probabilities"] is None
    client.post("/api/auth/logout")
    assert client.post("/api/crypto/decision", json=body).status_code == 401


def test_jev_error_does_not_fall_back_or_trigger_an_execution(client):
    cat = client.get("/api/crypto/catalog").json()
    app.state.jev = MagicMock()
    app.state.jev.decide.side_effect = JevError(429, "Jev 请求限流，请稍后重试。")
    response = client.post(
        "/api/crypto/decision",
        json={
            "snapshot": cat["cases"][0]["snapshot"],
            "stage": "execute",
            "provider": "jev",
        },
    )
    assert response.status_code == 429 and response.headers["Retry-After"] == "5"
    assert "choice" not in response.json()


def test_jev_loop_uses_feedback_and_completes_with_simulated_events(client):
    cat = client.get("/api/crypto/catalog").json()
    snapshots = {case["id"]: Snapshot(**case["snapshot"]) for case in cat["cases"]}
    calls = []

    def decide(payload):
        # Explicit fake for the control flow; this is not a model-quality test.
        state = json.loads(payload["state"])
        calls.append(state)
        s = snapshots[state["case_type"]]
        # Latest facts provided by the API determine the replay response.
        for key, value in {
            "received": Decimal(state["received_amount"]),
            "confirmations": state["confirmations"],
            "address_verified": state["refund_destination_verified"],
            "approved": state["refund_approved"],
            "risk_flag": state["risk_flag"],
            "settled": state["settled"],
        }.items():
            setattr(s, key, value)
        criteria = payload["questions"]["action"]["criteria"]
        stage = next(stage for stage, options in OPTIONS.items() if set(options) == set(criteria))
        choice = reference(Snapshot(**s.model_dump()), stage)
        return {
            "model": "explicit-test-double",
            "choice": choice,
            "confidence": 1,
            "probabilities": {k: float(k == choice) for k in criteria},
            "usage": None,
            "model_reported_ms": None,
        }

    app.state.jev = MagicMock()
    app.state.jev.decide.side_effect = decide
    state = {"snapshot": cat["cases"][0]["snapshot"]}
    for _ in range(32):
        response = client.post(
            "/api/crypto/loop/tick",
            json={
                "state": state,
                "provider": "jev",
                "auto_events": True,
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()
        state = data["state"]
        if state["status"] in ("complete", "handoff"):
            break
    assert state["status"] == "complete"
    assert state["ledger"]["simulated"]
    assert any(row["execution"]["recent_feedback"] for row in calls[1:])


def test_lambda_uses_only_its_secret_and_fixed_endpoint(monkeypatch):
    payload = payload_for(
        Snapshot(scenario="pending", message="未到账", expected=129, received=129, confirmations=3),
        "approve",
    )
    monkeypatch.setenv("JEV_SECRET_ARN", "secret-arn")
    monkeypatch.setattr(jev_proxy, "_key", None)
    secrets = MagicMock()
    secrets.get_secret_value.return_value = {"SecretString": "private-key"}
    monkeypatch.setattr(
        jev_proxy.boto3, "client", lambda service: secrets if service == "secretsmanager" else None
    )
    connection = MagicMock()
    upstream = connection.getresponse.return_value
    upstream.status = 200
    upstream.read.return_value = json.dumps(reply(payload, "approved")).encode()
    factory = MagicMock(return_value=connection)
    monkeypatch.setattr(jev_proxy.http.client, "HTTPSConnection", factory)
    body = {**payload, "model": "jev-latest"}
    result = jev_proxy.handler(body, None)
    assert result["status"] == 200
    factory.assert_called_once_with("api.typesafe.ai", timeout=30)
    secrets.get_secret_value.assert_called_once_with(SecretId="secret-arn")
    assert connection.request.call_args.args[:2] == ("POST", "/v1/systemone")
    assert "private-key" not in json.dumps(result)
    upstream.status = 401
    assert jev_proxy.handler(body, None) == {"status": 401}
    assert jev_proxy._key is None
    assert jev_proxy.handler({**body, "url": "https://evil.example"}, None)["status"] == 422
    assert jev_proxy.handler({**body, "model": "other"}, None)["status"] == 422
    connection.close.assert_called()


def test_lambda_client_validates_envelope_and_drops_errors(monkeypatch):
    runtime = MagicMock()
    monkeypatch.setattr("app.jev.boto3.client", lambda *a, **k: runtime)
    monkeypatch.setenv("JEV_FUNCTION_NAME", "only-this-function")
    c = create_client()
    payload = payload_for(
        Snapshot(scenario="pending", message="未到账", expected=129, received=129, confirmations=3),
        "approve",
    )
    runtime.invoke.return_value = {
        "Payload": io.BytesIO(
            json.dumps({"status": 200, "data": reply(payload, "approved")}).encode()
        )
    }
    assert c.decide(payload)["choice"] == "approved"
    assert runtime.invoke.call_args.kwargs["FunctionName"] == "only-this-function"
    runtime.invoke.return_value = {
        "FunctionError": "Unhandled",
        "Payload": io.BytesIO(b'{"error":"private-key"}'),
    }
    with pytest.raises(JevError) as error:
        c.decide(payload)
    assert "private-key" not in str(error.value)
    c.close()


@pytest.mark.parametrize("recover", [True, False])
def test_bridge_reconnects_only_before_submission(monkeypatch, caplog, recover):
    runtime = MagicMock()
    monkeypatch.setattr("app.jev.boto3.client", lambda *a, **k: runtime)
    c = JevClient(function_name="test-bridge")
    payload = payload_for(
        Snapshot(scenario="pending", message="未到账", expected=129, received=129, confirmations=3),
        "approve",
    )
    timeout = ConnectTimeoutError(endpoint_url="https://private-key.invalid")
    success = {
        "Payload": io.BytesIO(
            json.dumps({"status": 200, "data": reply(payload, "approved")}).encode()
        )
    }
    runtime.invoke.side_effect = [timeout, success if recover else timeout]
    if recover:
        assert c.decide(payload)["choice"] == "approved"
    else:
        with pytest.raises(JevError) as error:
            c.decide(payload)
        assert error.value.status_code == 503
        assert "未提交模型请求" in str(error.value)
    assert runtime.invoke.call_count == 2
    assert "private-key" not in caplog.text
    c.close()


@pytest.mark.parametrize(
    "failure", ["read_timeout", "connection_closed", "rate_limit", "upstream_unavailable"]
)
def test_bridge_does_not_resubmit_after_possible_model_call(monkeypatch, caplog, failure):
    runtime = MagicMock()
    monkeypatch.setattr("app.jev.boto3.client", lambda *a, **k: runtime)
    c = JevClient(function_name="test-bridge")
    if failure == "read_timeout":
        runtime.invoke.side_effect = ReadTimeoutError(endpoint_url="https://private-key.invalid")
        expected = 504
    elif failure == "connection_closed":
        runtime.invoke.side_effect = ConnectionClosedError(
            endpoint_url="https://private-key.invalid"
        )
        expected = 503
    else:
        status = 429 if failure == "rate_limit" else 503
        runtime.invoke.return_value = {
            "Payload": io.BytesIO(json.dumps({"status": status}).encode())
        }
        expected = status
    with pytest.raises(JevError) as error:
        c.decide({})
    assert error.value.status_code == expected
    assert runtime.invoke.call_count == 1
    assert "private-key" not in caplog.text
    assert "private-key" not in str(error.value)
    c.close()


def test_bridge_calls_own_and_close_distinct_clients(monkeypatch):
    payload = payload_for(
        Snapshot(scenario="pending", message="未到账", expected=129, received=129, confirmations=3),
        "approve",
    )
    runtimes = [MagicMock(), MagicMock()]
    streams = []
    for runtime in runtimes:
        stream = io.BytesIO(
            json.dumps({"status": 200, "data": reply(payload, "approved")}).encode()
        )
        streams.append(stream)
        runtime.invoke.return_value = {"Payload": stream}
    factory = MagicMock(side_effect=runtimes)
    monkeypatch.setattr("app.jev.boto3.client", factory)
    c = JevClient(function_name="test-bridge")
    for runtime in runtimes:
        assert c.decide(payload)["choice"] == "approved"
        runtime.invoke.assert_called_once()
        runtime.close.assert_called_once()
    assert factory.call_count == 2
    assert all(stream.closed for stream in streams)
    c.close()


def test_jev_infrastructure_keeps_ecs_private_and_scopes_credentials():
    doc = template()
    resources = doc["Resources"]
    fn = resources["JevFunction"]
    assert fn["Condition"] == "HasJev"
    assert "VpcConfig" not in fn["Properties"]
    assert not any(
        v["Type"] in ("AWS::Lambda::Url", "AWS::EC2::NatGateway") for v in resources.values()
    )
    statements = resources["JevRole"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]
    assert statements[0]["Action"] == "secretsmanager:GetSecretValue"
    assert statements[0]["Resource"] == {"Ref": "JevSecretArn"}
    assert resources["JevInvokePolicy"]["Properties"]["PolicyDocument"]["Statement"][0][
        "Resource"
    ] == {"Fn::GetAtt": ["JevFunction", "Arn"]}
    endpoint = resources["LambdaEndpoint"]["Properties"]
    assert endpoint["PrivateDnsEnabled"]
    assert endpoint["PolicyDocument"]["Statement"][0]["Action"] == "lambda:InvokeFunction"
    assert endpoint["PolicyDocument"]["Statement"][0]["Condition"]["ArnEquals"][
        "aws:PrincipalArn"
    ] == {"Fn::GetAtt": ["TaskRole", "Arn"]}
    env = resources["TaskDefinition"]["Properties"]["ContainerDefinitions"][0]["Environment"]
    assert not any(v["Name"] in ("JEV_API_KEY", "JEV_API_KEY_FILE") for v in env)
