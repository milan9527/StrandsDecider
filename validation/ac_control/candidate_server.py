"""Serial loopback adapter around unchanged public Perplexity, Torchcast and Clef SDKs."""

import argparse
import hashlib
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


def main(args):
    import torch
    import transformers

    torch.set_num_threads(2)
    assert torch.cuda.is_available(), "CUDA required; no CPU fallback"
    path = args.model.resolve()
    manifest = json.loads((path / "manifest.json").read_text())
    sys.path.insert(0, str(path))
    metadata = {
        "provider": args.provider, "repository": manifest["model"], "revision": manifest["revision"],
        "gpu": torch.cuda.get_device_name(), "torch": torch.__version__,
        "cuda": torch.version.cuda, "transformers": transformers.__version__,
        "cpu_threads": 2, "external_concurrency": 1,
        "adapter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    cases = json.loads(args.cases.read_text())
    if args.provider == "pplx":
        sys.path.insert(0, str(path / "source/src"))
        from pplx_decider import Decider, FastOptions
        settings = FastOptions(buckets=(2048, 4096, 8192, 16384))
        model = Decider.from_pretrained(path, device="cuda", fast=settings, max_length=16384)
        lengths = [model.encoder.plan(case["payload"], 16384) for case in cases]
        metadata.update(runtime="official fast=True, BF16, CUDA graphs", buckets=list(settings.buckets),
                        max_encoded_tokens=max(chunk.length for plan in lengths for chunk in plan),
                        max_sequences_per_request=max(map(len, lengths)), input_truncated=False)
        evaluate = model.decide
        # Compiles the selected bounded buckets; excluded from HTTP benchmark timing.
        model.warmup()
    elif args.provider == "torchcast":
        from torchcast_decision.model import TorchcastDecision
        model = TorchcastDecision(str(path), device="cuda", images=False)
        # Conservative UTF-8 byte upper bound: native groups/finalists use subsets of these options.
        bound = max(len(case["payload"]["state"].encode())
                    + len(json.dumps(spec, ensure_ascii=False).encode()) + 1024
                    for case in cases for spec in case["payload"]["questions"].values())
        assert bound < 16384, "Preflight cannot guarantee untruncated native prompts"
        metadata.update(runtime="official noncausal BF16 with CUDA graphs; images=False",
                        cuda_graphs=len(model.graphs), fast_kernels=model.fast_kernels,
                        prompt_token_upper_bound=bound, input_truncated=False,
                        native_option_grouping={"threshold": 26, "group": model.group, "keep": model.keep})

        def evaluate(request):
            answers, usage = model.decide(request["state"], request["questions"])
            return {"answers": answers, "usage": usage}
    else:
        from joint_schema_model import encode_record, load_release_model, systemone
        model, processor = load_release_model(path, device="cuda")
        lengths = [len(encode_record(processor.tokenizer, case["payload"],
                                    processor=processor, max_length=1_000_000).input_ids)
                   for case in cases]
        assert max(lengths) <= 16384, "Native Clef would truncate the state"
        metadata.update(runtime="official Clef joint schema head, BF16",
                        max_encoded_tokens=max(lengths), input_truncated=False)

        def evaluate(request):
            with torch.inference_mode():
                return systemone(model, processor, request)

    torch.cuda.synchronize()
    metadata["gpu_allocated_after_load"] = torch.cuda.memory_allocated()
    args.metadata.parent.mkdir(parents=True, exist_ok=True)
    args.metadata.write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps({"ready": True, **metadata}), flush=True)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *unused):
            pass

        def respond(self, status, value):
            body = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self.respond(200, {"ok": True, "model": manifest["model"], **metadata})

        def do_POST(self):
            try:
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                started = time.perf_counter()
                with torch.inference_mode():
                    response = dict(evaluate(request))
                torch.cuda.synchronize()
                response.setdefault("model", manifest["model"])
                response["benchmark_timing"] = {
                    "sdk_call_ms": (time.perf_counter() - started) * 1000,
                    "gpu_peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                }
                self.respond(200, response)
            except torch.cuda.OutOfMemoryError as error:
                self.respond(503, {"error": type(error).__name__, "detail": str(error)})
            except Exception as error:
                self.respond(422, {"error": type(error).__name__, "detail": str(error)})

    HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("pplx", "torchcast", "clef"), required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18811)
    main(parser.parse_args())
