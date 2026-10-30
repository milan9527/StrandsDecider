"""Transfer answer-free Liquid trials to the existing GPU; never restart services."""

import argparse
import hashlib
import io
import json
import shlex
import tarfile
from pathlib import Path

import boto3


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def submit(root, phase):
    if phase == "development":
        if (root / "transfer.json").exists():
            raise FileExistsError("Run already submitted")
        transfer = {
            "region": "us-east-1", "bucket": "strands-decider-vllm-632930644527",
            "instance": "i-0ae7eb0abcb815af3", "prefix": "ac-control/" + root.name,
            "remote": "/opt/decider-open-models/ac-control/" + root.name, "commands": [],
        }
        plan = json.loads((root / "plan.json").read_text())
        files = {name: root / name for name in ("plan.json", "development_cases.json")}
        files.update({name: root / "sources" / name for name in plan["source_sha256"]})
    else:
        transfer = json.loads((root / "transfer.json").read_text())
        files = {name: root / name for name in ("validation_cases.json", "selection.json")}
    ssm = boto3.client("ssm", region_name=transfer["region"])
    if transfer["commands"]:
        status = ssm.get_command_invocation(
            CommandId=transfer["commands"][-1]["id"], InstanceId=transfer["instance"])["Status"]
        assert status == "Success", "Prior phase is not complete"
    assert phase not in [command["phase"] for command in transfer["commands"]]
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for name, path in files.items():
            assert name != "references.json"
            data = path.read_bytes()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    data = stream.getvalue()
    (root / (phase + "_input.tar.gz")).write_bytes(data)
    key = "input/" + transfer["prefix"] + "/" + phase + ".tar.gz"
    boto3.client("s3", region_name=transfer["region"]).put_object(
        Bucket=transfer["bucket"], Key=key, Body=data, ServerSideEncryption="AES256")
    remote = transfer["remote"]
    uri = "s3://" + transfer["bucket"] + "/output/" + transfer["prefix"] + "/results"
    script = [
        "set -eu",
        shlex.join(["mkdir", "-p", remote]),
        shlex.join(["aws", "s3", "cp", "s3://" + transfer["bucket"] + "/" + key,
                    remote + "/" + phase + "_input.tar.gz", "--only-show-errors"]),
        shlex.join(["tar", "-xzf", remote + "/" + phase + "_input.tar.gz", "-C", remote]),
        "trap " + shlex.quote(shlex.join(["aws", "s3", "sync", remote, uri, "--only-show-errors"])) + " EXIT",
        shlex.join(["python3", remote + "/run_liquid_accuracy.py", "--run", remote,
                    "--phase", phase, "--s3-output", uri]),
    ]
    response = ssm.send_command(
        InstanceIds=[transfer["instance"]], DocumentName="AWS-RunShellScript",
        Parameters={"commands": ["\n".join(script)], "executionTimeout": ["3600"]},
        Comment="Liquid AC accuracy: serial inference only; no service restarts")
    transfer["commands"].append({
        "phase": phase, "id": response["Command"]["CommandId"], "input_key": key,
        "archive_sha256": hashlib.sha256(data).hexdigest(), "files": list(files),
    })
    save(root / "transfer.json", transfer)
    print(json.dumps(transfer["commands"][-1]))


def collect(root):
    transfer = json.loads((root / "transfer.json").read_text())
    command = transfer["commands"][-1]
    response = boto3.client("ssm", region_name=transfer["region"]).get_command_invocation(
        CommandId=command["id"], InstanceId=transfer["instance"])
    save(root / (command["phase"] + "_ssm.json"), {key: response.get(key) for key in (
        "Status", "ResponseCode", "StandardOutputContent", "StandardErrorContent")})
    prefix = "output/" + transfer["prefix"] + "/results/"
    s3 = boto3.client("s3", region_name=transfer["region"])
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=transfer["bucket"], Prefix=prefix):
        for item in page.get("Contents", []):
            relative = Path(item["Key"].removeprefix(prefix))
            assert not relative.is_absolute() and ".." not in relative.parts
            target = root / relative
            data = s3.get_object(Bucket=transfer["bucket"], Key=item["Key"])["Body"].read()
            if target.exists() and relative.name in (
                "plan.json", "development_cases.json", "validation_cases.json", "selection.json"):
                assert target.read_bytes() == data, "Frozen input changed"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    progress = root / command["phase"] / "run.json"
    print(json.dumps({"ssm": response["Status"],
                      "progress": json.loads(progress.read_text()) if progress.exists() else None}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("development", "validation", "collect"))
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    collect(args.run) if args.action == "collect" else submit(args.run, args.action)
