import base64
import copy
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.vision import ASSETS, CASES


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DECIDER_VISION_URL", "http://vision:18123")
    with TestClient(app) as client:
        client.headers["X-Decider-Client"] = "web"
        assert client.post("/api/auth/login", json={
            "username": "tester", "password": "test-password-with-entropy",
        }).status_code == 200
        yield client


def upstream(monkeypatch, data=None, status=200, error=None):
    if data is None:
        data = copy.deepcopy(CASES["case-11"]["recordings"]["original"]["response"])
    mock = AsyncMock(side_effect=error, return_value=httpx.Response(
        status, json=data, request=httpx.Request("POST", "http://vision:18123/v1/systemone"),
    ))
    monkeypatch.setattr(app.state.client, "post", mock)
    return mock


def test_vision_requires_login_and_csrf():
    with TestClient(app) as anonymous:
        assert anonymous.get("/api/vision/catalog").status_code == 401
        assert anonymous.post("/api/vision/decide", json={"case_id": "case-01"}).status_code == 401


def test_catalog_has_all_images_and_three_question_sets(client):
    result = client.get("/api/vision/catalog").json()
    assert len(result["cases"]) == 12
    assert {g["id"] for g in result["groups"]} == {"payment", "support", "receipt"}
    for case in result["cases"]:
        assert client.get(case["image_url"]).status_code == 200


def test_historical_record_preserves_wrong_choice_and_labels_timing(client):
    result = client.post("/api/vision/decide", json={"case_id": "case-11"}).json()
    assert result["source"] == "recorded"
    assert result["answers"]["action"]["choice"] == "accept"
    assert result["expected"]["action"] == "request_reference"
    assert result["model_ms"] == 168.42
    assert result["backend_total_ms"] is None
    assert result["captured_at"].startswith("2026-10-23")


def test_live_uses_image_backend_and_does_not_send_reference(client, monkeypatch):
    mock = upstream(monkeypatch)
    result = client.post("/api/vision/decide", json={"case_id": "case-11", "mode": "live"}).json()
    assert result["source"] == "live" and result["captured_at"] is None
    assert result["answers"]["action"]["choice"] == "accept"
    assert result["backend_total_ms"] >= 0
    assert mock.call_args.args == ("http://vision:18123/v1/systemone",)
    payload = mock.call_args.kwargs["json"]
    assert set(payload) == {"state", "questions", "images"}
    assert base64.b64decode(payload["images"][0]) == (ASSETS / "case-11.png").read_bytes()
    assert "images" not in result["request"]  # Do not echo uploaded bytes in an export.
    assert result["request"]["image"]["sent"]


def test_reverse_changes_only_candidate_order(client, monkeypatch):
    data = CASES["case-11"]["recordings"]["reverse"]["response"]
    mock = upstream(monkeypatch, data)
    result = client.post("/api/vision/decide", json={
        "case_id": "case-11", "mode": "live", "variant": "reverse",
    }).json()
    questions = mock.call_args.kwargs["json"]["questions"]
    original = CASES["case-11"]["request"]["questions"]["action"]["criteria"]
    assert list(questions["action"]["criteria"]) == list(reversed(original))
    assert questions["action"]["criteria"] == original
    assert result["answers"]["action"]["choice"] == "request_both"


@pytest.mark.parametrize("variant", ["no_image", "blank"])
def test_missing_image_controls_never_score_against_original_picture(client, variant):
    result = client.post("/api/vision/decide", json={"case_id": "case-01", "variant": variant}).json()
    assert result["expected"] is None
    assert result["request"]["image"]["sent"] == (variant == "blank")
    assert result["source"] == "recorded"


def test_uploaded_images_cannot_get_canned_results_or_reference_scores(client, monkeypatch):
    body = {"image": base64.b64encode((ASSETS / "case-11.png").read_bytes()).decode(), "task": "receipt"}
    assert client.post("/api/vision/decide", json=body).status_code == 422
    mock = upstream(monkeypatch)
    response = client.post("/api/vision/decide", json={**body, "mode": "live"})
    assert response.status_code == 200
    assert response.json()["expected"] is None
    assert mock.call_args.kwargs["json"]["images"] == [body["image"]]
    assert client.post("/api/vision/decide", json={
        **body, "mode": "live", "case_id": "case-01",
    }).status_code == 422


@pytest.mark.parametrize("image", ["https://example.com/image.png", "PHN2Zz48L3N2Zz4=", "%%%"])
def test_unsupported_input_never_reaches_gpu(client, monkeypatch, image):
    mock = upstream(monkeypatch)
    assert client.post("/api/vision/decide", json={"mode": "live", "image": image}).status_code == 422
    mock.assert_not_called()


def test_outage_is_an_error_and_does_not_fall_back_to_recorded(client, monkeypatch):
    upstream(monkeypatch, error=httpx.ConnectError("unavailable"))
    response = client.post("/api/vision/decide", json={"case_id": "case-11", "mode": "live"})
    assert response.status_code == 502
    assert "answers" not in response.json()


def test_invalid_model_reply_is_rejected(client, monkeypatch):
    response = copy.deepcopy(CASES["case-11"]["recordings"]["original"]["response"])
    response["answers"]["action"]["choice"] = "not-a-candidate"
    upstream(monkeypatch, response)
    assert client.post("/api/vision/decide", json={
        "case_id": "case-11", "mode": "live",
    }).status_code == 502
