"""Transfer only answer-free jobs; run one SSM operation at a time."""

import argparse
import hashlib
import io
import json
import shlex
import tarfile
from pathlib import Path

import boto3
from run_resident import save, stamp


def submit(args):
    root = args.run
    path = root / "transfer.json"
    transfer = json.loads(path.read_text()) if path.exists() else {
        "region": "us-east-1", "bucket": "strands-decider-vllm-632930644527",
        "instance": "i-0ae7eb0abcb815af3", "prefix": "ac-control/" + root.name,
        "remote": "/opt/decider-open-models/ac-control/" + root.name, "commands": [],
    }
    ssm = boto3.client("ssm", region_name=transfer["region"])
    for previous in transfer["commands"]:
        status = ssm.get_command_invocation(CommandId=previous["id"], InstanceId=transfer["instance"])["Status"]
        assert status in ("Success", "Failed", "TimedOut", "Cancelled"), "An earlier operation is active"
    assert args.name and args.name not in [c["name"] for c in transfer["commands"]]
    assert "/" not in args.name and ".." not in args.name
    files = {}
    if not transfer["commands"]:
        files["plan.json"] = root / "plan.json"
        files.update({p.name: p for p in (root / "sources").iterdir()})
        files["tune_h2o_runtime.py"] = Path(__file__).resolve().parents[2] / "deployment/open_models/tune_h2o_runtime.py"
    if args.action == "job":
        files["jobs/" + args.name + ".json"] = root / "jobs" / (args.name + ".json")
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for name, source in files.items():
            assert "references" not in name
            data = source.read_bytes()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    data = stream.getvalue()
    incoming = root / "transfer_inputs"
    incoming.mkdir(exist_ok=True)
    (incoming / (args.name + ".tar.gz")).write_bytes(data)
    key = "input/" + transfer["prefix"] + "/" + args.name + ".tar.gz"
    boto3.client("s3", region_name=transfer["region"]).put_object(
        Bucket=transfer["bucket"], Key=key, Body=data, ServerSideEncryption="AES256")
    remote = transfer["remote"]
    output_uri = "s3://" + transfer["bucket"] + "/output/" + transfer["prefix"] + "/results"
    script = [
        "set -eu", shlex.join(["mkdir", "-p", remote]),
        shlex.join(["aws", "s3", "cp", "s3://" + transfer["bucket"] + "/" + key,
                    remote + "/" + args.name + "_input.tar.gz", "--only-show-errors"]),
        shlex.join(["tar", "-xzf", remote + "/" + args.name + "_input.tar.gz", "-C", remote]),
        "trap " + shlex.quote(shlex.join(["aws", "s3", "sync", remote, output_uri, "--only-show-errors"])) + " EXIT",
    ]
    if args.action == "job":
        job_sha = hashlib.sha256((root / "jobs" / (args.name + ".json")).read_bytes()).hexdigest()
        invocation = shlex.join(["python3", remote + "/run_h2o_official.py", "--run", remote,
                                "--job", args.name, "--sha256", job_sha, "--s3-output", output_uri])
        restore = shlex.join(["python3", remote + "/tune_h2o_runtime.py", "rollback", "--root", remote])
        script.append("if " + invocation + "; then :; else trial_status=$?; "
                      "if test -f /etc/systemd/system/decider-h2o.service.d/90-ac-optimization.conf"
                      " && test -f " + shlex.quote(remote + "/rollback/original.json")
                      + "; then " + restore + '; fi; exit "$trial_status"; fi')
    elif args.action == "restart":
        # Backup and restart exactly the original unit, without adding any override.
        code = ("from pathlib import Path; import tune_h2o_runtime as t; "
                f"root=Path({remote!r}); t.backup(root); t.rollback(root)")
        script.append(shlex.join(["bash", "-c", "cd " + shlex.quote(remote)
                                  + " && " + shlex.join(["python3", "-c", code])]))
    elif args.action == "gdn1024":
        # The old controller function accepts 1024; only its old CLI enumerated 2048/4096.
        code = ("from pathlib import Path; from types import SimpleNamespace; import tune_h2o_runtime as t; "
                f"t.configure(SimpleNamespace(root=Path({remote!r}),variant='gdn1024',"
                "sequences=1,graphs='off',gdn_tokens=1024,timeout=600))")
        script.append(shlex.join(["bash", "-c", "cd " + shlex.quote(remote)
                                  + " && " + shlex.join(["python3", "-c", code])]))
    else:
        script.append(shlex.join(["python3", remote + "/tune_h2o_runtime.py",
                                  args.action, "--root", remote]))
    response = ssm.send_command(
        InstanceIds=[transfer["instance"]], DocumentName="AWS-RunShellScript",
        Parameters={"commands": ["\n".join(script)], "executionTimeout": ["2400"]},
        Comment="H2O official-guidance trial; serial operations and protected resident services")
    command = {
        "name": args.name, "action": args.action, "submitted_at": stamp(),
        "id": response["Command"]["CommandId"], "input_key": key,
        "archive_sha256": hashlib.sha256(data).hexdigest(),
        "files": {name: hashlib.sha256(source.read_bytes()).hexdigest() for name, source in files.items()},
    }
    transfer["commands"].append(command)
    save(path, transfer)
    print(json.dumps(command))


def collect(root):
    transfer = json.loads((root / "transfer.json").read_text())
    command = transfer["commands"][-1]
    invocation = boto3.client("ssm", region_name=transfer["region"]).get_command_invocation(
        CommandId=command["id"], InstanceId=transfer["instance"])
    save(root / (command["name"] + "_ssm.json"), {key: invocation.get(key) for key in (
        "Status", "ResponseCode", "StandardOutputContent", "StandardErrorContent")})
    s3 = boto3.client("s3", region_name=transfer["region"])
    prefix = "output/" + transfer["prefix"] + "/results/"
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=transfer["bucket"], Prefix=prefix):
        for obj in page.get("Contents", []):
            relative = Path(obj["Key"].removeprefix(prefix))
            assert not relative.is_absolute() and ".." not in relative.parts
            target = root / relative
            data = s3.get_object(Bucket=transfer["bucket"], Key=obj["Key"])["Body"].read()
            if target.exists() and (relative.name == "plan.json" or relative.parts[0] == "jobs"):
                assert target.read_bytes() == data
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    progress = {}
    for path in sorted((root / "stages").glob("*/run.json")):
        data = json.loads(path.read_text())
        progress[path.parent.name] = {key: data.get(key) for key in ("status", "actual_calls", "errors", "last")}
    print(json.dumps({"ssm": invocation["Status"], "stages": progress}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("job", "restart", "gdn1024", "rollback", "accept", "collect"))
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--name")
    args = parser.parse_args()
    collect(args.run) if args.action == "collect" else submit(args)
