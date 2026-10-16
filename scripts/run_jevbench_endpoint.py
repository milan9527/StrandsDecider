"""Run pinned JevBench public tasks against an existing native Decider endpoint.

The official harness, task text, candidate order and scorer remain unmodified.
This script does not start, stop or change the model service.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

COMMIT = "1bcc55eb6c8cffde2306b3db03ede39b61c6152a"
MODEL = "strands-decider-2B-hobson-v19"


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def health(endpoint):
    with urlopen(endpoint.rstrip("/") + "/health", timeout=20) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--harness", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--endpoint", required=True)
    args = parser.parse_args()
    harness, out = args.harness.resolve(), args.output.resolve()
    if out.is_relative_to(harness):
        raise ValueError("Output must be outside the JevBench checkout")
    if out.exists() and any(out.iterdir()):
        raise ValueError("Use a new, empty output directory")
    out.mkdir(parents=True, exist_ok=True)
    started = datetime.now(UTC).isoformat()
    before = health(args.endpoint)
    save(out / "health-before.json", before)
    if before.get("model") != MODEL or before.get("max_length") != 4096:
        raise ValueError("Unexpected model identity or context window; no tasks sent")
    task_path = out / "tasks.jsonl"
    task_path.write_bytes(b"".join(
        (harness / f"datasets/public/{name}.jsonl").read_bytes()
        for name in ("original", "easy", "hard")
    ))
    sys.path.insert(0, str(harness))
    from jevbench.adapters.typesafe import TypeSafeAdapter
    from jevbench.tasks import dataset_hash, load_jsonl

    tasks = load_jsonl(str(task_path))
    if len(tasks) != 231 or len({t.id for t in tasks}) != 231:
        raise ValueError("Expected exactly 231 unique public tasks")
    adapter = TypeSafeAdapter(endpoint=args.endpoint, model=MODEL, key_env="")
    warmups = []
    for kind in ("choice", "noul", "score"):
        task = next(t for t in tasks if t.question["type"] == kind)
        result = adapter.run(task)
        warmups.append({
            "type": kind, "task_id": task.id,
            "request": result.request_body, "response": result.raw,
            "ok": result.ok, "error": result.error, "status": result.status,
            "latency_s": result.latency_s,
        })
        save(out / "warmups.json", warmups)
        if not result.ok:
            raise RuntimeError(f"Warmup {kind} failed: {result.error}")
    meta = {
        "started_at": started,
        "jevbench_commit": COMMIT,
        "model": MODEL,
        "dataset_hash": dataset_hash(tasks),
        "task_file_sha256": hashlib.sha256(task_path.read_bytes()).hexdigest(),
        "public_tasks": len(tasks),
        "warmups_excluded": len(warmups),
        "concurrency": 1,
        "retries": 0,
        "endpoint": args.endpoint,
        "timing": "Fargate client to existing GPU service over private HTTP; includes network and service queuing",
        "gpu_lifecycle_changes": 0,
        "scope": "JevBench v1 public231, not current leaderboard Composite",
    }
    save(out / "run-meta.json", meta)
    env = {**os.environ, "PYTHONPATH": str(harness), "PYTHONUNBUFFERED": "1"}
    command = [
        sys.executable, "-m", "jevbench.cli", "run",
        "--tasks", str(task_path), "--adapter", "typesafe",
        "--endpoint", args.endpoint, "--key-env", "", "--model", MODEL,
        "--run-label", "decider-original-public231-20261016",
        "--revision", "strands-decider:63d24ae286e50105fba0bd1db15b0e243aea4650",
        "--cost-basis", "self_hosted_ec2_no_per_request_tariff_compute_excluded",
        "--reserve-usd", "0",
        "--results", str(out / "results.jsonl"),
        "--raw-dir", str(out / "raw"),
        "--ledger", str(out / "ledger.jsonl"),
        "--manifest", str(out / "manifest.json"),
    ]
    save(out / "command.json", command)
    with (out / "run.log").open("w") as log:
        proc = subprocess.Popen(
            command, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        for line in proc.stdout:
            print(line, end="", flush=True)
            log.write(line)
            log.flush()
        code = proc.wait()
    summary_command = [
        sys.executable, "-m", "jevbench.cli", "summarize",
        "--tasks", str(task_path),
        "--results", str(out / "results.jsonl"),
        "--ledger", str(out / "ledger.jsonl"),
        "--public-export", str(out / "summary.json"),
    ]
    with (out / "summarize.log").open("w") as log:
        subprocess.run(summary_command, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    after = health(args.endpoint)
    save(out / "health-after.json", after)
    summary = json.loads((out / "summary.json").read_text())
    meta.update(
        finished_at=datetime.now(UTC).isoformat(),
        harness_exit_code=code,
        model_health_unchanged=before == after,
        n_attempted=summary["n_attempted"],
        n_correct=summary["n_correct"],
        accuracy=summary["accuracy"],
        complete=summary["complete"],
    )
    save(out / "run-meta.json", meta)
    print(json.dumps(meta, ensure_ascii=False), flush=True)
    if code or not summary["complete"] or before != after:
        raise RuntimeError("Incomplete run or model service identity changed; retained all evidence")


if __name__ == "__main__":
    main()
