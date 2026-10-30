"""Execute an answer-free, hashed H2O job strictly serially on the GPU host."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from h2o_ac_client import decide
from run_ablation import call
from run_resident import save, snapshot, stamp, wire


def runtime():
    response = subprocess.run(["docker", "inspect", "decider-h2o-resident"],
                              capture_output=True, text=True, timeout=15, check=True)
    container = json.loads(response.stdout)[0]
    env = dict(item.split("=", 1) for item in container["Config"]["Env"] if "=" in item)
    return {"recorded_at": stamp(), "image": container["Image"],
            "started_at": container["State"]["StartedAt"], "restart_count": container["RestartCount"],
            "env": {key: env.get(key) for key in (
                "MAX_LEN", "GPU_UTIL", "VLLM_ARGS", "SHIM_CACHE_WRITE", "VLLM_CACHE_ROOT",
                "CUDA_GRAPH_MAX_TOKENS", "VLLM_GDN_PREFILL_GRAPH_MAX_TOKENS",
                "VLLM_GDN_PREFILL_GRAPH_PRECAPTURE", "VLLM_GDN_PREFILL_GRAPH_MAX_SEQS")}}


def publish(root, uri):
    subprocess.run(["aws", "s3", "sync", str(root), uri, "--only-show-errors"],
                   capture_output=True, text=True, timeout=60, check=True)


def run(args):
    root = args.run
    plan = json.loads((root / "plan.json").read_text())
    for name, digest in plan["sources"].items():
        assert hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() == digest
    path = root / "jobs" / (args.job + ".json")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == args.sha256
    job = json.loads(path.read_text())
    out = root / "stages" / args.job
    out.mkdir(parents=True, exist_ok=False)
    snapshot(out, "before")
    save(out / "runtime.json", runtime())
    health = call("http://127.0.0.1:18803/health", None, {})
    save(out / "health_before.json", health)
    assert health["status"] == "ok" and health["response"]["model"] == plan["model"]
    meta = {"started_at": stamp(), "status": "running", "actual_calls": 0, "errors": 0,
            "job_sha256": args.sha256, "planned_calls": len(job["requests"]),
            "external_concurrency": 1, "automatic_retries": 0}
    save(out / "run.json", meta)
    with (out / "receipts.jsonl").open("x") as stream:
        try:
            for index, item in enumerate(job["requests"]):
                row = {key: value for key, value in item.items() if key != "payload"}
                row.update(decide(item["payload"]))
                stream.write(wire(row) + "\n")
                stream.flush()
                meta["actual_calls"] += 1
                meta["errors"] += row["status"] != "ok"
                meta["last"] = {key: row.get(key) for key in (
                    "case_id", "order", "profile", "attention", "kind", "repetition")}
                save(out / "run.json", meta)
                if row["status"] != "ok":
                    raise RuntimeError("Failed observation retained; stopping without retry")
                if (index + 1) % 8 == 0:
                    publish(root, args.s3_output)
            meta.update(status="complete", finished_at=stamp())
        finally:
            save(out / "run.json", meta)
            snapshot(out, "after")
            save(out / "health_after.json", call("http://127.0.0.1:18803/health", None, {}))
            publish(root, args.s3_output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--job", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--s3-output", required=True)
    run(parser.parse_args())
