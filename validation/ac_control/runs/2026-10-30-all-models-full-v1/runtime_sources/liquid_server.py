"""Pinned Liquid implementation; one CUDA call at a time, no CPU fallback."""

import argparse
import threading
import time

import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from transformers import AutoModel


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    torch.set_num_threads(2)
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA required")
    model = AutoModel.from_pretrained(
        args.model, trust_remote_code=True, dtype=torch.bfloat16, local_files_only=True,
    ).to("cuda").eval()
    warmup = {"action": {"type": "choice", "instructions": "Which mode is requested?",
                        "criteria": {"cool": "Cooling", "heat": "Heating"}}}
    for _ in range(3):
        model.system_one("The user requests cooling.", warmup)
        torch.cuda.synchronize()
    app = FastAPI()
    lock = threading.Lock()

    @app.get("/health")
    def health():
        return {"status": "ok", "model": "LiquidAI/d1-2B", "device": "cuda", "dtype": "BF16"}

    @app.post("/v1/systemone")
    def decide(payload: dict):
        with lock, torch.inference_mode():
            started = time.perf_counter()
            try:
                result = model.system_one(payload["state"], payload["questions"])
                torch.cuda.synchronize()
                result = dict(result.model_dump() if hasattr(result, "model_dump") else result)
                result.update(model="LiquidAI/d1-2B", latency_ms=(time.perf_counter() - started) * 1000)
                return result
            except (ValueError, KeyError, RuntimeError) as exc:
                raise HTTPException(422, "Liquid 无法处理这次请求") from exc

    uvicorn.run(app, host="127.0.0.1", port=18801, access_log=False)


if __name__ == "__main__":
    main()
