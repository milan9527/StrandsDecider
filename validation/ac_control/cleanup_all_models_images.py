"""Remove only this run's temporary image copies after successful finalization."""

import json

import boto3
from all_models_protocol import PROVIDERS, ROOT, save, stamp


def cleanup():
    audit = json.loads((ROOT / "audit.json").read_text())
    assert audit["passed"] and audit["observed_calls"] == 18441
    archive = json.loads((ROOT / "receipt-archive.json").read_text())
    assert archive["lossless"] and set(archive["providers"]) == set(PROVIDERS)
    active = json.loads((ROOT / "infrastructure/active_instance.json").read_text())
    assert active["instance_id"] == "i-01e87f489911925cf"
    tokyo = boto3.client("ec2", region_name="ap-northeast-1")
    instance = tokyo.describe_instances(
        InstanceIds=[active["instance_id"]])["Reservations"][0]["Instances"][0]
    assert instance["State"]["Name"] == "stopped"
    assert instance["ImageId"] == "ami-0a555d6d091154165"
    resources = {
        "us-east-1": {
            "images": {"ami-035e007c40c3d6957"},
            "snapshots": {"snap-0268249ee324c48cc"},
        },
        "ap-northeast-1": {
            "images": {"ami-0f10edf115af897b3", "ami-0a555d6d091154165"},
            "snapshots": {"snap-013b703746a5b1dd3"},
        },
    }
    path = ROOT / "infrastructure/temporary-image-cleanup.json"
    result = json.loads(path.read_text()) if path.exists() else {
        "started_at": stamp(), "status": "running", "inventory": {}, "actions": [],
    }
    for region, targets in resources.items():
        client = boto3.client("ec2", region_name=region)
        images = client.describe_images(
            Owners=["self"], Filters=[{"Name": "image-id", "Values": sorted(targets["images"])}])["Images"]
        snapshots = client.describe_snapshots(
            OwnerIds=["self"], Filters=[{"Name": "snapshot-id", "Values": sorted(targets["snapshots"])}]
        )["Snapshots"]
        result["inventory"].setdefault(region, {"images": images, "snapshots": snapshots})
        save(path, result)
        for image in images:
            assert image["ImageId"] in targets["images"] and image["OwnerId"] == "632930644527"
            assert image["Name"].startswith("ac-nine-models-")
            assert {b["Ebs"]["SnapshotId"] for b in image["BlockDeviceMappings"]
                    if "Ebs" in b} <= targets["snapshots"]
            response = client.deregister_image(ImageId=image["ImageId"])
            result["actions"].append({"at": stamp(), "region": region,
                                      "deregistered_image": image["ImageId"], "response": response})
            save(path, result)
        # Both Tokyo registrations reference one snapshot; remove all registrations first.
        for snapshot in snapshots:
            assert snapshot["SnapshotId"] in targets["snapshots"] and snapshot["OwnerId"] == "632930644527"
            response = client.delete_snapshot(SnapshotId=snapshot["SnapshotId"])
            result["actions"].append({"at": stamp(), "region": region,
                                      "deleted_snapshot": snapshot["SnapshotId"], "response": response})
            save(path, result)
    result.update(status="complete", finished_at=stamp(),
                  retained_test_instance=active["instance_id"], instance_state="stopped",
                  retained_test_root_volumes=instance["BlockDeviceMappings"])
    save(path, result)
    print(json.dumps({"status": result["status"], "actions": len(result["actions"])}))


if __name__ == "__main__":
    cleanup()
