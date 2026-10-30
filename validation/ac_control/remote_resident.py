"""Transfer a bounded benchmark to the existing GPU via private S3 and SSM."""

import argparse
import hashlib
import io
import json
import shlex
import tarfile
from pathlib import Path

import boto3

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def start(args, state):
    if not args.source or not args.output:
        raise ValueError("start requires --source and --output")
    args.output.mkdir(parents=True, exist_ok=False)
    files = {
        "requests.json": args.source / "requests.json",
        "plan.json": args.source / "plan.json",
        "run_resident.py": HERE / "run_resident.py",
    }
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, path in files.items():
            content = path.read_bytes()
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    prefix = f"ac-control/{args.output.name}"
    s3 = boto3.client("s3", region_name=state["region"])
    s3.put_object(Bucket=state["bucket"], Key="input/" + prefix + "/input.tar.gz",
                  Body=buffer.getvalue(), ServerSideEncryption="AES256")
    remote = "/opt/decider-open-models/ac-control/" + args.output.name
    transfer = {
        "region": state["region"], "bucket": state["bucket"], "prefix": prefix,
        "instance": state["instance"], "remote": remote, "commands": [],
        "input_archive_sha256": hashlib.sha256(buffer.getvalue()).hexdigest(),
    }
    script = f"""set -eu
mkdir -p {shlex.quote(remote)}
aws s3 cp {shlex.quote('s3://' + state['bucket'] + '/input/' + prefix + '/input.tar.gz')} {shlex.quote(remote + '/input.tar.gz')} --only-show-errors
tar -xzf {shlex.quote(remote + '/input.tar.gz')} -C {shlex.quote(remote)}
"""
    submit(args.output, transfer, script, "probe")


def submit(output, transfer, prelude, phase):
    remote = shlex.quote(transfer["remote"])
    script = prelude + f"""
set +e
python3 {remote}/run_resident.py --requests {remote}/requests.json --plan {remote}/plan.json --output {remote}/results --phase {phase}
run_status=$?
aws s3 sync {remote}/results {shlex.quote('s3://' + transfer['bucket'] + '/output/' + transfer['prefix'] + '/results')} --only-show-errors
upload_status=$?
if [ "$upload_status" -ne 0 ]; then exit "$upload_status"; fi
exit "$run_status"
"""
    ssm = boto3.client("ssm", region_name=transfer["region"])
    response = ssm.send_command(
        InstanceIds=[transfer["instance"]], DocumentName="AWS-RunShellScript",
        Parameters={"commands": [script], "executionTimeout": ["1800"]},
        Comment=f"AC control {phase}: existing resident Liquid and H2O; unchanged inputs",
    )
    transfer["commands"].append({"phase": phase, "id": response["Command"]["CommandId"]})
    (output / "transfer.json").write_text(json.dumps(transfer, indent=2) + "\n")
    print(json.dumps(transfer["commands"][-1]))


def collect(args, transfer):
    command = transfer["commands"][-1]
    response = boto3.client("ssm", region_name=transfer["region"]).get_command_invocation(
        CommandId=command["id"], InstanceId=transfer["instance"],
    )
    public = {
        key: response.get(key) for key in [
            "Status", "ResponseCode", "ExecutionStartDateTime", "ExecutionEndDateTime",
            "StandardOutputContent", "StandardErrorContent",
        ]
    }
    (args.output / f"{command['phase']}_ssm.json").write_text(json.dumps(public, indent=2) + "\n")
    print(json.dumps(public))
    if response["Status"] not in {"Success", "Failed", "TimedOut", "Cancelled"}:
        return
    s3 = boto3.client("s3", region_name=transfer["region"])
    prefix = "output/" + transfer["prefix"] + "/results/"
    count = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=transfer["bucket"], Prefix=prefix):
        for item in page.get("Contents", []):
            relative = Path(item["Key"].removeprefix(prefix))
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Unsafe result path")
            target = args.output / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(transfer["bucket"], item["Key"], str(target))
            count += 1
    print(f"Downloaded {count} evidence files")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "formal", "collect"])
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--deployment-state", type=Path,
                        default=ROOT.parent / "StrandsDeciderVLLM/.deployment/state.json")
    args = parser.parse_args()
    if args.action == "start":
        start(args, json.loads(args.deployment_state.read_text()))
    else:
        transfer = json.loads((args.output / "transfer.json").read_text())
        if args.action == "formal":
            submit(args.output, transfer, "", "formal")
        else:
            collect(args, transfer)
