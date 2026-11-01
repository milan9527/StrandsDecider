"""Single-model, loopback Liquid LoRA service for the AC demo."""

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import torch

ROOT = Path("/opt/ac-liquid-lora")
MODEL = Path("/opt/ac-input-tests/models/liquid")
ADAPTER_SHA = "2a87384a624545021fc6ca91cf5406ed42e518a8607f048ca264048f57a0d171"
BASE_SHA = "b5e573687315e82ea80f4f7dd8d76b5cec3b6ee97e3509fd0493cfebb203719f"
WORKER_SHA = "0f07beab3c479327c6acba36b51ac585deb9ab0bc3dc5c0259d520f7b6cd9a9f"


def serve():
    import hashlib
    assert hashlib.sha256((ROOT / "worker.py").read_bytes()).hexdigest() == WORKER_SHA
    sys.path.insert(0, str(ROOT))
    from worker import Native, load_adapter, merge, sha
    adapter = ROOT / "training/adapter-1024.pt"
    assert sha(adapter) == ADAPTER_SHA
    assert sha(MODEL / "model.safetensors") == BASE_SHA
    native = Native(MODEL, lora=True)
    load_adapter(native.model, adapter)
    native.model.eval()
    merge(native.model)
    native.model.fuse_projections()
    metadata = {"ready": True, "model": "LiquidAI/d1-2B",
                "selected": {"sha256": ADAPTER_SHA}, "base_sha256": BASE_SHA,
                "deployment": "ac-lora-demo-v1", "precision": "BF16", "merged": True}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send_json(self, value, status=200):
            body = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self.send_json(metadata if self.path == "/health" else {"error": "Not found"},
                           200 if self.path == "/health" else 404)

        def do_POST(self):
            if self.path != "/lora":
                return self.send_json({"error": "Not found"}, 404)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 131072:
                    return self.send_json({"error": "Invalid request size"}, 413)
                payload = json.loads(self.rfile.read(length))
                result = native.infer(payload)
                torch.cuda.synchronize()
                self.send_json(result)
            except Exception as exc:
                self.send_json({"error": type(exc).__name__}, 500)

    HTTPServer(("127.0.0.1", 18821), Handler).serve_forever()


if __name__ == "__main__":
    serve()
