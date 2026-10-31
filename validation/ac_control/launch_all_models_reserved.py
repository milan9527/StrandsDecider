"""Launch one reserved L4 with the cloned benchmark environment."""

import json
import subprocess
import sys
import time
from datetime import UTC, datetime

import boto3
from all_models_protocol import ROOT, save, stamp
from botocore.config import Config
from botocore.exceptions import ClientError


def main():
    root = ROOT / "infrastructure"
    assert not (root / "active_instance.json").exists()
    reservation = json.loads((root / "reserved_capacity.json").read_text())
    region = reservation["region"]
    reservation_id = reservation["capacity_reservation_id"]
    client = boto3.client("ec2", region_name=region,
                          config=Config(retries={"total_max_attempts": 1}))
    image_record = root / "tokyo-image-direct-registration.json"
    image_id = json.loads(image_record.read_text())["response"]["ImageId"]
    while True:
        current_reservation = client.describe_capacity_reservations(
            CapacityReservationIds=[reservation_id])["CapacityReservations"][0]
        assert current_reservation["State"] == "active", current_reservation["State"]
        remaining = (current_reservation["EndDate"] - datetime.now(UTC)).total_seconds()
        assert remaining > 3600, "Reservation nearly expired; do not launch a long test"
        image = client.describe_images(ImageIds=[image_id])["Images"][0]
        save(root / "tokyo-image-status.json", {"recorded_at": stamp(), "image": image})
        print(stamp(), "image", image["State"], "reservation", reservation_id, flush=True)
        assert image["State"] in ("pending", "available"), image["State"]
        if image["State"] == "available":
            break
        time.sleep(30)
    assert not (root / "active_instance.json").exists()
    network = json.loads((root / "tokyo-network.json").read_text())
    path = root / "replacement-launch-tokyo-reserved.json"
    assert not path.exists()
    request = json.loads((root / "replacement-launch-automatic.request.json").read_text())
    request.update(
        ImageId=image_id, SubnetId=network["subnet"]["SubnetId"],
        SecurityGroupIds=[network["security_groups"][0]["GroupId"]],
        ClientToken="ac-nine-20261030-tokyo-reserved",
        CapacityReservationSpecification={
            "CapacityReservationTarget": {"CapacityReservationId": reservation_id}},
    )
    assert request["InstanceType"] == "g6.xlarge"
    save(path.with_suffix(".request.json"), request)
    try:
        response = client.run_instances(**request)
    except ClientError as error:
        save(path, {"recorded_at": stamp(), "error": error.response})
        raise
    save(path, {"recorded_at": stamp(), "response": response})
    instance = response["Instances"][0]
    active = {
        "recorded_at": stamp(), "instance_id": instance["InstanceId"], "region": region,
        "availability_zone": instance["Placement"]["AvailabilityZone"],
        "instance_type": instance["InstanceType"], "source_image": image_id,
        "capacity_reservation_id": reservation_id,
    }
    save(root / "active_instance.json", active)
    save(root / "actual-region-amendment.json", {
        **active, "gpu": "One NVIDIA L4", "vcpus": 4, "memory_gib": 16,
        "reason": "US capacity attempts failed; targeted reservation succeeded in Tokyo.",
        "environment_source": "Complete stopped benchmark disk copied through an AMI.",
        "boot_image_registration": str(image_record.relative_to(ROOT)),
        "completed_snapshot_registered_directly": True,
        "inference_inputs_and_schedule_unchanged": True,
        "all_seven_local_models_same_host": True,
        "cloud_api_region_unchanged": "us-east-1",
    })
    print(json.dumps(active), flush=True)
    subprocess.run(
        [sys.executable, "-u", str(ROOT.parents[1] / "continue_all_models.py"),
         "--controller-name", "gpu-controller-tokyo"], check=True)


if __name__ == "__main__":
    main()
