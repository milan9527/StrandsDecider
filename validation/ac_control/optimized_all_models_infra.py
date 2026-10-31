"""Infrastructure operations for the authorized isolated input-optimization test."""

import argparse
import io
import json
import shlex
import tarfile
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from all_models_protocol import digest, save, stamp
from optimized_all_models_protocol import ROOT, SOURCES

BUCKET = "strands-decider-vllm-632930644527"
PREFIX = "ac-input-optimization/2026-10-31-nine-v1"
REMOTE = "/opt/ac-input-tests"
CONFIG = Config(connect_timeout=10, read_timeout=30, retries={"total_max_attempts": 1})


def active():
    record = json.loads((ROOT / "infrastructure/active_instance.json").read_text())
    assert record["instance_id"] in ("i-0bd4d9196f1c163c0", "i-01e87f489911925cf")
    assert record["instance_type"] == "g6.xlarge"
    return record


def submit(name, script, timeout=3600):
    instance = active()
    path = ROOT / "operations" / f"{name}.json"
    assert not path.exists(), "Operation names are immutable"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.with_suffix(".sh").write_text(script)
    response = boto3.client("ssm", region_name=instance["region"], config=CONFIG).send_command(
        InstanceIds=[instance["instance_id"]], DocumentName="AWS-RunShellScript",
        Parameters={"commands": [script], "executionTimeout": [str(timeout)]},
        Comment="Nine-model AC input optimization: " + name[:50],
    )
    result = {"id": response["Command"]["CommandId"], "instance": instance["instance_id"],
              "region": instance["region"], "submitted_at": stamp(),
              "script_sha256": digest(path.with_suffix(".sh"))}
    save(path, result)
    return result


def status(name):
    path = ROOT / "operations" / f"{name}.json"
    operation = json.loads(path.read_text())
    try:
        result = boto3.client("ssm", region_name=operation["region"], config=CONFIG).get_command_invocation(
            CommandId=operation["id"], InstanceId=operation["instance"])
    except ClientError as error:
        # SendCommand is eventually consistent: a successful submission can take
        # a few seconds to appear in GetCommandInvocation. Poll the same command;
        # never submit it again or retry a model request.
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(operation["submitted_at"])).total_seconds()
        if error.response.get("Error", {}).get("Code") != "InvocationDoesNotExist" or age > 120:
            raise
        output = {
            "Status": "Pending", "ResponseCode": -1,
            "StandardOutputContent": "", "StandardErrorContent": "",
            "ExecutionStartDateTime": None, "ExecutionEndDateTime": None,
            "poll_note": "Submitted command is not yet visible in GetCommandInvocation",
            "observed_at": stamp(),
        }
        save(path.with_suffix(".status.json"), output)
        return output
    output = {key: result.get(key) for key in (
        "Status", "ResponseCode", "StandardOutputContent", "StandardErrorContent",
        "ExecutionStartDateTime", "ExecutionEndDateTime",
    )}
    save(path.with_suffix(".status.json"), output)
    return output


def transfer():
    files = {name: ROOT / "profiles/baseline/sources" / name for name in SOURCES}
    here = Path(__file__).parent
    files["candidate_server.py"] = here / "candidate_server.py"
    # Use the frozen runtime adapter, not unrelated working-tree application edits.
    files["liquid_server.py"] = here / "runs/2026-10-30-all-models-full-v1/runtime_sources/liquid_server.py"
    cases = []
    for profile in ("baseline", "compact_catalog", "schema_once"):
        folder = ROOT / "profiles" / profile
        for name in ("cases.json", "models.json", "schedule.json", "plan.json"):
            files[f"profiles/{profile}/{name}"] = folder / name
        cases.extend(json.loads((folder / "cases.json").read_text()))
    save(ROOT / "runtime-preflight-cases.json", cases)
    files["cases.json"] = ROOT / "runtime-preflight-cases.json"
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for name, path in files.items():
            assert path.is_file() and Path(name).name not in ("references.json", "spec_references.json", "spec.md")
            archive.add(path, arcname=name)
    artifact = ROOT / "runtime-input.tar.gz"
    assert not artifact.exists()
    artifact.write_bytes(stream.getvalue())
    key = "input/" + PREFIX + "/runtime-input.tar.gz"
    boto3.client("s3", region_name="us-east-1", config=CONFIG).put_object(
        Bucket=BUCKET, Key=key, Body=artifact.read_bytes(), ServerSideEncryption="AES256")
    result = {"recorded_at": stamp(), "bucket": BUCKET, "key": key, "sha256": digest(artifact),
              "files": {name: digest(path) for name, path in files.items()},
              "reference_answers_in_archive": False}
    save(ROOT / "runtime-transfer.json", result)
    return {"files": len(files), "bytes": artifact.stat().st_size, "sha256": result["sha256"]}


def collect():
    s3 = boto3.client("s3", region_name="us-east-1", config=CONFIG)
    prefix = "output/" + PREFIX + "/"
    count = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            relative = Path(obj["Key"].removeprefix(prefix))
            assert not relative.is_absolute() and ".." not in relative.parts
            target = ROOT / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(s3.get_object(Bucket=BUCKET, Key=obj["Key"])["Body"].read())
            count += 1
    return {"objects": count}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("submit", "status", "transfer", "collect"))
    parser.add_argument("--name")
    parser.add_argument("--script", type=Path)
    parser.add_argument("--timeout", type=int, default=3600)
    args = parser.parse_args()
    result = (submit(args.name, args.script.read_text(), args.timeout) if args.action == "submit"
              else status(args.name) if args.action == "status"
              else transfer() if args.action == "transfer" else collect())
    print(json.dumps(result, indent=2))
