"""Continue unattempted observations after the documented SDK byte capture failure."""

import argparse
import base64
import hashlib
import json
from pathlib import Path

import boto3
from api_ablation_protocol import GPT_MODEL
from botocore.config import Config
from run_api_ablation import observe
from run_resident import save, sha, stamp


def encode_binary(value):
    if isinstance(value, bytes):
        return {"__sdk_bytes_base64__": base64.b64encode(value).decode("ascii")}
    raise TypeError("Unsupported captured type: " + type(value).__name__)


def resume(run):
    plan = json.loads((run / "plan.json").read_text())
    for name, checksum in plan["source_sha256"].items():
        if hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() != checksum:
            raise ValueError("Original source changed: " + name)
    experiments = json.loads((run / "experiments.json").read_text())
    assert sha(experiments) == plan["experiments_sha256"]
    output = run / "gpt"
    original = output / "formal_receipts.jsonl"
    receipts = [json.loads(s) for s in original.read_text().splitlines()]
    assert len(receipts) == 179
    for row, experiment in zip(receipts, experiments[:len(receipts)], strict=True):
        assert all(row[k] == experiment[k] for k in ("case_id", "arm", "variant"))
    lost = experiments[len(receipts)]
    assert (lost["case_id"], lost["variant"], lost["arm"]) == ("M08", "reversed", "criteria_only")
    assert lost["arm"] != "two_stage"
    log = (run / "gpt_formal.log").read_text()
    assert "Object of type bytes is not JSON serializable" in log
    assert 'stream.write(wire(row) + "\\n")' in log
    recovery_path = output / "recovery_plan.json"
    if recovery_path.exists():
        raise FileExistsError("Recovery already planned; refusing duplicate requests")
    recovery_plan = {
        "created_at": stamp(), "original_recorded_observations": len(receipts),
        "original_receipts_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
        "original_metadata_sha256": hashlib.sha256((output / "formal_run.json").read_bytes()).hexdigest(),
        "original_log_sha256": hashlib.sha256((run / "gpt_formal.log").read_bytes()).hexdigest(),
        "original_plan_sha256": hashlib.sha256((run / "plan.json").read_bytes()).hexdigest(),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "experiments_sha256": sha(experiments),
        "lost_observation": {
            **{k: lost[k] for k in ("case_id", "dataset", "arm", "variant")},
            "index_zero_based": len(receipts), "known_attempted_calls": 1,
            "status": "capture_error", "raw_response_available": False,
            "reason": "SDK object contained bytes; JSON serialization failed after observe returned. "
                      "Response, choices, status and timing were lost; no score can be recovered.",
            "scoring": "Count as failure with missing response, never as a wrong model decision.",
        },
        "remaining_indices": list(range(len(receipts) + 1, len(experiments))),
        "changes": "Only lossless JSON serialization of SDK bytes using __sdk_bytes_base64__; "
                   "reuse frozen observe(), payload, model, effort, parser, grading. No replay.",
        "automatic_retries": 0, "replayed_observations": 0,
    }
    save(recovery_path, recovery_plan)
    (output / "resume_api_capture.py").write_bytes(Path(__file__).read_bytes())
    client = boto3.client("bedrock-runtime", region_name=plan["region"],
                          config=Config(connect_timeout=10, read_timeout=180,
                                        retries={"total_max_attempts": 1}))
    metadata = {"started_at": stamp(), "status": "running", "provider": "gpt",
                "expected_model": GPT_MODEL, "actual_observations": 0, "actual_calls": 0,
                "errors": 0, "automatic_retries": 0, "concurrency_per_provider": 1,
                "recovery_plan_sha256": hashlib.sha256(recovery_path.read_bytes()).hexdigest()}
    save(output / "remainder_run.json", metadata)
    try:
        with (output / "remainder_receipts.jsonl").open("x") as stream:
            for index in recovery_plan["remaining_indices"]:
                row = observe(experiments[index], "gpt", client)
                stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":"),
                                        allow_nan=False, default=encode_binary) + "\n")
                stream.flush()
                metadata["actual_observations"] += 1
                metadata["actual_calls"] += len(row["stages"])
                metadata["errors"] += row["status"] != "ok"
                metadata["last_case"] = row["case_id"]
                save(output / "remainder_run.json", metadata)
                if metadata["actual_observations"] % 10 == 0 or row["status"] != "ok":
                    print(json.dumps(metadata), flush=True)
        metadata.update(status="complete", finished_at=stamp())
    finally:
        client.close()
        save(output / "remainder_run.json", metadata)
    print(json.dumps(metadata), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    resume(parser.parse_args().run)
