"""Infrastructure and evidence operations restricted to the AC test instance."""

import argparse
import json
from pathlib import Path

import boto3
from all_models_protocol import ROOT, digest, save, stamp
from botocore.config import Config

ACTIVE_INSTANCE = ROOT / "infrastructure/active_instance.json"
INSTANCE = (json.loads(ACTIVE_INSTANCE.read_text())["instance_id"]
            if ACTIVE_INSTANCE.exists() else "i-0bd4d9196f1c163c0")
RESIDENT = "i-0ae7eb0abcb815af3"
BUCKET = "strands-decider-vllm-632930644527"
PREFIX = "ac-all-models/2026-10-30-full-v1"
REMOTE = "/opt/ac-nine-tests"
CONFIG = Config(connect_timeout=10, read_timeout=30, retries={"max_attempts": 0})


def submit(name, script, timeout=3600, instance=None):
    active = json.loads(ACTIVE_INSTANCE.read_text()) if ACTIVE_INSTANCE.exists() else {}
    if instance is None:
        instance = active.get("instance_id", INSTANCE)
    region = active.get("region", "us-east-1") if instance == active.get("instance_id") else "us-east-1"
    path = ROOT / "operations" / (name + ".json")
    assert not path.exists(), "Operation names are immutable"
    source = path.with_suffix(".sh")
    source.parent.mkdir(exist_ok=True)
    source.write_text(script)
    response = boto3.client("ssm", region_name=region, config=CONFIG).send_command(
        InstanceIds=[instance], DocumentName="AWS-RunShellScript",
        Parameters={"commands": [script], "executionTimeout": [str(timeout)]},
        Comment="Unified nine-model AC test: " + name[:50])
    result = {"id": response["Command"]["CommandId"], "instance": instance, "region": region,
              "submitted_at": stamp(), "script_sha256": digest(source)}
    save(path, result)
    return result


def status(name):
    path = ROOT / "operations" / (name + ".json")
    operation = json.loads(path.read_text())
    try:
        response = boto3.client("ssm", region_name=operation.get("region", "us-east-1"), config=CONFIG).get_command_invocation(
            CommandId=operation["id"], InstanceId=operation["instance"])
    except boto3.client("ssm", region_name="us-east-1").exceptions.InvocationDoesNotExist:
        return {"Status": "Pending"}
    result = {key: response.get(key) for key in (
        "Status", "ResponseCode", "StandardOutputContent", "StandardErrorContent",
        "ExecutionStartDateTime", "ExecutionEndDateTime")}
    save(path.with_suffix(".status.json"), result)
    return result


def collect():
    client = boto3.client("s3", region_name="us-east-1", config=CONFIG)
    count = 0
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix="output/" + PREFIX + "/"):
        for obj in page.get("Contents", []):
            relative = Path(obj["Key"].removeprefix("output/" + PREFIX + "/"))
            assert not relative.is_absolute() and ".." not in relative.parts
            target = ROOT / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(client.get_object(Bucket=BUCKET, Key=obj["Key"])["Body"].read())
            count += 1
    return {"objects_downloaded": count}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("submit", "status", "collect"))
    parser.add_argument("--name")
    parser.add_argument("--script", type=Path)
    parser.add_argument("--instance", default=INSTANCE)
    parser.add_argument("--timeout", type=int, default=3600)
    args = parser.parse_args()
    result = (submit(args.name, args.script.read_text(), args.timeout, args.instance) if args.action == "submit"
              else status(args.name) if args.action == "status" else collect())
    print(json.dumps(result, indent=2))
