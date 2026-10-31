"""Verify final evidence and stop only the dedicated, newly created test host."""

import json
import time

import boto3
from all_models_infra import ACTIVE_INSTANCE, collect, status
from all_models_protocol import PROVIDERS, ROOT, digest, save, stamp
from archive_all_models_evidence import archive
from finalize_all_models import inventory
from report_all_models import audit, render


def finish():
    active = json.loads(ACTIVE_INSTANCE.read_text())
    instance_id = active["instance_id"]
    assert instance_id not in ("i-0ae7eb0abcb815af3", "i-0bd4d9196f1c163c0")
    client = boto3.client("ec2", region_name=active["region"])
    instance = client.describe_instances(InstanceIds=[instance_id])["Reservations"][0]["Instances"][0]
    tags = {t["Key"]: t["Value"] for t in instance.get("Tags", [])}
    assert tags["Name"] == "ac-nine-models-isolated-L4-20261030"
    assert instance["ImageId"] == active["source_image"]
    assert instance["InstanceType"] == "g6.xlarge"
    assert instance["State"]["Name"] == "running"
    for provider in PROVIDERS:
        meta = json.loads((ROOT / "results" / provider / "run.json").read_text())
        assert meta["status"] in ("complete", "complete_with_errors") and meta["calls"] == 2049
    operation = "final-runtime-inventory"
    if not (ROOT / "operations" / (operation + ".json")).exists():
        print(inventory(), flush=True)
    while True:
        current = status(operation)
        if current["Status"] == "Success":
            break
        assert current["Status"] in ("Pending", "InProgress", "Delayed"), current
        time.sleep(20)
    print(collect(), flush=True)
    final = json.loads((ROOT / "logs/final-runtime-inventory.json").read_text())
    assert final["reference_files_absent"] and not final["gpu_processes"].strip()
    initialized = json.loads((ROOT / "logs/storage-initialization.json").read_text())
    assert initialized["status"] == "complete" and initialized["read_only"]
    assert initialized["read_bytes"] == initialized["total_bytes"]
    assert final["root_read_ahead_kb"] == "128"
    plan = json.loads((ROOT / "plan.json").read_text())
    assert final["inference_sources"] == plan["source_sha256"]
    transferred = json.loads((ROOT / "runtime-transfer.json").read_text())
    assert final["runtime_input_files"] == transferred["files"]
    for provider, files in final["results_file_sha256"].items():
        assert provider in PROVIDERS[2:]
        for filename, expected in files.items():
            assert digest(ROOT / "results" / provider / filename) == expected, (provider, filename)
    assert set(final["results_file_sha256"]) == set(PROVIDERS[2:])
    save(ROOT / "final-evidence-verification.json", {
        "verified_at": stamp(), "remote_and_collected_files_identical": True,
        "reference_files_absent": True, "gpu_empty": True,
        "final_inventory_sha256": digest(ROOT / "logs/final-runtime-inventory.json"),
        "instance_id": instance_id,
    })
    audit(ROOT)
    archive()
    result = audit(ROOT)
    render(ROOT, result)
    response = client.stop_instances(InstanceIds=[instance_id])
    save(ROOT / "infrastructure/test-instance-stop.json", {"recorded_at": stamp(), "response": response})
    if active.get("capacity_reservation_id"):
        reservation_id = active["capacity_reservation_id"]
        reservation = client.describe_capacity_reservations(
            CapacityReservationIds=[reservation_id])["CapacityReservations"][0]
        response = (client.cancel_capacity_reservation(CapacityReservationId=reservation_id)
                    if reservation["State"] == "active" else None)
        save(ROOT / "infrastructure/capacity-reservation-cancel.json",
             {"recorded_at": stamp(), "reservation": reservation, "response": response})
    while True:
        state = client.describe_instances(InstanceIds=[instance_id])["Reservations"][0]["Instances"][0]
        save(ROOT / "infrastructure/test-instance-final.json", {"recorded_at": stamp(), "instance": state})
        if state["State"]["Name"] == "stopped":
            break
        assert state["State"]["Name"] in ("running", "stopping")
        time.sleep(20)
    print(json.dumps({"completed_at": stamp(), "calls": result["observed_calls"],
                      "errors": result["errors"], "instance_stopped": instance_id}), flush=True)


if __name__ == "__main__":
    finish()
