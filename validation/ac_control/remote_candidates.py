"""Manage the one authorized isolated L4 benchmark instance through SSM."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import boto3

ROOT = Path(__file__).parent / "runs/2026-10-30-candidates-l4-v1"
INSTANCE = "i-0bd4d9196f1c163c0"
BUCKET = "strands-decider-vllm-632930644527"
PREFIX = "ac-candidates/2026-10-30-l4-v1"
REMOTE = "/opt/ac-candidate-tests"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str) + "\n")


def submit(name, script, timeout=3600, instance=INSTANCE):
    path = ROOT / "operations" / (name + ".json")
    assert not path.exists(), "Operation names are immutable"
    source = ROOT / "operations" / (name + ".sh")
    source.parent.mkdir(exist_ok=True)
    source.write_text(script)
    response = boto3.client("ssm", region_name="us-east-1").send_command(
        InstanceIds=[instance], DocumentName="AWS-RunShellScript",
        Parameters={"commands": [script], "executionTimeout": [str(timeout)]},
        Comment="Authorized isolated L4 AC benchmark: " + name[:50],
    )
    result = {"id": response["Command"]["CommandId"], "instance": instance,
              "submitted_at": datetime.now(UTC).isoformat(),
              "script_sha256": hashlib.sha256(script.encode()).hexdigest()}
    save(path, result)
    return result


def status(name):
    path = ROOT / "operations" / (name + ".json")
    operation = json.loads(path.read_text())
    response = boto3.client("ssm", region_name="us-east-1").get_command_invocation(
        CommandId=operation["id"], InstanceId=operation["instance"])
    fields = ("Status", "ResponseCode", "StandardOutputContent", "StandardErrorContent",
              "ExecutionStartDateTime", "ExecutionEndDateTime")
    result = {key: response.get(key) for key in fields}
    save(path.with_suffix(".status.json"), result)
    return result


def collect():
    s3 = boto3.client("s3", region_name="us-east-1")
    prefix = "output/" + PREFIX + "/"
    count = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            relative = Path(obj["Key"].removeprefix(prefix))
            assert not relative.is_absolute() and ".." not in relative.parts
            target = ROOT / relative
            data = s3.get_object(Bucket=BUCKET, Key=obj["Key"])["Body"].read()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            count += 1
    return {"downloaded_objects": count}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("submit", "status", "collect"))
    parser.add_argument("--name")
    parser.add_argument("--script", type=Path)
    parser.add_argument("--timeout", type=int, default=3600)
    args = parser.parse_args()
    result = (submit(args.name, args.script.read_text(), args.timeout) if args.action == "submit"
              else status(args.name) if args.action == "status" else collect())
    print(json.dumps(result, indent=2))
