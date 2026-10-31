"""Answer-free serial benchmark; no disk/network artifact work inside serial30 timing."""

import argparse
import copy
import hashlib
import json
import socket
import subprocess
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path


def stamp():
    return datetime.now(UTC).isoformat()


def wire(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def sha(value):
    # Match run_resident.sha: ordered compact JSON, not sorted keys.
    return hashlib.sha256(wire(value).encode()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def fetch(url, payload=None):
    request = urllib.request.Request(url, data=wire(payload).encode() if payload is not None else None,
                                     headers={"Content-Type": "application/json"})
    started = time.perf_counter()
    result = {}
    try:
        try:
            response = urllib.request.urlopen(request, timeout=180)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            text = response.read().decode()
            result.update(http_status=response.status, response_text=text,
                          status="ok" if response.status == 200 else "http_error")
            try:
                result["response"] = json.loads(text)
            except ValueError:
                result["status"] = "format_error"
    except (OSError, TimeoutError) as error:
        result.update(status="transport_error", error=str(error))
    result["client_ms"] = (time.perf_counter() - started) * 1000
    return result


def selected(response, payload):
    answers = response.get("answers")
    assert isinstance(answers, dict) and set(answers) == set(payload["questions"]), "Question IDs changed"
    result = {}
    for key, spec in payload["questions"].items():
        answer = answers[key]
        assert isinstance(answer, dict) and answer.get("type", "choice") == "choice", "Invalid answer type"
        value = answer.get("choice")
        assert isinstance(value, str) and value in spec["criteria"], "Invalid candidate"
        result[key] = value
    return result


def snapshot():
    commands = {
        "gpu": ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,driver_version,utilization.gpu",
                "--format=csv,noheader"],
        "processes": ["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader"],
    }
    return {"recorded_at": stamp(), "hostname": socket.gethostname(),
            **{key: subprocess.run(command, capture_output=True, text=True, check=True).stdout
               for key, command in commands.items()}}


def run(args):
    root = args.run
    cases = json.loads((root / "cases.json").read_text())
    plan = json.loads((root / "plan.json").read_text())
    assert sha(cases) == plan["cases_sha256"]
    models = json.loads((root / "models.json").read_text())
    assert sha(models) == plan["models_sha256"]
    model_id = models[args.provider]["repository"]
    output = root / "results" / args.provider
    output.mkdir(parents=True, exist_ok=False)
    save(output / "environment_before.json", snapshot())
    health = fetch(args.endpoint + "/health")
    save(output / "health_before.json", health)
    assert health["status"] == "ok", "Model is not healthy"
    meta = {"started_at": stamp(), "status": "running", "provider": args.provider,
            "model": models[args.provider], "external_concurrency": 1, "automatic_retries": 0,
            "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "calls": 0, "errors": 0, "serial30_blocks": [],
            "endpoint": args.endpoint}
    save(output / "run.json", meta)
    s03 = next(case for case in cases if case["case_id"] == "S03" and case["order"] == "original")

    def observe(case, kind, repetition=0, key=None):
        payload = copy.deepcopy(case["payload"])
        if key is not None:
            payload["questions"] = {key: payload["questions"][key]}
        payload["model"] = model_id
        if args.provider == "h2o":
            payload["attention_mode"] = "bidirectional"
        row = {key: case[key] for key in ("case_id", "dataset", "order", "language")}
        row.update(kind=kind, repetition=repetition, started_at=stamp(),
                   transport_request=payload, input_sha256=sha(payload))
        row.update(fetch(args.endpoint + "/v1/systemone", payload))
        if row["status"] == "ok":
            try:
                assert row["response"].get("model") == model_id, "Unexpected response model"
                assert not row["response"].get("effort_used", {}).get("state_selection"), "Input was truncated"
                row["choices"] = selected(row["response"], payload)
                row["commands"] = [{"cmdKey": k, "cmdValue": v}
                                   for k, v in row["choices"].items() if v != "omit"]
            except (AssertionError, KeyError, TypeError) as error:
                row.update(status="format_error", error=str(error))
        row.setdefault("commands", [])
        row["finished_at"] = stamp()
        return row

    def publish():
        if args.s3_output:
            subprocess.run(["aws", "s3", "sync", str(output),
                            args.s3_output.rstrip("/") + "/" + args.provider, "--only-show-errors"],
                           capture_output=True, text=True, timeout=90, check=True)

    with (output / "receipts.jsonl").open("x") as stream:
        def record(rows):
            for row in rows:
                stream.write(wire(row) + "\n")
                meta["calls"] += 1
                meta["errors"] += row["status"] != "ok"
                meta["last"] = {key: row[key] for key in ("case_id", "order", "kind", "repetition")}
            stream.flush()
            save(output / "run.json", meta)

        try:
            for repetition in range(3):
                row = observe(s03, "warmup_full30", repetition)
                record([row])
                assert row["status"] == "ok", "Full30 warmup failed; preserve failure and stop"
            failures = 0
            for index, case in enumerate(cases):
                row = observe(case, "quality")
                record([row])
                failures = failures + 1 if row["status"] != "ok" else 0
                assert failures < 3, "Three consecutive errors; preserve partial run"
                if (index + 1) % 16 == 0:
                    publish()
            for key in s03["payload"]["questions"]:
                row = observe(s03, "warmup_single", key=key)
                record([row])
                assert row["status"] == "ok", "Single-field warmup failed"
            for repetition in range(3):
                order = ("single_key", "serial30", "full30") if repetition % 2 == 0 else (
                    "full30", "serial30", "single_key")
                for kind in order:
                    if kind == "serial30":
                        started_at, started = stamp(), time.perf_counter()
                        # Buffer all receipts until the whole serial task has finished.
                        rows = [observe(s03, kind, repetition, key=key)
                                for key in s03["payload"]["questions"]]
                        elapsed = (time.perf_counter() - started) * 1000
                        meta["serial30_blocks"].append({
                            "repetition": repetition, "started_at": started_at, "finished_at": stamp(),
                            "wall_ms": elapsed, "http_sum_ms": sum(row["client_ms"] for row in rows),
                            "artifact_operations_inside_block": 0,
                        })
                    else:
                        rows = [observe(s03, kind, repetition, key="t_temp" if kind == "single_key" else None)]
                    record(rows)
                    assert all(row["status"] == "ok" for row in rows), "Timing block failed"
                publish()
            assert meta["calls"] == 285
            meta["status"] = "complete"
        except BaseException as error:
            meta.update(status="failed", error_type=type(error).__name__, error=str(error))
            raise
        finally:
            meta["finished_at"] = stamp()
            save(output / "run.json", meta)
            save(output / "environment_after.json", snapshot())
            save(output / "health_after.json", fetch(args.endpoint + "/health"))
            publish()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--endpoint", default="http://127.0.0.1:18811")
    parser.add_argument("--s3-output")
    run(parser.parse_args())
