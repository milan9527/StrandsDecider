import base64
import copy
import json
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.jev import JevClient, JevError
from app.main import app
from app.vision import ASSETS, CASES
from app.vision_providers import GPT_MODEL, bedrock_decide, jev_payload
from deployment import jev_proxy


def payload(case="case-11"):
    return {**copy.deepcopy(CASES[case]["request"]),
            "images": [base64.b64encode((ASSETS / f"{case}.png").read_bytes()).decode()]}


def bedrock_reply(selected):
    return {
        "stopReason": "end_turn",
        "output": {"message": {"content": [{"text": json.dumps(selected)}]}},
        "usage": {"inputTokens": 500, "outputTokens": 20},
        "metrics": {"latencyMs": 901},
    }


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("BEDROCK_ENABLED", raising=False)
    with TestClient(app, headers={"X-Decider-Client": "web"}) as c:
        assert c.post("/api/auth/login", json={
            "username": "tester", "password": "test-password-with-entropy",
        }).status_code == 200
        yield c


def test_jev_assets_retain_pixels_and_all_questions():
    original = payload()
    wire = jev_payload(original)
    assert wire["questions"] == original["questions"]
    assert len(wire["assets"]) == 1
    key, asset = next(iter(wire["assets"].items()))
    assert wire["state"] == original["state"] + "\n" + key
    assert asset["data_base64"] == original["images"][0]
    assert set(wire) == {"state", "questions", "assets"}
    assert set(jev_payload({k: v for k, v in original.items() if k != "images"})) == {"state", "questions"}


def test_jev_direct_adds_image_header_and_preserves_mixed_answers():
    wire = jev_payload(payload())
    expected = copy.deepcopy(CASES["case-11"]["recordings"]["original"]["response"])
    expected["model"] = "jev-1.14.0"
    def handler(request):
        assert request.headers["TypeSafe-Danger-Zone-Images"] == "true"
        assert json.loads(request.content) == {**wire, "model": "jev-latest"}
        return httpx.Response(200, json=expected)
    c = JevClient(api_key="test-key")
    c.http.close()
    c.http = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        assert c.system_one(wire)["answers"] == expected["answers"]
    finally:
        c.close()


def test_bridge_accepts_mixed_questions_and_one_local_image(monkeypatch):
    body = {**jev_payload(payload()), "model": "jev-latest"}
    monkeypatch.setattr(jev_proxy, "_key", "test-key")
    connection = MagicMock()
    connection.getresponse.return_value.status = 200
    connection.getresponse.return_value.read.return_value = b'{"answers": {}, "provider_debug": "omit"}'
    monkeypatch.setattr(jev_proxy.http.client, "HTTPSConnection", MagicMock(return_value=connection))
    assert jev_proxy.handler(body, None) == {"status": 200, "data": {"answers": {}}}
    assert connection.request.call_args.kwargs["headers"]["TypeSafe-Danger-Zone-Images"] == "true"
    assert json.loads(connection.request.call_args.kwargs["body"]) == body


@pytest.mark.parametrize("mutation", ["url", "unreferenced", "oversized", "invalid_base64", "wrong_type", "too_many"])
def test_bridge_rejects_invalid_images_before_outbound(monkeypatch, mutation):
    body = {**jev_payload(payload()), "model": "jev-latest"}
    asset = next(iter(body["assets"].values()))
    if mutation == "url":
        asset["url"] = "https://example.com/image.png"
    elif mutation == "unreferenced":
        body["state"] = "missing image"
    elif mutation == "oversized":
        asset["data_base64"] = "A" * 2_666_669
    elif mutation == "invalid_base64":
        asset["data_base64"] = "%%%"
    elif mutation == "wrong_type":
        body["questions"]["action"]["type"] = "box"
    elif mutation == "too_many":
        body["assets"]["another_reference"] = asset
    factory = MagicMock()
    monkeypatch.setattr(jev_proxy.http.client, "HTTPSConnection", factory)
    assert jev_proxy.handler(body, None) == {"status": 422}
    factory.assert_not_called()


def test_gpt_sees_same_pixels_questions_and_returns_no_fake_probability():
    original = payload()
    c = MagicMock()
    c.converse.return_value = bedrock_reply({"signature": True, "reference": False, "action": "request_reference"})
    result = bedrock_decide(c, original)
    call = c.converse.call_args.kwargs
    assert call["modelId"] == GPT_MODEL
    content = call["messages"][0]["content"]
    assert base64.b64encode(content[1]["image"]["source"]["bytes"]).decode() == original["images"][0]
    assert json.loads(content[0]["text"]) == {k: original[k] for k in ("state", "questions")}
    assert call["additionalModelRequestFields"] == {"reasoning": {"effort": "low"}}
    assert result["answers"]["signature"] == {"type": "noul", "value": True}
    assert result["answers"]["action"]["probabilities"] is None
    assert result["answers"]["action"]["confidence"] is None
    assert result["provider_latency_ms"] == 901


@pytest.mark.parametrize("selected", [
    {"signature": True, "action": "accept"},
    {"signature": True, "reference": False, "action": "not-a-choice"},
    {"signature": 1, "reference": False, "action": "accept"},
    {"signature": "false", "reference": False, "action": "accept"},
    {"signature": True, "reference": False, "action": "accept", "probability": 1},
])
def test_gpt_requires_complete_candidates_and_actual_booleans(selected):
    c = MagicMock()
    c.converse.return_value = bedrock_reply(selected)
    with pytest.raises(ValueError):
        bedrock_decide(c, payload())


def test_same_fingerprint_across_providers_and_controls(client, monkeypatch):
    jev = MagicMock()
    reply = copy.deepcopy(CASES["case-11"]["recordings"]["original"]["response"])
    reply["model"] = "jev-1.14.0"
    jev.system_one.return_value = reply
    gpt = MagicMock()
    gpt.converse.return_value = bedrock_reply({"signature": True, "reference": False, "action": "request_reference"})
    monkeypatch.setattr(app.state, "jev", jev)
    monkeypatch.setattr(app.state, "bedrock", gpt)
    for variant in ("original", "reverse", "no_image", "blank"):
        responses = [client.post("/api/vision/decide", json={
            "provider": provider, "mode": "live", "case_id": "case-11", "variant": variant,
        }).json() for provider in ("jev", "bedrock")]
        assert responses[0]["input_fingerprint"] == responses[1]["input_fingerprint"]
        assert responses[0]["request"] == responses[1]["request"]
        assert responses[0]["answers"]["action"]["choice"] == "accept"  # Preserve the wrong answer.
        assert responses[1]["answers"]["action"]["choice"] == "request_reference"
        if variant == "original":
            historical = client.post("/api/vision/decide", json={"case_id": "case-11"}).json()
            assert historical["input_fingerprint"] == responses[0]["input_fingerprint"]
        if variant in ("no_image", "blank"):
            assert all(r["expected"] is None for r in responses)
        if variant == "no_image":
            assert "assets" not in jev.system_one.call_args.args[0]
            assert len(gpt.converse.call_args.kwargs["messages"][0]["content"]) == 1


def test_failure_and_missing_history_are_not_substituted(client, monkeypatch):
    jev = MagicMock()
    jev.system_one.side_effect = JevError(429, "Jev 请求限流")
    monkeypatch.setattr(app.state, "jev", jev)
    body = {"provider": "jev", "case_id": "case-11"}
    assert client.post("/api/vision/decide", json=body).status_code == 404
    response = client.post("/api/vision/decide", json={**body, "mode": "live"})
    assert response.status_code == 429 and "answers" not in response.json()
