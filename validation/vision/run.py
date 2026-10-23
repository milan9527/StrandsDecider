"""Exercise the official vision HTTP server and retain every actual request/response."""

import base64
import copy
import hashlib
import importlib.metadata
import json
import random
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results"
URL = "http://127.0.0.1:18123"


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def request(method, path, payload=None):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(URL + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as response:
        return response.status, json.load(response)


def gpu():
    return subprocess.check_output(
        ["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu",
         "--format=csv,noheader"], text=True,
    ).strip()


def main():
    OUT.mkdir(exist_ok=True)
    manifest = json.loads((ROOT / "cases.json").read_text())
    for case in manifest["cases"]:
        assert hashlib.sha256((ROOT / case["image"]).read_bytes()).hexdigest() == case["sha256"]
    assert len(manifest["cases"]) == 12
    checkpoint = Path("/opt/models/decider")
    immutable = [checkpoint / "head.safetensors", checkpoint / "lora/adapter_model.safetensors"]
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in immutable}
    metadata = {
        "started_at": datetime.now(UTC).isoformat(), "gpu_before": gpu(),
        "python": sys.version, "packages": {p: importlib.metadata.version(p)
            for p in ("torch", "transformers", "peft", "pillow")},
        "checkpoint_hashes": hashes,
        "config": json.loads((checkpoint / "hobson_config.json").read_text()),
        "source": json.loads((ROOT / "sources/upstream.json").read_text()),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "cases_sha256": hashlib.sha256((ROOT / "cases.json").read_bytes()).hexdigest(),
        "transport": "Loopback HTTP, concurrency 1; co-resident existing services retained.",
    }
    save("environment.json", metadata)
    launch = (
        "import torch,uvicorn;"
        "torch.set_num_threads(2);"
        "from strands_decider.server import create_app;"
        "app=create_app('/opt/models/decider',device='cuda',vision=True,strict_window=True,"
        "model_name='strands-decider-2B-hobson-v19-vision',max_batch=8,"
        "attn_implementation='sdpa');"
        "uvicorn.run(app,host='127.0.0.1',port=18123,log_level='warning')"
    )
    with (OUT / "server.log").open("w") as log:
        server = subprocess.Popen([sys.executable, "-u", "-c", launch], stdout=log, stderr=log)
        try:
            load_start = time.perf_counter()
            while True:
                if server.poll() is not None:
                    raise RuntimeError("Vision server exited during startup; see server.log")
                try:
                    _, health = request("GET", "/health")
                    break
                except (urllib.error.URLError, TimeoutError):
                    if time.perf_counter() - load_start > 600:
                        raise TimeoutError("Vision model readiness exceeded ten minutes") from None
                    time.sleep(2)
            assert health["vision"] is True and health["device"] == "cuda"
            metadata["model_load_seconds"] = time.perf_counter() - load_start
            metadata["gpu_loaded"] = gpu()
            save("health.json", health)
            save("environment.json", metadata)
            print(json.dumps({"event": "ready", "health": health, "gpu": metadata["gpu_loaded"]}), flush=True)

            def execute(case, stage, repetition):
                payload = copy.deepcopy(case["request"])
                if stage != "no_image":
                    image = ROOT / ("images/blank.png" if stage == "blank" else case["image"])
                    payload["images"] = [base64.b64encode(image.read_bytes()).decode()]
                if stage == "reverse":
                    for question in payload["questions"].values():
                        if question["type"] == "choice":
                            question["criteria"] = dict(reversed(list(question["criteria"].items())))
                entry = {
                    "case": case["id"], "stage": stage, "repetition": repetition,
                    "started_at": datetime.now(UTC).isoformat(), "request": payload,
                }
                started = time.perf_counter()
                try:
                    status, response = request("POST", "/v1/systemone", payload)
                    entry.update(http_status=status, response=response)
                except urllib.error.HTTPError as exc:
                    entry.update(http_status=exc.code, error=exc.read().decode())
                except Exception as exc:
                    entry.update(error=f"{type(exc).__name__}: {exc}")
                entry["client_ms"] = (time.perf_counter() - started) * 1000
                with (OUT / "receipts.jsonl").open("a") as stream:
                    stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
                print(json.dumps({
                    "case": case["id"], "stage": stage, "repetition": repetition,
                    "ms": round(entry["client_ms"], 1), "status": entry.get("http_status"),
                    "answers": entry.get("response", {}).get("answers", {}), "error": entry.get("error"),
                }, ensure_ascii=False), flush=True)

            for i in range(manifest["plan"]["warmups"]):
                execute(manifest["cases"][i * 4], "warmup", i)
            for stage, repetitions in [("image", 3), ("reverse", 1), ("no_image", 1), ("blank", 1)]:
                for repetition in range(repetitions):
                    cases = list(manifest["cases"])
                    random.Random(20261023 + repetition).shuffle(cases)
                    for case in cases:
                        execute(case, stage, repetition)
            metadata["completed_at"] = datetime.now(UTC).isoformat()
            metadata["gpu_finished"] = gpu()
            assert hashes == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in immutable}
            save("environment.json", metadata)
        finally:
            server.terminate()
            try:
                server.wait(timeout=30)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=10)


if __name__ == "__main__":
    main()
