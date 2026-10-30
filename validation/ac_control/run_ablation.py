"""Portable, answer-free runner for the three existing GPU services."""

import argparse
import hashlib
import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from ablation_protocol import selected_payload
from run_resident import save, sha, snapshot, stamp, wire

MODELS = {
    "decider": {"id": "strands-decider-2B-hobson-v19-vllm", "url": "http://127.0.0.1:8100"},
    "liquid": {"id": "LiquidAI/d1-2B", "url": "http://127.0.0.1:18801"},
    "h2o": {"id": "h2oai/h2o-lightning-4b", "url": "http://127.0.0.1:18803"},
}


def choices(response, payload, model):
    if response.get("model") != model:
        raise ValueError("Unexpected model identity")
    answers = response.get("answers")
    if not isinstance(answers, dict) or set(answers) != set(payload["questions"]):
        raise ValueError("Expected exactly the supplied question IDs")
    result = {}
    for key, question in payload["questions"].items():
        answer = answers[key]
        if not isinstance(answer, dict) or answer.get("type") != "choice":
            raise ValueError("Expected typed choice")
        value = answer.get("choice")
        if not isinstance(value, str) or value not in question["criteria"]:
            raise ValueError("Invalid candidate")
        result[key] = value
    return result


def call(url, payload, headers):
    request = urllib.request.Request(
        url, data=wire(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json", **headers},
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


def observe(experiment, provider, headers):
    model = MODELS[provider]
    row = {k: experiment[k] for k in ("case_id", "dataset", "arm", "variant")}
    row.update(provider=provider, started_at=stamp(), stages=[], status="ok")
    payload = experiment["first_payload"]
    while payload is not None:
        stage = {
            "stage": "gate" if experiment["arm"] == "two_stage" and not row["stages"] else "value",
            "payload": payload, "input_sha256": sha(payload),
            **call(model["url"] + "/v1/systemone", payload, headers),
        }
        row["stages"].append(stage)
        try:
            if stage["status"] != "ok":
                row["status"] = stage["status"]
                break
            selected = choices(stage["response"], payload, model["id"])
            stage["choices"] = selected
        except (ValueError, TypeError, AttributeError) as error:
            stage.update(status="format_error", error=str(error))
            row["status"] = stage["status"]
            break
        if stage["stage"] == "gate":
            row["gate_selected_keys"] = [k for k, v in selected.items() if v == "apply"]
            payload = selected_payload(experiment["value_payload"], selected)
        else:
            payload = None
    row["client_ms"] = sum(s["client_ms"] for s in row["stages"])
    latencies = [
        s.get("response", {}).get("latency_ms",
                                s.get("response", {}).get("usage", {}).get("latency_ms"))
        for s in row["stages"]
    ]
    row["server_ms"] = sum(latencies) if all(isinstance(v, (int, float)) for v in latencies) else None
    return row


def publish(output, uri):
    if uri:
        process = subprocess.run(
            ["aws", "s3", "sync", str(output), uri, "--only-show-errors"],
            capture_output=True, text=True, timeout=90,
        )
        if process.returncode:
            raise RuntimeError("Evidence upload failed: " + process.stderr)


def run(args):
    experiments = json.loads(args.experiments.read_text())
    plan = json.loads(args.plan.read_text())
    if sha(experiments) != plan["experiments_sha256"]:
        raise ValueError("Frozen experiments changed")
    for row in experiments:
        if sha(row["first_payload"]) != row["first_sha256"]:
            raise ValueError("First payload changed")
        if row["value_payload"] is not None and sha(row["value_payload"]) != row["value_sha256"]:
            raise ValueError("Value payload changed")
    for name in ("run_ablation.py", "ablation_protocol.py", "run_resident.py"):
        if hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() != plan["source_sha256"][name]:
            raise ValueError("Runner source changed: " + name)
    experiments = [e for e in experiments if not e["reuse_baseline"]]
    if args.phase == "probe":
        # Largest numeric candidate set is always present, regardless of query.
        experiments = [e for e in experiments if e["case_id"] == "S01" and e["variant"] == "original"]
    for provider in args.providers:
        if (args.output / provider / (args.phase + "_receipts.jsonl")).exists():
            raise FileExistsError("Refusing to overwrite an existing run")
    args.output.mkdir(parents=True, exist_ok=True)
    snapshot(args.output, args.phase + "_before")
    headers = {}
    if "decider" in args.providers:
        secret = subprocess.run(
            ["aws", "secretsmanager", "get-secret-value", "--secret-id", args.secret_arn,
             "--query", "SecretString", "--output", "text"],
            capture_output=True, text=True, timeout=30, check=True,
        )
        headers["decider"] = {"Authorization": "Bearer " + json.loads(secret.stdout)["api_key"]}
    progress = {"phase": args.phase, "started_at": stamp(), "models": {}, "status": "running"}
    for provider in args.providers:
        model = MODELS[provider]
        output = args.output / provider
        output.mkdir(exist_ok=True)
        before = call(model["url"] + "/health", None, headers.get(provider, {}))
        save(output / (args.phase + "_health_before.json"), before)
        health = before.get("response", {})
        if before["status"] != "ok" or health.get("model") != model["id"]:
            raise RuntimeError(provider + ": failed health or model identity")
        metadata = {
            "provider": provider, "model": model["id"], "endpoint": model["url"],
            "phase": args.phase, "started_at": stamp(), "status": "running",
            "experiments_sha256": plan["experiments_sha256"],
            "planned_observations": len(experiments), "actual_observations": 0,
            "actual_calls": 0, "automatic_retries": 0, "concurrency": 1,
        }
        progress["models"][provider] = metadata
        save(output / (args.phase + "_run.json"), metadata)
        last_publish = 0
        with (output / (args.phase + "_receipts.jsonl")).open("x") as stream:
            for experiment in experiments:
                row = observe(experiment, provider, headers.get(provider, {}))
                stream.write(wire(row) + "\n")
                stream.flush()
                metadata["actual_observations"] += 1
                metadata["actual_calls"] += len(row["stages"])
                metadata["last_case"] = row["case_id"]
                metadata["last_arm"] = row["arm"]
                save(output / (args.phase + "_run.json"), metadata)
                save(args.output / (args.phase + "_progress.json"), progress)
                if time.monotonic() - last_publish >= 40:
                    publish(args.output, args.s3_output)
                    last_publish = time.monotonic()
        metadata.update(status="complete", finished_at=stamp())
        save(output / (args.phase + "_run.json"), metadata)
        save(output / (args.phase + "_health_after.json"),
             call(model["url"] + "/health", None, headers.get(provider, {})))
        save(args.output / (args.phase + "_progress.json"), progress)
        publish(args.output, args.s3_output)
        print(wire({"provider": provider, "phase": args.phase,
                    "observations": metadata["actual_observations"],
                    "calls": metadata["actual_calls"]}), flush=True)
    snapshot(args.output, args.phase + "_after")
    progress.update(status="complete", finished_at=stamp())
    save(args.output / (args.phase + "_progress.json"), progress)
    publish(args.output, args.s3_output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiments", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", choices=["probe", "formal"], required=True)
    parser.add_argument("--providers", nargs="+", choices=list(MODELS), default=list(MODELS))
    parser.add_argument("--secret-arn", required=True)
    parser.add_argument("--s3-output")
    run(parser.parse_args())
