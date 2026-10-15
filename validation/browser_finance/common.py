"""Bounded real model calls. No model-selected financial action is executed."""

import asyncio
import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import httpx


def stamp():
    return datetime.now(UTC).isoformat()


def wire(value):
    # Preserve candidate insertion order: order reversals must have distinct hashes.
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(wire(value).encode()).hexdigest()


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def validate(reply, payload, provider):
    assert isinstance(reply, dict)
    assert isinstance(reply.get("model"), str)
    if provider == "decider":
        assert "decider" in reply["model"].lower() and reply.get("source") == "live"
    else:
        assert reply["model"].startswith("jev-")
    assert set(reply["answers"]) == {"decision"}
    answer = reply["answers"]["decision"]
    assert answer["type"] == "choice"
    options = payload["questions"]["decision"]["criteria"]
    probs = answer["probabilities"]
    assert set(probs) == set(options) and answer["choice"] in options
    for value in [*probs.values(), answer["confidence"]]:
        assert type(value) in (float, int) and math.isfinite(value) and 0 <= value <= 1
    assert abs(sum(probs.values()) - 1) < 0.02
    assert probs[answer["choice"]] + 1e-5 >= max(probs.values())
    return answer["choice"]


class Models:
    def __init__(self, gateway, credentials, jev_key, max_calls):
        self.gateway = gateway.rstrip("/")
        self.credentials = credentials
        self.jev_key = jev_key
        self.max_calls = max_calls
        self.calls = 0
        self.locks = {provider: asyncio.Lock() for provider in ("jev", "decider")}
        self.clients = {}

    async def __aenter__(self):
        self.clients = {
            "decider": httpx.AsyncClient(
                base_url=self.gateway,
                headers={"X-Decider-Client": "web"},
                timeout=httpx.Timeout(55, connect=6),
                follow_redirects=False,
                trust_env=False,
            ),
            "jev": httpx.AsyncClient(
                base_url="https://api.typesafe.ai",
                headers={"Authorization": "Bearer " + Path(self.jev_key).read_text().strip()},
                timeout=httpx.Timeout(55, connect=6),
                follow_redirects=False,
                trust_env=False,
            ),
        }
        r = await self.clients["decider"].post(
            "/api/auth/login", json=json.loads(Path(self.credentials).read_text())
        )
        r.raise_for_status()
        r = await self.clients["decider"].get("/api/health")
        r.raise_for_status()
        self.health = r.json()
        if not self.health.get("connected"):
            raise RuntimeError("Existing Decider is not ready; no GPU state changed")
        return self

    async def __aexit__(self, *unused):
        try:
            await self.clients["decider"].post("/api/auth/logout", json={})
        finally:
            for client in self.clients.values():
                await client.aclose()

    async def decide(self, provider, payload):
        assert len(payload["state"]) <= 12000
        assert 2 <= len(payload["questions"]["decision"]["criteria"]) <= 12
        async with self.locks[provider]:
            if self.calls >= self.max_calls:
                raise RuntimeError("Frozen model call budget exhausted")
            self.calls += 1
            record = {
                "provider": provider,
                "started_at": stamp(),
                "input": payload,
                "input_sha256": digest(payload),
                "attempt": 1,
                "retry": False,
            }
            start = perf_counter()
            try:
                path = "/api/decide" if provider == "decider" else "/v1/systemone"
                body = {
                    **payload,
                    **({"mode": "live"} if provider == "decider" else {"model": "jev-latest"}),
                }
                r = await self.clients[provider].post(path, json=body)
                r.raise_for_status()
                data = r.json()
                selected = validate(data, payload, provider)
                record.update(status="ok", choice=selected, response=data, model=data["model"])
            except Exception as exc:
                record.update(status="error", error_type=type(exc).__name__)
                if isinstance(exc, httpx.HTTPStatusError):
                    record["http_status"] = exc.response.status_code
            record["elapsed_ms"] = round((perf_counter() - start) * 1000, 3)
            return record
