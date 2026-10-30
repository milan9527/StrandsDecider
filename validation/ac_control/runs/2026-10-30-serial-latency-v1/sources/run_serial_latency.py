"""Measure one AC task at a time, including strictly serial per-Key requests."""

import argparse
import json
import subprocess
from pathlib import Path

from run_ablation import MODELS, call, choices
from run_resident import save, sha, snapshot, stamp, wire


def run(args):
    payload = json.loads((args.run / "payload.json").read_text())
    plan = json.loads((args.run / "plan.json").read_text())
    assert sha(payload) == plan["payload_sha256"] and len(payload["questions"]) == 30
    snapshot(args.run, "before")
    secret = subprocess.run(
        ["aws", "secretsmanager", "get-secret-value", "--secret-id", plan["secret_arn"],
         "--query", "SecretString", "--output", "text"],
        capture_output=True, text=True, timeout=30, check=True,
    )
    auth = {"Authorization": "Bearer " + json.loads(secret.stdout)["api_key"]}
    with (args.run / "receipts.jsonl").open("x") as output:
        for provider, model in MODELS.items():
            headers = auth if provider == "decider" else {}
            save(args.run / (provider + "_health_before.json"),
                 call(model["url"] + "/health", None, headers))
            for repetition in range(-1, plan["repetitions"]):
                modes = (["full_30"] if repetition == -1
                         else ["full_30", "serial_1"] if repetition % 2 == 0
                         else ["serial_1", "full_30"])
                for mode in modes:
                    tasks = ([payload] if mode == "full_30" else [
                        {"state": payload["state"], "questions": {key: value}}
                        for key, value in payload["questions"].items()
                    ])
                    for task in tasks:
                        row = {
                            "provider": provider, "mode": mode, "repetition": repetition,
                            "warmup": repetition == -1, "started_at": stamp(),
                            "question_ids": list(task["questions"]), "input_sha256": sha(task),
                            **call(model["url"] + "/v1/systemone", task, headers),
                        }
                        row["finished_at"] = stamp()
                        if row["status"] == "ok":
                            try:
                                row["choices"] = choices(row["response"], task, model["id"])
                            except (ValueError, TypeError, KeyError) as error:
                                row.update(status="format_error", error=str(error))
                        output.write(wire(row) + "\n")
                        output.flush()
                    print(wire({"provider": provider, "repetition": repetition, "mode": mode}), flush=True)
            save(args.run / (provider + "_health_after.json"),
                 call(model["url"] + "/health", None, headers))
    snapshot(args.run, "after")
    save(args.run / "complete.json", {"finished_at": stamp(), "status": "complete"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    run(parser.parse_args())
