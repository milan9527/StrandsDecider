"""Authenticated private bridge to the pinned, merged Liquid LoRA evaluation service."""

import asyncio
import hmac
import os
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request

ADAPTER = "2a87384a624545021fc6ca91cf5406ed42e518a8607f048ca264048f57a0d171"
UPSTREAM = "http://127.0.0.1:18821"


@asynccontextmanager
async def lifespan(app):
    if not os.getenv("AC_LORA_TOKEN"):
        raise RuntimeError("AC_LORA_TOKEN is required")
    app.state.client = httpx.AsyncClient(trust_env=False, timeout=120)
    app.state.slot = asyncio.Lock()
    try:
        yield
    finally:
        await app.state.client.aclose()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def auth(request, call_next):
    wanted = "Bearer " + os.getenv("AC_LORA_TOKEN", "")
    if not hmac.compare_digest(request.headers.get("authorization", ""), wanted):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)


async def identity(request):
    response = await request.app.state.client.get(UPSTREAM + "/health")
    response.raise_for_status()
    metadata = response.json()
    if metadata.get("selected", {}).get("sha256") != ADAPTER or not metadata.get("ready"):
        raise ValueError("Unexpected Liquid adapter")
    return {"ready": True, "model": "LiquidAI/d1-2B", "adapter_sha256": ADAPTER}


@app.get("/health")
async def health(request: Request):
    try:
        return await identity(request)
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(503, "Liquid LoRA unavailable") from exc


@app.post("/v1/systemone")
async def decide(payload: dict, request: Request):
    if (set(payload) != {"state", "questions"} or not isinstance(payload["state"], str)
            or len(payload["state"]) > 32768 or not isinstance(payload["questions"], dict)
            or not 1 <= len(payload["questions"]) <= 30):
        raise HTTPException(422, "Invalid AC request")
    for question in payload["questions"].values():
        if (not isinstance(question, dict) or question.get("type") != "choice"
                or not isinstance(question.get("criteria"), dict)
                or not 2 <= len(question["criteria"]) <= 102
                or any(not isinstance(v, str) for v in question["criteria"].values())):
            raise HTTPException(422, "Invalid AC choices")
    try:
        async with request.app.state.slot:
            metadata = await identity(request)
            response = await request.app.state.client.post(UPSTREAM + "/lora", json=payload)
            response.raise_for_status()
            return {**response.json(), **metadata}
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(503, "Liquid LoRA request failed; no fallback") from exc


if __name__ == "__main__":
    uvicorn.run(app, host=os.getenv("AC_LORA_BIND", "127.0.0.1"), port=18125, access_log=False)
