import pytest

from app.auth import SQLiteStore, hash_password

PASSWORD = "test-password-with-entropy"


@pytest.fixture(scope="session")
def password_hash():
    return hash_password(PASSWORD)


@pytest.fixture(autouse=True)
def auth_config(tmp_path, monkeypatch, password_hash):
    monkeypatch.delenv("AUTH_TABLE", raising=False)
    monkeypatch.delenv("AUTH_ORIGIN", raising=False)
    monkeypatch.delenv("GPU_STATE_TABLE", raising=False)
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    monkeypatch.setenv("AUTH_DB_PATH", str(tmp_path / "auth.sqlite3"))
    store = SQLiteStore(tmp_path / "auth.sqlite3")
    store.put(
        {
            "pk": "USER#tester",
            "username": "tester",
            "password_hash": password_hash,
            "enabled": True,
            "version": "test-version",
        }
    )
    return store
