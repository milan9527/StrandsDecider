"""Audit the completed experiment, write its report and keep its EC2 running."""

import fcntl
import json
import time

import boto3

from all_models_protocol import save, stamp
from optimized_all_models_infra import CONFIG, ROOT, active, collect
from report_optimized_models import PROJECT, audit, render


def main():
    record = {"started_at": stamp(), "status": "waiting_for_benchmarks",
              "ec2_policy": "keep_running"}
    path = ROOT / "finalization.json"
    if path.exists():
        prior = json.loads(path.read_text())
        assert prior["status"] != "complete", "Experiment is already finalized"
        archive = ROOT / "attempts/orchestration" / ("finalizer-" + stamp().replace(":", "-") + ".json")
        save(archive, prior)
        record["prior_state"] = str(archive.relative_to(ROOT))
    save(path, record)
    try:
        while True:
            controller = json.loads((ROOT / "gpu-orchestration.json").read_text())
            if controller["status"] == "failed":
                raise RuntimeError("GPU controller failed; see preserved operation logs")
            if controller["status"] == "complete":
                break
            time.sleep(20)
        record["status"] = "auditing"
        save(path, record)
        record["collection"] = collect()
        result = audit(ROOT)
        report = render(ROOT, result)
        record.update(report=str(report.relative_to(PROJECT)),
                      final_comparison_calls=result["calls"],
                      total_calls_including_predecessor=result["total_calls_including_predecessor"])
        save(path, record)

        # The user explicitly requested that the EC2 instance remain running.
        instance = active()
        assert instance["instance_id"] == "i-0bd4d9196f1c163c0"
        assert instance["region"] == "us-east-1"
        ec2 = boto3.client("ec2", region_name=instance["region"], config=CONFIG)
        data = ec2.describe_instances(InstanceIds=[instance["instance_id"]])
        state = data["Reservations"][0]["Instances"][0]["State"]["Name"]
        record.update(status="complete", instance_state=state, completed_at=stamp())
        save(path, record)
        print(json.dumps(record, indent=2), flush=True)
    except BaseException as error:
        record.update(status="failed", error_type=type(error).__name__, error=str(error),
                      failed_at=stamp())
        save(path, record)
        raise


if __name__ == "__main__":
    with (ROOT / "finalization-controller.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        main()
