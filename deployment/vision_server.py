"""Serve the pinned official vision engine, serialize GPU calls and warm it before readiness."""

import json
import threading
from pathlib import Path
from time import perf_counter

import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from strands_decider.infer import EngineConfig
from strands_decider.schema import SystemOneRequest
from strands_decider.vision import load_vision_engine

ROOT = Path(__file__).resolve().parent
MODEL = "strands-decider-2B-hobson-v19-vision"


def main():
    torch.set_num_threads(2)
    engine = load_vision_engine(
        "/opt/models/decider",
        EngineConfig(device="cuda", model_name=MODEL, strict_window=True, max_batch=8),
        attn_implementation="sdpa",
    )
    warmup = SystemOneRequest.model_validate_json((ROOT / "warmup.json").read_text())
    engine.evaluate(warmup)
    lock = threading.Lock()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    provenance = json.loads((ROOT / "provenance.json").read_text())

    @app.get("/health")
    def health():
        return {"status": "ok", "model": MODEL, "vision": True, "device": "cuda",
                "engine": "official-vision", "max_length": 4096,
                "upstream_commit": provenance["upstream_commit"]}

    @app.post("/v1/systemone")
    def evaluate(request: SystemOneRequest):
        if len(request.images) > 1 or any(len(s) > 2_800_000 for s in request.images):
            raise HTTPException(422, "One image, maximum 2 MB decoded")
        if not lock.acquire(timeout=3):
            raise HTTPException(429, "Vision service busy", headers={"Retry-After": "2"})
        try:
            started = perf_counter()
            response = engine.evaluate(request).model_dump()
            response["latency_ms"] = round((perf_counter() - started) * 1000, 3)
            return JSONResponse(response)
        except ValueError as exc:
            raise HTTPException(422, "Invalid image or context window exceeded") from exc
        finally:
            lock.release()

    uvicorn.run(app, host="0.0.0.0", port=18123, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
