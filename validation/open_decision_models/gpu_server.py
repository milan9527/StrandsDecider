"""Thin loopback-only wrappers around official CUDA implementations."""
import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["liquid", "pplx", "knowline", "decider"], required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--port", type=int, default=18801)
    args = parser.parse_args()
    import torch
    from fastapi import FastAPI, HTTPException
    import uvicorn
    torch.set_num_threads(2)
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA required; CPU fallback is disabled")
    if args.provider == "liquid":
        from transformers import AutoModel
        model = AutoModel.from_pretrained(
            args.model_path, trust_remote_code=True, dtype=torch.bfloat16,
            local_files_only=True).to("cuda").eval()
        evaluate = lambda payload: model.system_one(payload["state"], payload["questions"])
    elif args.provider == "pplx":
        sys.path.insert(0, str(Path(args.model_path) / "source/src"))
        from pplx_decider import Decider
        model = Decider.from_pretrained(args.model_path, device="cuda", fast=False)
        evaluate = model.decide
    elif args.provider == "knowline":
        sys.path.insert(0, args.model_path)
        from transformers import AutoTokenizer
        from knowline_server import HF, KnowLine
        from knowline_layout import Layout
        backend = HF(args.model_path, device="cuda")
        model = KnowLine(AutoTokenizer.from_pretrained(args.model_path), backend,
                        temperature=1.0, workers=1, layout=Layout(read_twice=True, twice_max_tokens=3000))
        def evaluate(payload):
            answers, usage = model.run(payload["state"], payload["questions"])
            return {"answers": answers, "usage": usage}
    else:
        from strands_decider.infer import EngineConfig, SystemOneEngine
        from strands_decider.modeling import StrandsDeciderModel
        from strands_decider.schema import SystemOneRequest
        model = SystemOneEngine(StrandsDeciderModel.load(args.model_path),
                                EngineConfig(device="cuda", max_batch=8, strict_window=True,
                                             model_name="strands-decider-2B-hobson-v19"))
        evaluate = lambda payload: model.evaluate(SystemOneRequest(**payload)).model_dump()
    metadata = {"provider": args.provider, "gpu": torch.cuda.get_device_name(),
                "torch": torch.__version__, "cuda": torch.version.cuda,
                "engine": "official CUDA reference implementation", "cpu_threads": 2,
                "serial_gpu_execution": True}
    Path("/bench/environment-" + args.provider + ".json").write_text(json.dumps(metadata, indent=2))
    warmup = {"state": "The user explicitly requests cooling mode.",
              "questions": {"action": {"type": "choice", "instructions": "Which mode is requested?",
                                      "criteria": {"cool": "Cooling", "heat": "Heating"}}}}
    for _ in range(3):
        evaluate(warmup)
        torch.cuda.synchronize()
    lock = threading.Lock()
    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "ok", **metadata}

    @app.post("/v1/systemone")
    def infer(payload: dict):
        start = time.perf_counter()
        with lock:
            entered = time.perf_counter()
            try:
                data = evaluate(payload)
                torch.cuda.synchronize()
                if hasattr(data, "model_dump"):
                    data = data.model_dump()
                data = dict(data)
                data.setdefault("model", args.provider)
                data["benchmark_timing"] = {
                    "queue_ms": (entered - start) * 1000,
                    "inference_ms": (time.perf_counter() - entered) * 1000}
                data["latency_ms"] = (time.perf_counter() - start) * 1000
                return data
            except Exception as exc:
                raise HTTPException(422, f"{type(exc).__name__}: {exc}") from exc

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
