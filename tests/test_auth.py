import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.auth import Auth, hash_password, save_user, session_key, verify_password
from app.main import app

CREDS = {"username": "tester", "password": "test-password-with-entropy"}
HEADERS = {"X-Decider-Client": "web"}


@pytest.fixture
def client():
    with TestClient(app, base_url="https://testserver") as client:
        yield client


def login(client, **kwargs):
    return client.post("/api/auth/login", json=CREDS, headers=HEADERS, **kwargs)


@pytest.mark.parametrize(
    "path",
    [
        "/api/examples",
        "/api/health",
        "/api/auth/me",
        "/api/docs",
        "/api/openapi.json",
        "/api/decide",
        "/api/guard",
    ],
)
def test_anonymous_requests_cannot_access_api(client, path):
    response = client.get(path)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


def test_login_uses_secure_cookie_and_never_returns_token(client, monkeypatch):
    monkeypatch.setattr(app.state.auth, "secure", True)
    monkeypatch.setattr(app.state.auth, "cookie", "__Host-decider_session")
    response = login(client)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert all(part in cookie for part in ("HttpOnly", "Secure", "SameSite=strict", "Path=/"))
    assert "Domain=" not in cookie
    assert set(response.json()) == {"username", "expires_at"}
    assert client.get("/api/examples").status_code == 200
    assert client.get("/api/auth/me").json()["username"] == "tester"
    assert client.get("/api/live").status_code == 200


def test_logout_revokes_replayed_cookie(client):
    login(client)
    cookie = client.cookies.get("decider_session")
    assert client.post("/api/auth/logout", headers=HEADERS).status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    client.cookies.set("decider_session", cookie)
    assert client.get("/api/examples").status_code == 401


def test_expiry_checked_even_before_ttl_cleanup(client, auth_config):
    login(client)
    key = session_key(client.cookies.get("decider_session"))
    row = auth_config.get(key)
    row["expires_at"] = int(time.time()) - 1
    auth_config.put(row)
    assert client.get("/api/examples").status_code == 401


@pytest.mark.parametrize("change", ["reset", "disable"])
def test_account_changes_revoke_all_sessions(client, auth_config, change):
    login(client)
    if change == "reset":
        save_user(auth_config, "tester", "a-new-and-long-password", reset=True)
    else:
        user = auth_config.get("USER#tester")
        user["enabled"] = False
        auth_config.put(user)
    assert client.get("/api/examples").status_code == 401


def test_new_login_rotates_existing_session(client, auth_config):
    login(client)
    old = client.cookies.get("decider_session")
    login(client)
    assert old != client.cookies.get("decider_session")
    assert auth_config.get(session_key(old)) is None


@pytest.mark.parametrize("username", ["tester", "unknown"])
def test_wrong_password_and_unknown_user_have_same_error(client, username):
    response = client.post(
        "/api/auth/login",
        headers=HEADERS,
        json={
            "username": username,
            "password": "wrong-password",
        },
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "用户名或密码不正确"}
    assert not client.cookies


def test_username_normalization(client):
    response = client.post(
        "/api/auth/login",
        headers=HEADERS,
        json={
            **CREDS,
            "username": " TESTER ",
        },
    )
    assert response.json()["username"] == "tester"


def test_login_throttle_persists_across_instances(client):
    for _ in range(10):
        response = client.post(
            "/api/auth/login",
            headers=HEADERS,
            json={
                **CREDS,
                "password": "wrong-password",
            },
        )
        assert response.status_code == 401
    # A new ECS process shares the durable rate limit.
    app.state.auth = Auth()
    response = login(client)
    assert response.status_code == 429 and int(response.headers["retry-after"]) > 0


def test_concurrent_rate_increments_are_atomic(auth_config):
    with ThreadPoolExecutor(max_workers=8) as pool:
        counts = list(
            pool.map(
                lambda _: auth_config.increment("LOGIN#concurrent", int(time.time()) + 300),
                range(24),
            )
        )
    assert sorted(counts) == list(range(1, 25))


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-Decider-Client": "web", "Origin": "https://evil.example"},
        {"X-Decider-Client": "web", "Sec-Fetch-Site": "cross-site"},
    ],
)
def test_login_rejects_csrf(client, headers):
    assert client.post("/api/auth/login", json=CREDS, headers=headers).status_code == 403


def test_authenticated_mutation_requires_csrf_header(client):
    login(client)
    assert client.post("/api/guard", json={}).status_code == 403
    assert client.post("/api/auth/logout").status_code == 403
    assert client.get("/api/auth/me").status_code == 200


def test_storage_outage_fails_closed(client, monkeypatch):
    login(client)

    def fail(*args):
        raise RuntimeError("store unavailable")

    monkeypatch.setattr(app.state.auth.store, "get", fail)
    response = client.get("/api/examples")
    assert response.status_code == 503
    assert "store unavailable" not in response.text


def test_passwords_use_unique_salt_and_require_correct_password():
    first, second = hash_password(CREDS["password"]), hash_password(CREDS["password"])
    assert first != second and CREDS["password"] not in first
    assert verify_password(CREDS["password"], first)
    assert not verify_password("not-the-password", first)


def test_session_survives_another_process(client):
    login(client)
    app.state.auth = Auth()
    assert client.get("/api/auth/me").status_code == 200


def test_no_account_registration_or_overwrite(client, auth_config):
    assert client.post("/api/auth/register", json=CREDS).status_code == 401
    with pytest.raises(sqlite3.IntegrityError):
        save_user(auth_config, "tester", "another-long-password")
