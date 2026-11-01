"""Infrastructure for the isolated Liquid LoRA experiment, never stopping EC2."""
import hashlib
import io
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent / "runs/2026-11-01-liquid-lora-v1"
REMOTE = "/opt/ac-liquid-lora"
INSTANCE = "i-0bd4d9196f1c163c0"
REGION = "us-east-1"
BUCKET = "strands-decider-vllm-632930644527"
PREFIX = "ac-liquid-lora/2026-11-01-v1"
PYTHON = "/opt/ac-input-tests/envs/h2o/bin/python"
MODEL = "/opt/ac-input-tests/models/liquid"


def stamp():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def client(name):
    return boto3.client(name, region_name=REGION,
                        config=Config(connect_timeout=10, read_timeout=30,
                                      retries={"total_max_attempts": 2}))


def submit(name, script, timeout=3600):
    path = ROOT / "operations" / f"{name}.json"
    assert not path.exists(), "Operation names must be unique; no inference resubmissions."
    path.parent.mkdir(parents=True, exist_ok=True)
    path.with_suffix(".sh").write_text(script)
    result = client("ssm").send_command(
        InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
        Parameters={"commands": [script], "executionTimeout": [str(timeout)]},
        Comment="Liquid LoRA isolated experiment: " + name[:45],
    )
    op = {"id": result["Command"]["CommandId"], "instance": INSTANCE,
          "submitted_at": stamp(), "script_sha256": hashlib.sha256(script.encode()).hexdigest()}
    save(path, op)
    return op


def status(name):
    path = ROOT / "operations" / f"{name}.json"
    op = json.loads(path.read_text())
    try:
        r = client("ssm").get_command_invocation(CommandId=op["id"], InstanceId=INSTANCE)
    except ClientError as error:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(op["submitted_at"])).total_seconds()
        if error.response["Error"]["Code"] != "InvocationDoesNotExist" or age > 120:
            raise
        return {"Status": "Pending", "StandardOutputContent": "",
                "note": "SSM command visibility delay; do not resubmit."}
    result = {k: r.get(k) for k in ("Status", "ResponseCode", "StandardOutputContent",
                                   "StandardErrorContent", "ExecutionStartDateTime",
                                   "ExecutionEndDateTime")}
    save(path.with_suffix(".status.json"), result)
    return result


def transfer(name, files):
    path = ROOT / f"{name}.tar.gz"
    assert not path.exists()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as archive:
        for arc, source in files.items():
            assert not Path(arc).is_absolute() and ".." not in Path(arc).parts
            archive.add(source, arcname=arc)
    path.write_bytes(buf.getvalue())
    key = f"input/{PREFIX}/{path.name}"
    client("s3").put_object(Bucket=BUCKET, Key=key, Body=path.read_bytes(),
                            ServerSideEncryption="AES256")
    manifest = {"key": key, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "files": {arc: hashlib.sha256(p.read_bytes()).hexdigest()
                          for arc, p in files.items()}}
    save(path.with_suffix(".json"), manifest)
    return manifest


def collect():
    c = client("s3")
    prefix = f"output/{PREFIX}/"
    count = 0
    for page in c.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            rel = Path(obj["Key"].removeprefix(prefix))
            assert not rel.is_absolute() and ".." not in rel.parts
            p = ROOT / rel
            if p.exists() and p.stat().st_size == obj["Size"] and p.stat().st_mtime >= obj["LastModified"].timestamp():
                continue
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(c.get_object(Bucket=BUCKET, Key=obj["Key"])["Body"].read())
            count += 1
    return {"downloaded": count}


if __name__ == "__main__":
    import sys
    print(json.dumps(status(sys.argv[2]) if sys.argv[1] == "status" else collect(), indent=2))
