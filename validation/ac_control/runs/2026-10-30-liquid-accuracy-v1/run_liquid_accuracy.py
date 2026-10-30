"""Run frozen Liquid AC strategy comparisons serially on the resident service."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from liquid_ac_client import MODEL, decide
from run_ablation import call
from run_resident import save, sha, snapshot, stamp, wire


def publish(root, uri):
    if uri:
        subprocess.run(["aws", "s3", "sync", str(root), uri, "--only-show-errors"],
                       capture_output=True, text=True, timeout=60, check=True)


def run(args):
    root = args.run
    plan = json.loads((root / "plan.json").read_text())
    cases = json.loads((root / (args.phase + "_cases.json")).read_text())
    assert sha(cases) == plan[args.phase + "_sha256"]
    for name, digest in plan["source_sha256"].items():
        assert hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() == digest
    if args.phase == "development":
        strategies = plan["strategies"]
    else:
        selection = json.loads((root / "selection.json").read_text())
        strategies = list(dict.fromkeys(["baseline", "two_stage", selection["candidate"]]))
    output = root / args.phase
    output.mkdir(exist_ok=False)
    snapshot(output, "before")
    health = call("http://127.0.0.1:18801/health", None, {})
    assert health["status"] == "ok" and health["response"]["model"] == MODEL
    save(output / "health_before.json", health)
    inspection = subprocess.run(["docker", "inspect", "decider-liquid-resident"],
                                capture_output=True, text=True, timeout=15, check=True)
    container = json.loads(inspection.stdout)[0]
    save(output / "runtime.json", {
        "image": container["Image"], "started_at": container["State"]["StartedAt"],
        "restart_count": container["RestartCount"], "command": container["Config"]["Cmd"],
    })
    meta = {"phase": args.phase, "started_at": stamp(), "status": "running",
            "observations": 0, "actual_calls": 0, "errors": 0, "strategies": strategies}
    save(output / "run.json", meta)
    with (output / "warmup.jsonl").open("x") as stream:
        warmup = next(case for case in cases if case["order"] == "original")
        for strategy in strategies:
            row = decide(warmup["payload"], strategy)
            stream.write(wire(row) + "\n")
            assert row["status"] == "ok"
    with (output / "receipts.jsonl").open("x") as stream:
        try:
            for index, case in enumerate(cases):
                rotated = strategies[index % len(strategies):] + strategies[:index % len(strategies)]
                for strategy in rotated:
                    row = {k: case[k] for k in ("case_id", "dataset", "category", "order", "input_sha256")}
                    row.update(decide(case["payload"], strategy))
                    stream.write(wire(row) + "\n")
                    stream.flush()
                    meta["observations"] += 1
                    meta["actual_calls"] += len(row["stages"])
                    meta["errors"] += row["status"] != "ok"
                    meta["last"] = {key: row[key] for key in ("case_id", "order", "strategy")}
                    save(output / "run.json", meta)
                if (index + 1) % 5 == 0:
                    publish(root, args.s3_output)
            meta.update(status="complete", finished_at=stamp())
        finally:
            save(output / "run.json", meta)
            snapshot(output, "after")
            save(output / "health_after.json", call("http://127.0.0.1:18801/health", None, {}))
            publish(root, args.s3_output)
    print(wire(meta))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--phase", choices=("development", "validation"), required=True)
    parser.add_argument("--s3-output")
    run(parser.parse_args())
