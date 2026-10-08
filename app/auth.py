"""Self-managed passwords and revocable sessions; DynamoDB in AWS, SQLite locally."""

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import threading
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)
SESSION_SECONDS = 8 * 60 * 60
LOGIN_WINDOW = 5 * 60
LOGIN_LIMIT = 10


def canonical_username(value):
    value = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9_.-]{3,32}", value):
        raise ValueError("用户名须为 3–32 位字母、数字、点、下划线或连字符")
    return value


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(
        password.encode(),
        salt=bytes.fromhex(salt),
        n=32768,
        r=8,
        p=1,
        maxmem=64 * 1024 * 1024,
        dklen=32,
    )
    return f"scrypt${salt}${digest.hex()}"


def verify_password(password, encoded):
    scheme, salt, _ = encoded.split("$")
    return scheme == "scrypt" and hmac.compare_digest(hash_password(password, salt), encoded)


class SQLiteStore:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS auth (pk TEXT PRIMARY KEY, data TEXT NOT NULL)")
        path.chmod(0o600)

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def get(self, key):
        with self.connect() as db:
            row = db.execute("SELECT data FROM auth WHERE pk=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, item, *, create=False):
        with self.connect() as db:
            query = "INSERT INTO" if create else "INSERT OR REPLACE INTO"
            db.execute(f"{query} auth VALUES (?, ?)", (item["pk"], json.dumps(item)))

    def delete(self, key):
        with self.connect() as db:
            db.execute("DELETE FROM auth WHERE pk=?", (key,))

    def increment(self, key, expires):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # Local equivalent of DynamoDB TTL cleanup.
            db.execute(
                "DELETE FROM auth WHERE json_extract(data, '$.expires_at') <= ?",
                (int(time.time()),),
            )
            row = db.execute("SELECT data FROM auth WHERE pk=?", (key,)).fetchone()
            count = json.loads(row[0])["attempts"] + 1 if row else 1
            item = {"pk": key, "attempts": count, "expires_at": expires}
            db.execute("INSERT OR REPLACE INTO auth VALUES (?, ?)", (key, json.dumps(item)))
            return count


class DynamoStore:
    def __init__(self, name, region=None):
        import boto3
        from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
        from botocore.config import Config

        self.client = boto3.client(
            "dynamodb",
            region_name=region,
            config=Config(connect_timeout=3, read_timeout=3, retries={"max_attempts": 2}),
        )
        self.name = name
        self.serializer = TypeSerializer()
        self.deserializer = TypeDeserializer()

    def encode(self, item):
        return {key: self.serializer.serialize(value) for key, value in item.items()}

    def get(self, key):
        item = self.client.get_item(
            TableName=self.name, Key=self.encode({"pk": key}), ConsistentRead=True
        ).get("Item")
        return (
            {key: self.deserializer.deserialize(value) for key, value in item.items()}
            if item
            else None
        )

    def put(self, item, *, create=False):
        options = {"ConditionExpression": "attribute_not_exists(pk)"} if create else {}
        self.client.put_item(TableName=self.name, Item=self.encode(item), **options)

    def delete(self, key):
        self.client.delete_item(TableName=self.name, Key=self.encode({"pk": key}))

    def increment(self, key, expires):
        result = self.client.update_item(
            TableName=self.name,
            Key=self.encode({"pk": key}),
            UpdateExpression="SET expires_at = :expiry ADD attempts :one",
            ExpressionAttributeValues=self.encode({":expiry": expires, ":one": 1}),
            ReturnValues="UPDATED_NEW",
        )
        return int(result["Attributes"]["attempts"]["N"])


def configured_store():
    if table := os.getenv("AUTH_TABLE"):
        return DynamoStore(table, os.getenv("AWS_REGION"))
    return SQLiteStore(os.getenv("AUTH_DB_PATH", ".data/auth.sqlite3"))


def save_user(store, username, password, *, reset=False):
    username = canonical_username(username)
    if not 12 <= len(password) <= 128:
        raise ValueError("密码长度须为 12–128 个字符")
    store.put(
        {
            "pk": "USER#" + username,
            "username": username,
            "password_hash": hash_password(password),
            "version": secrets.token_hex(16),
            "enabled": True,
        },
        create=not reset,
    )
    return username


def session_key(token):
    return "SESSION#" + hashlib.sha256(token.encode()).hexdigest()


class Auth:
    def __init__(self):
        self.store = configured_store()
        self.secure = os.getenv("AUTH_COOKIE_SECURE", "true").lower() == "true"
        self.cookie = "__Host-decider_session" if self.secure else "decider_session"
        self.origin = os.getenv("AUTH_ORIGIN", "").rstrip("/")
        if os.getenv("AUTH_TABLE") and (not self.secure or not self.origin):
            raise RuntimeError("AWS authentication requires secure cookies and AUTH_ORIGIN")
        self.dummy_hash = hash_password(secrets.token_urlsafe(32))
        # Bound simultaneous memory-intensive password checks in this API container.
        self.hash_slots = threading.BoundedSemaphore(2)

    def identity(self, token):
        if not token or len(token) > 128:
            return None
        session = self.store.get(session_key(token))
        if not session or int(session["expires_at"]) <= int(time.time()):
            return None
        user = self.store.get("USER#" + session["username"])
        if not user or not user["enabled"] or user["version"] != session["version"]:
            return None
        return {"username": user["username"], "expires_at": int(session["expires_at"])}

    def login(self, username, password, old_token):
        try:
            username = canonical_username(username)
        except ValueError:
            raise HTTPException(401, "用户名或密码不正确") from None
        now = int(time.time())
        bucket = now // LOGIN_WINDOW
        attempts = self.store.increment(f"LOGIN#{username}#{bucket}", (bucket + 2) * LOGIN_WINDOW)
        if attempts > LOGIN_LIMIT:
            raise HTTPException(
                429,
                "登录尝试过于频繁，请稍后重试",
                headers={"Retry-After": str((bucket + 1) * LOGIN_WINDOW - now)},
            )
        if not self.hash_slots.acquire(blocking=False):
            raise HTTPException(429, "登录服务繁忙，请稍后重试", headers={"Retry-After": "3"})
        try:
            user = self.store.get("USER#" + username)
            valid = verify_password(password, user["password_hash"] if user else self.dummy_hash)
        finally:
            self.hash_slots.release()
        if not valid or not user or not user["enabled"]:
            raise HTTPException(401, "用户名或密码不正确")
        token = secrets.token_urlsafe(32)
        expires = now + SESSION_SECONDS
        self.store.put(
            {
                "pk": session_key(token),
                "username": username,
                "version": user["version"],
                "expires_at": expires,
            }
        )
        if old_token and len(old_token) <= 128:
            self.store.delete(session_key(old_token))
        return token, {"username": username, "expires_at": expires}

    def check_csrf(self, request):
        # Custom headers require a preflight from foreign origins; no CORS is enabled.
        if request.headers.get("x-decider-client") != "web":
            raise HTTPException(403, "请求校验失败，请刷新页面后重试")
        expected = self.origin or str(request.base_url).rstrip("/")
        if origin := request.headers.get("origin"):
            if origin != expected:
                raise HTTPException(403, "不允许此来源的请求")
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "不允许跨站请求")

    async def middleware(self, request, call_next):
        if not request.url.path.startswith("/api"):
            return await call_next(request)
        public = request.url.path in ("/api/live", "/api/ready", "/api/auth/login")
        try:
            if not public:
                identity = await run_in_threadpool(self.identity, request.cookies.get(self.cookie))
                if identity is None:
                    raise HTTPException(401, "请先登录，或重新登录以恢复会话")
                request.state.user = identity
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                self.check_csrf(request)
        except HTTPException as exc:
            response = JSONResponse({"detail": exc.detail}, exc.status_code, headers=exc.headers)
        except Exception:
            logger.exception("Authentication storage unavailable")
            response = JSONResponse({"detail": "登录服务暂时不可用，请稍后重试"}, 503)
        else:
            response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response


router = APIRouter(prefix="/api/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response):
    auth = request.app.state.auth
    try:
        token, user = auth.login(body.username, body.password, request.cookies.get(auth.cookie))
    except HTTPException:
        raise
    except Exception:
        logger.exception("Authentication storage unavailable during login")
        raise HTTPException(503, "登录服务暂时不可用，请稍后重试") from None
    response.set_cookie(
        auth.cookie,
        token,
        max_age=SESSION_SECONDS,
        secure=auth.secure,
        httponly=True,
        samesite="strict",
        path="/",
    )
    return user


@router.get("/me")
def me(request: Request):
    return request.state.user


@router.post("/logout")
def logout(request: Request, response: Response):
    auth = request.app.state.auth
    try:
        auth.store.delete(session_key(request.cookies[auth.cookie]))
    except Exception:
        logger.exception("Authentication storage unavailable during logout")
        raise HTTPException(503, "退出失败，请稍后重试") from None
    response.delete_cookie(
        auth.cookie, secure=auth.secure, httponly=True, samesite="strict", path="/"
    )
    return {"ok": True}
