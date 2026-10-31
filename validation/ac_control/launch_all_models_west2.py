"""Wait for the cloned environment and attempt one equivalent L4 in us-west-2."""

import json
import subprocess
import sys
import time

import boto3
from all_models_protocol import ROOT, save, stamp
from botocore.config import Config
from botocore.exceptions import ClientError


def main():
    root = ROOT / "infrastructure"
    assert not (root / "active_instance.json").exists()
    client = boto3.client("ec2", region_name="us-west-2",
                          config=Config(retries={"total_max_attempts": 1}))
    image_id = json.loads((root / "west2-image-copy.json").read_text())["response"]["ImageId"]
    while True:
        image = client.describe_images(ImageIds=[image_id])["Images"][0]
        save(root / "west2-image-status.json", {"recorded_at": stamp(), "image": image})
        print(stamp(), "image", image["State"], flush=True)
        assert image["State"] in ("pending", "available"), image["State"]
        if image["State"] == "available":
            break
        time.sleep(30)
    assert not (root / "active_instance.json").exists()
    path = root / "replacement-launch-west2-automatic.json"
    assert not path.exists()
    request = json.loads((root / "replacement-launch-automatic.request.json").read_text())
    request.update(ImageId=image_id, SecurityGroupIds=["sg-086810599c0e44d6a"],
                   ClientToken="ac-nine-20261030-west2-auto")
    assert request["InstanceType"] == "g6.xlarge"
    save(path.with_suffix(".request.json"), request)
    save(root / "region-amendment.json", {
        "recorded_at": stamp(), "region": "us-west-2", "instance_type": "g6.xlarge",
        "gpu": "One NVIDIA L4", "vcpus": 4, "memory_gib": 16,
        "reason": "No successful independent L4 allocation in us-east-1; attempt normal on-demand launch in us-west-2.",
        "environment_source": "Complete stopped benchmark disk copied through an AMI.",
        "inference_inputs_and_schedule_unchanged": True,
        "all_seven_local_models_same_host": True,
        "cloud_api_region_unchanged": "us-east-1",
    })
    try:
        response = client.run_instances(**request)
    except ClientError as error:
        save(path, {"recorded_at": stamp(), "error": error.response})
        raise
    save(path, {"recorded_at": stamp(), "response": response})
    instance = response["Instances"][0]
    active = {
        "recorded_at": stamp(), "instance_id": instance["InstanceId"], "region": "us-west-2",
        "availability_zone": instance["Placement"]["AvailabilityZone"],
        "instance_type": instance["InstanceType"], "source_image": image_id,
    }
    save(root / "active_instance.json", active)
    print(json.dumps(active), flush=True)
    subprocess.run([sys.executable, "-u", str(ROOT.parents[1] / "continue_all_models.py"),
                    "--controller-name", "gpu-controller-west2"], check=True)


if __name__ == "__main__":
    main()
