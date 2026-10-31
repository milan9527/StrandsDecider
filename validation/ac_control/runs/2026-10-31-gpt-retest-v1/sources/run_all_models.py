"""One shared answer-free schedule for local and hosted nine-model AC benchmarks."""

import argparse
import json
import platform
import subprocess
import time
from pathlib import Path

from all_models_protocol import PROVIDERS, business_payload, digest, save, sha, stamp, wire
from run_candidate_benchmark import fetch, selected


def run(args):
    root = args.run
    plan = json.loads((root / "plan.json").read_text())
    # References are deliberately never loaded by the inference runner.
    for name in ("cases.json", "models.json", "schedule.json"):
        assert digest(root / name) == plan["input_sha256"][name], name
    for name, expected in plan["source_sha256"].items():
        assert digest(Path(__file__).with_name(name)) == expected, name
    cases = {(c["case_id"], c["order"]): c for c in json.loads((root / "cases.json").read_text())}
    jobs = json.loads((root / "schedule.json").read_text())
    model = json.loads((root / "models.json").read_text())[args.provider]
    output = root / "results" / args.provider
    output.mkdir(parents=True, exist_ok=False)
    meta = {
        "provider": args.provider, "model": model, "started_at": stamp(), "status": "running",
        "calls": 0, "errors": 0, "blocks": [], "external_concurrency": 1,
        "automatic_retries": 0, "plan_sha256": digest(root / "plan.json"),
        "runner_sha256": digest(Path(__file__)), "hostname": platform.node(),
        "expected_model": None if args.provider == "jev" else model["repository"],
    }
    save(output / "run.json", meta)
    client = None
    if args.provider in ("jev", "gpt"):
        import boto3
        import httpx
        from botocore.config import Config
        from run_api_ablation import invoke

        config = Config(connect_timeout=10, read_timeout=180, retries={"total_max_attempts": 1})
        if args.provider == "gpt":
            profile = boto3.client("bedrock", region_name=plan["region"], config=config).get_inference_profile(
                inferenceProfileIdentifier=plan["gpt_model"])
            save(output / "bedrock_profile.json", profile)
            assert profile["status"] == "ACTIVE" and profile["inferenceProfileId"] == plan["gpt_model"]
            client = boto3.client("bedrock-runtime", region_name=plan["region"], config=config)
        else:
            secret = boto3.client("secretsmanager", region_name=plan["region"], config=config).get_secret_value(
                SecretId=plan["jev_secret_arn"])["SecretString"].strip()
            client = httpx.Client(headers={"Authorization": "Bearer " + secret},
                                  timeout=httpx.Timeout(180, connect=10), trust_env=False, follow_redirects=False)
            del secret
        save(output / "environment.json", {
            "python": platform.python_version(), "platform": platform.platform(),
            "boto3": boto3.__version__, "httpx": httpx.__version__,
        })
    else:
        health = fetch(args.endpoint + "/health")
        save(output / "health_before.json", health)
        assert health["status"] == "ok" and health["response"]["model"] == meta["expected_model"]
        process = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader"],
            capture_output=True, text=True, check=True)
        save(output / "environment.json", {"recorded_at": stamp(), "processes": process.stdout,
                                          "python": platform.python_version(), "platform": platform.platform()})

    def observe(job, key):
        payload = business_payload(cases[job["case_id"], job["order"]], key)
        row = {k: job[k] for k in ("case_id", "dataset", "order", "language", "kind", "repetition")}
        row.update(provider=args.provider, field=key, sequence=meta["calls"])
        if client is not None:
            row.update(invoke(args.provider, client, payload, meta["expected_model"]))
            if args.provider == "jev" and row["status"] == "ok" and meta["expected_model"] is None:
                meta["expected_model"] = row["model_id"]
        else:
            transport = dict(payload, model=meta["expected_model"])
            if args.provider == "h2o":
                transport["attention_mode"] = "bidirectional"
            row.update(payload=payload, input_sha256=sha(payload), transport_request=transport,
                       transport_sha256=sha(transport), started_at=stamp())
            row.update(fetch(args.endpoint + "/v1/systemone", transport))
            if row["status"] == "ok":
                try:
                    assert row["response"]["model"] == meta["expected_model"], "Model identity changed"
                    assert not row["response"].get("effort_used", {}).get("state_selection"), "Input truncated"
                    if args.provider == "h2o":
                        assert row["response"]["attention_mode"] == "bidirectional"
                    row["choices"] = selected(row["response"], payload)
                except (AssertionError, KeyError, TypeError, ValueError) as error:
                    row.update(status="format_error", error=str(error))
        row["commands"] = [{"cmdKey": k, "cmdValue": v} for k, v in row.get("choices", {}).items() if v != "omit"]
        row["finished_at"] = stamp()
        return row

    def publish():
        if args.s3_output:
            subprocess.run(["aws", "s3", "sync", str(output), args.s3_output.rstrip("/") + "/" + args.provider,
                            "--only-show-errors"], check=True, timeout=120, capture_output=True)

    consecutive_errors = 0
    try:
        with (output / "receipts.jsonl").open("x") as stream:
            for job_index, job in enumerate(jobs):
                started_at, started = stamp(), time.perf_counter()
                rows = []
                for key in job["keys"]:
                    row = observe(job, key)
                    row["sequence"] = meta["calls"] + len(rows)
                    rows.append(row)
                    consecutive_errors = consecutive_errors + 1 if row["status"] != "ok" else 0
                    if consecutive_errors >= 3:
                        break
                elapsed = (time.perf_counter() - started) * 1000
                block_finished = stamp()
                if job["kind"] == "serial30":
                    meta["blocks"].append({
                        "case_id": job["case_id"], "repetition": job["repetition"],
                        "started_at": started_at, "finished_at": block_finished,
                        "wall_ms": elapsed, "http_sum_ms": sum(r["client_ms"] for r in rows),
                        "calls": len(rows), "artifact_operations_inside_block": 0,
                    })
                # Serial receipts are buffered. All artifact writes occur after its timer stops.
                for row in rows:
                    from resume_api_capture import encode_binary
                    stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":"),
                                            allow_nan=False, default=encode_binary) + "\n")
                    meta["calls"] += 1
                    meta["errors"] += row["status"] != "ok"
                stream.flush()
                meta["last"] = {k: job[k] for k in ("case_id", "kind", "repetition", "order")}
                meta["completed_jobs"] = job_index + 1
                save(output / "run.json", meta)
                if job["kind"] in ("serial30", "full30") or (job_index + 1) % 16 == 0:
                    print(wire({k: meta[k] for k in ("provider", "calls", "errors", "last")}), flush=True)
                    publish()
                assert consecutive_errors < 3, "Three consecutive failed calls; evidence retained without replay."
                if job["kind"].startswith("warmup"):
                    assert all(r["status"] == "ok" for r in rows), "Warmup failed; evidence retained."
        assert meta["calls"] == plan["calls_per_provider"]
        meta["status"] = "complete" if not meta["errors"] else "complete_with_errors"
    except BaseException as error:
        meta.update(status="failed", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        if client is not None:
            client.close()
        meta["finished_at"] = stamp()
        save(output / "run.json", meta)
        if client is None:
            save(output / "health_after.json", fetch(args.endpoint + "/health"))
        publish()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--provider", choices=PROVIDERS, required=True)
    parser.add_argument("--endpoint", default="http://127.0.0.1:18811")
    parser.add_argument("--s3-output")
    run(parser.parse_args())
