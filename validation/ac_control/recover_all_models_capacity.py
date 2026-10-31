"""Launch one equivalent dedicated L4 from the stopped benchmark environment."""

import json

import boto3
from all_models_protocol import ROOT, save, stamp
from botocore.exceptions import ClientError

IMAGE = "ami-035e007c40c3d6957"
SUBNETS = (
    ("us-east-1a", "subnet-062a148d1354577b3"),
    ("us-east-1b", "subnet-023880de85fb9261b"),
    ("us-east-1c", "subnet-029c0264a7e188a46"),
    ("us-east-1e", "subnet-0280c6306405e4dfa"),
    ("us-east-1f", "subnet-035e3e2820bda44e3"),
)


def launch():
    infrastructure = ROOT / "infrastructure"
    assert not (infrastructure / "active_instance.json").exists()
    ec2 = boto3.client("ec2", region_name="us-east-1")
    image = ec2.describe_images(ImageIds=[IMAGE])["Images"][0]
    save(infrastructure / "clone-image-status.json", {"recorded_at": stamp(), "image": image})
    if image["State"] != "available":
        return {"status": "image_pending"}
    old = ec2.describe_instances(InstanceIds=["i-0bd4d9196f1c163c0"])["Reservations"][0]["Instances"][0]
    assert old["State"]["Name"] == "stopped"
    userdata = "\n".join([
        "#!/bin/bash",
        "set -eu",
        "systemctl stop apt-daily.timer apt-daily-upgrade.timer fwupd-refresh.timer update-notifier-download.timer || true",
        "systemctl mask --runtime apt-daily.service apt-daily-upgrade.service fwupd-refresh.service update-notifier-download.service",
        "systemd-run --unit=ac-nine-auto-stop --on-active=6h /usr/sbin/shutdown -h now",
    ])
    (infrastructure / "replacement-userdata.sh").write_text(userdata + "\n")
    save(infrastructure / "capacity-amendment.json", {
        "recorded_at": stamp(),
        "reason": "Original test instance StartInstances returned InsufficientInstanceCapacity three times.",
        "source_instance": old["InstanceId"], "source_state": "stopped", "clone_ami": IMAGE,
        "replacement_specification": "g6.xlarge: one NVIDIA L4 24GB, four vCPUs, 16GiB RAM",
        "root_disk_gib": 250, "source_root_disk_gib": 200,
        "storage_reason": "Additional pinned Strands container and Strands/Liquid weights.",
        "unchanged": "Frozen model/request schedule; existing five candidate environments and weights cloned byte-for-byte.",
        "protected_resident": "i-0ae7eb0abcb815af3",
        "maximum_running_dedicated_test_instances": 1,
        "stop_guard_hours": 6,
    })
    for zone, subnet in SUBNETS:
        record = infrastructure / ("replacement-launch-" + zone + ".json")
        assert not record.exists(), "Never replay an infrastructure operation silently"
        request = {
            "ImageId": IMAGE, "InstanceType": "g6.xlarge", "MinCount": 1, "MaxCount": 1,
            "SubnetId": subnet, "SecurityGroupIds": ["sg-051a9e10a77085738"],
            "IamInstanceProfile": {"Arn": "arn:aws:iam::632930644527:instance-profile/strands-decider-vllm"},
            "MetadataOptions": {"HttpTokens": "required", "HttpEndpoint": "enabled"},
            "InstanceInitiatedShutdownBehavior": "stop",
            "BlockDeviceMappings": [{"DeviceName": image["RootDeviceName"], "Ebs": {
                "VolumeSize": 250, "VolumeType": "gp3", "Iops": 3000, "Throughput": 500,
                "Encrypted": True, "DeleteOnTermination": True}}],
            "TagSpecifications": [{"ResourceType": resource, "Tags": [
                {"Key": "Name", "Value": "ac-nine-models-isolated-L4-20261030"},
                {"Key": "Purpose", "Value": "Temporary complete uniform AC model benchmark"},
            ]} for resource in ("instance", "volume")],
            "UserData": userdata,
            "ClientToken": "ac-nine-20261030-" + zone,
        }
        save(record.with_suffix(".request.json"), request)
        try:
            response = ec2.run_instances(**request)
        except ClientError as error:
            save(record, {"recorded_at": stamp(), "error": error.response})
            if error.response["Error"]["Code"] in ("InsufficientInstanceCapacity", "Unsupported"):
                continue
            raise
        save(record, {"recorded_at": stamp(), "response": response})
        instance = response["Instances"][0]
        active = {"recorded_at": stamp(), "instance_id": instance["InstanceId"],
                  "availability_zone": instance["Placement"]["AvailabilityZone"],
                  "instance_type": instance["InstanceType"], "source_image": IMAGE}
        save(infrastructure / "active_instance.json", active)
        return active
    raise RuntimeError("No replacement launched: all candidate availability zones failed.")


if __name__ == "__main__":
    print(json.dumps(launch(), indent=2))
