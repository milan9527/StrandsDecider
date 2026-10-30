"""Measure unchanged AC inputs on one H2O deployment configuration, serially."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from run_ablation import call, choices
from run_resident import save, sha, snapshot, stamp, wire

MODEL = "h2oai/h2o-lightning-4b"
URL = "http://127.0.0.1:18803"


def publish(run, uri):
    if uri:
        subprocess.run(["aws", "s3", "sync", str(run), uri, "--only-show-errors"],
                       capture_output=True, text=True, timeout=60, check=True)


def run_test(args):
    root = args.run
    plan = json.loads((root / "plan.json").read_text())
    cases = json.loads((root / "cases.json").read_text())
    payload = json.loads((root / "payload.json").read_text())
    assert sha(cases) == plan["cases_sha256"] and sha(payload) == plan["payload_sha256"]
    for name, digest in plan["runner_source_sha256"].items():
        assert hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() == digest
    output = root / "variants" / args.variant
    output.mkdir(parents=True, exist_ok=True)
    if (output / "receipts.jsonl").exists():
        raise FileExistsError("Refusing to replay or overwrite observations")
    snapshot(output, "before")
    health = call(URL + "/health", None, {})
    save(output / "health_before.json", health)
    assert health["status"] == "ok" and health["response"]["model"] == MODEL
    assert args.attention in health["response"]["modes"]
    inspect = subprocess.run(["docker", "inspect", "decider-h2o-resident"],
                             capture_output=True, text=True, timeout=15, check=True)
    container = json.loads(inspect.stdout)[0]
    # The H2O container has no credentials; preserve only relevant runtime fields.
    env = {entry.split("=", 1)[0]: entry.split("=", 1)[1]
           for entry in container["Config"]["Env"] if "=" in entry}
    save(output / "runtime.json", {
        "recorded_at": stamp(), "image": container["Image"],
        "started_at": container["State"]["StartedAt"], "restart_count": container["RestartCount"],
        "env": {key: env.get(key) for key in (
            "MAX_LEN", "GPU_UTIL", "VLLM_ARGS", "CUDA_GRAPH_MAX_TOKENS",
            "VLLM_GDN_PREFILL_GRAPH_MAX_TOKENS", "VLLM_GDN_PREFILL_GRAPH_PRECAPTURE",
            "VLLM_CACHE_ROOT", "SHIM_ATTENTION_MODE",
        )},
    })
    metadata = {
        "variant": args.variant, "attention_mode": args.attention,
        "started_at": stamp(), "status": "running", "actual_calls": 0,
        "errors": 0, "concurrency": 1, "automatic_retries": 0,
        "plan_sha256": hashlib.sha256((root / "plan.json").read_bytes()).hexdigest(),
        "phase": args.phase,
    }
    save(output / "run.json", metadata)
    with (output / "receipts.jsonl").open("x") as stream:
        def invoke(task, **fields):
            transport = task if args.attention == "bidirectional" else {
                **task, "attention_mode": args.attention,
            }
            row = {
                **fields, "variant": args.variant, "attention_mode": args.attention,
                "question_ids": list(task["questions"]), "input_sha256": sha(task),
                "transport_request": transport, "transport_sha256": sha(transport),
                "started_at": stamp(), **call(URL + "/v1/systemone", transport, {}),
                "finished_at": stamp(),
            }
            if row["status"] == "ok":
                try:
                    assert row["response"]["attention_mode"] == args.attention
                    row["choices"] = choices(row["response"], task, MODEL)
                except (AssertionError, ValueError, TypeError, KeyError) as error:
                    row.update(status="format_error", error=str(error))
            stream.write(wire(row) + "\n")
            stream.flush()
            metadata["actual_calls"] += 1
            metadata["errors"] += row["status"] != "ok"
            metadata["last"] = fields
            save(output / "run.json", metadata)
            if row["status"] != "ok":
                raise RuntimeError("Saved failed observation; stopping without retry")
            return row

        try:
            invoke(payload, phase="warmup", repetition=-1, mode="full_30", case_id="S03")
            if args.phase in ("all", "performance"):
                for repetition in range(plan["repetitions"]):
                    modes = ["full_30", "serial_1"] if repetition % 2 == 0 else ["serial_1", "full_30"]
                    for mode in modes:
                        tasks = ([payload] if mode == "full_30" else [
                            {"state": payload["state"], "questions": {key: question}}
                            for key, question in payload["questions"].items()
                        ])
                        for task in tasks:
                            invoke(task, phase="performance", repetition=repetition,
                                   mode=mode, case_id="S03")
                        print(wire({"variant": args.variant, "phase": "performance",
                                    "repetition": repetition, "mode": mode,
                                    "completed": metadata["actual_calls"]}), flush=True)
                        publish(root, args.s3_output)
            if args.phase in ("all", "quality"):
                for index, case in enumerate(cases):
                    invoke(case["payload"], phase="quality", repetition=0, mode="full_30",
                           case_id=case["case_id"], order=case["order"], dataset=case["dataset"])
                    if (index + 1) % 5 == 0:
                        print(wire({"variant": args.variant, "phase": "quality",
                                    "cases": index + 1, "completed": metadata["actual_calls"]}), flush=True)
                        publish(root, args.s3_output)
            metadata.update(status="complete", finished_at=stamp())
        finally:
            save(output / "run.json", metadata)
            snapshot(output, "after")
            save(output / "health_after.json", call(URL + "/health", None, {}))
            publish(root, args.s3_output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--attention", choices=["bidirectional", "causal"], default="bidirectional")
    parser.add_argument("--phase", choices=["all", "performance", "quality"], default="all")
    parser.add_argument("--s3-output")
    run_test(parser.parse_args())
