"""Install official vision on the existing experimental L4 without replacing text services."""

import argparse
import base64
import hashlib
import io
import json
import tarfile
from datetime import UTC, datetime
from pathlib import Path

import boto3
from botocore.config import Config

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", default="i-0daca64f56056aa1c")
    parser.add_argument("--wheels", type=Path, default=ROOT / ".deployment/vision-20261023/wheels")
    parser.add_argument("--name", default="decider-vision-service-20261023-v1")
    args = parser.parse_args()
    local = ROOT / ".deployment" / args.name
    local.mkdir(exist_ok=True)
    ecs = boto3.client("ecs", region_name="us-east-1")
    s3 = boto3.client("s3", region_name="us-east-1", config=Config(signature_version="s3v4"))
    source = ecs.describe_task_definition(taskDefinition="strands-decider-demo-gpu-model:3")["taskDefinition"]
    original = source["containerDefinitions"][0]
    upstream = ROOT / "validation/vision/sources"
    provenance = json.loads((upstream / "upstream.json").read_text())
    for file in provenance["package_files"]:
        assert hashlib.sha256((upstream / file["file"]).read_bytes()).hexdigest() == file["sha256"]
    fixture = json.loads((ROOT / "validation/vision/cases.json").read_text())["cases"][0]
    warmup = {**fixture["request"], "images": [
        base64.b64encode((ROOT / "validation/vision" / fixture["image"]).read_bytes()).decode(),
    ]}
    bundle = local / "bundle.tar"
    with tarfile.open(bundle, "w") as archive:
        for name in ("vision_server.py", "vision_bootstrap.py"):
            archive.add(ROOT / "deployment" / name, arcname=name)
        archive.add(args.wheels, arcname="wheels")
        archive.add(upstream / "upstream", arcname="upstream")
        for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
            archive.add(upstream / name, arcname=name)
        for name, value in {
            "warmup.json": warmup,
            "provenance.json": {"upstream_commit": provenance["commit"], "source_files": provenance["package_files"]},
        }.items():
            data = json.dumps(value, ensure_ascii=False).encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    account = boto3.client("sts").get_caller_identity()["Account"]
    bucket = f"strands-decider-tetris-training-{account}"
    key = args.name + "/bundle.tar"
    s3.upload_file(str(bundle), bucket, key)
    definition = ecs.register_task_definition(
        family="strands-decider-vision-installer", networkMode="host", requiresCompatibilities=["EC2"],
        executionRoleArn=source["executionRoleArn"],
        volumes=[{"name": "docker", "host": {"sourcePath": "/var/run/docker.sock"}}],
        containerDefinitions=[{
            "name": "installer", "image": original["image"], "cpu": 128, "memory": 384,
            "user": "0", "essential": True, "entryPoint": ["python", "-u", "-c"],
            "command": [(ROOT / "deployment/vision_host_install.py").read_text()],
            "mountPoints": [{"sourceVolume": "docker", "containerPath": "/var/run/docker.sock"}],
            "logConfiguration": {**original["logConfiguration"], "options": {
                **original["logConfiguration"]["options"], "awslogs-stream-prefix": "vision-install",
            }},
        }],
    )["taskDefinition"]["taskDefinitionArn"]
    env = {
        "VISION_CONTAINER": args.name, "MODEL_IMAGE": original["image"],
        "BUNDLE_SHA256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
        "BUNDLE_URL": s3.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=1800),
    }
    response = ecs.run_task(
        cluster="strands-decider-demo", taskDefinition=definition, launchType="EC2", count=1,
        placementConstraints=[{"type": "memberOf", "expression": f"ec2InstanceId == {args.instance}"}],
        overrides={"containerOverrides": [{"name": "installer", "environment": [
            {"name": k, "value": v} for k, v in env.items()
        ]}]}, startedBy="vision-module-deploy",
    )
    assert not response.get("failures"), response.get("failures")
    state = {
        "created_at": datetime.now(UTC).isoformat(), "instance": args.instance,
        "container_name": args.name, "task": response["tasks"][0]["taskArn"],
        "task_definition": definition, "bundle_sha256": env["BUNDLE_SHA256"],
        "upstream_commit": provenance["commit"], "log_group": original["logConfiguration"]["options"]["awslogs-group"],
    }
    (local / "state.json").write_text(json.dumps(state, indent=2) + "\n")
    print(json.dumps(state))


if __name__ == "__main__":
    main()
