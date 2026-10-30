"""Run unchanged frozen AC requests against resident services from the GPU host."""

import argparse
import hashlib
import json
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

MODELS = {
    "liquid": {"id": "LiquidAI/d1-2B", "url": "http://127.0.0.1:18801"},
    "h2o": {"id": "h2oai/h2o-lightning-4b", "url": "http://127.0.0.1:18803"},
}


def wire(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def sha(value):
    return hashlib.sha256(wire(value).encode()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def stamp():
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017 - GPU host Python 3.9


def call(url, payload=None):
    body = wire(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"},
    )
    started = time.perf_counter()
    try:
        try:
            response = urllib.request.urlopen(request, timeout=120)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            text = response.read().decode()
            result = {
                "http_status": response.code, "response_text": text,
                "request_id": response.headers.get("x-request-id"),
                "status": "ok" if response.code == 200 else "http_error",
            }
            try:
                result["response"] = json.loads(text)
            except ValueError:
                result["status"] = "format_error"
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        result = {"status": "transport_error", "error": str(error)}
    result["client_ms"] = round((time.perf_counter() - started) * 1000, 3)
    return result


def snapshot(output, phase):
    result = {"observed_at": stamp()}
    for name, command in [
        ("gpu", ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,utilization.gpu",
                 "--format=csv,noheader"]),
        ("services", ["systemctl", "show", "decider-vllm", "decider-liquid", "decider-h2o",
                      "decider-comparison-gateway",
                      "--property=Id,ActiveState,SubState,NRestarts,ExecMainStartTimestamp"]),
    ]:
        process = subprocess.run(command, capture_output=True, text=True, timeout=15)
        result[name] = {
            "returncode": process.returncode, "stdout": process.stdout, "stderr": process.stderr,
        }
    save(output / f"{phase}_environment.json", result)


def run(args):
    requests = json.loads(args.requests.read_text())
    plan = json.loads(args.plan.read_text())
    if sha(requests) != plan["requests_sha256"]:
        raise ValueError("Frozen request collection hash mismatch")
    for request in requests:
        if sha(request["payload"]) != request["input_sha256"]:
            raise ValueError("Frozen individual request hash mismatch")
    if args.phase == "probe":
        requests = requests[:1]
    args.output.mkdir(parents=True, exist_ok=True)
    snapshot(args.output, args.phase + "_before")
    for provider in args.providers:
        model = MODELS[provider]
        output = args.output / provider
        output.mkdir(exist_ok=True)
        metadata = {
            "provider": provider, "model": model["id"], "endpoint": model["url"],
            "phase": args.phase, "started_at": stamp(), "status": "running",
            "requests_sha256": plan["requests_sha256"], "planned_calls": len(requests),
            "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "automatic_retries": 0, "concurrency": 1,
            "transport": "GPU host loopback; unchanged 30-question payload",
        }
        before = call(model["url"] + "/health")
        save(output / f"{args.phase}_health_before.json", before)
        health = before.get("response", {})
        if before["status"] != "ok" or health.get("model") != model["id"]:
            raise RuntimeError(f"{provider}: unexpected model or failed health")
        if not (health.get("status") == "ok" or health.get("ok") is True):
            raise RuntimeError(f"{provider}: model is not ready")
        save(output / f"{args.phase}_run.json", metadata)
        actual_calls = 0
        with (output / f"{args.phase}_receipts.jsonl").open("x") as stream:
            try:
                for request in requests:
                    receipt = {
                        "case_id": request["case_id"], "variant": request["variant"],
                        "provider": provider, "input_sha256": request["input_sha256"],
                        "started_at": stamp(),
                    }
                    receipt.update(call(model["url"] + "/v1/systemone", request["payload"]))
                    actual_calls += 1
                    stream.write(wire(receipt) + "\n")
                    stream.flush()
                    response = receipt.get("response", {})
                    print(wire({
                        "provider": provider, "phase": args.phase, "completed": actual_calls,
                        "case": request["case_id"], "variant": request["variant"],
                        "status": receipt["status"], "client_ms": receipt["client_ms"],
                        "server_ms": response.get("latency_ms", response.get("usage", {}).get("latency_ms")),
                        "answers": len(response.get("answers", {})),
                    }), flush=True)
                metadata.update(status="complete", finished_at=stamp())
            finally:
                metadata["actual_calls"] = actual_calls
                save(output / f"{args.phase}_run.json", metadata)
        save(output / f"{args.phase}_health_after.json", call(model["url"] + "/health"))
    snapshot(args.output, args.phase + "_after")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", choices=["probe", "formal"], required=True)
    parser.add_argument("--providers", nargs="+", choices=list(MODELS), default=list(MODELS))
    run(parser.parse_args())
