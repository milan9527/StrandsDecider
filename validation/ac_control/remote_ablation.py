"""Stage frozen answer-free experiments; collect progress and raw evidence."""

import argparse
import hashlib
import io
import json
import shlex
import tarfile
from pathlib import Path

import boto3

HERE = Path(__file__).resolve().parent


def start(run, state):
    if (run / "transfer.json").exists():
        raise FileExistsError("Transfer already exists")
    files = {name: run / name for name in ("experiments.json", "plan.json")}
    files.update({name: run / "sources" / name
                  for name in ("run_ablation.py", "ablation_protocol.py", "run_resident.py")})
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, path in files.items():
            data = path.read_bytes()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    prefix = "ac-control/" + run.name
    s3 = boto3.client("s3", region_name=state["region"])
    s3.put_object(Bucket=state["bucket"], Key="input/" + prefix + "/input.tar.gz",
                  Body=buffer.getvalue(), ServerSideEncryption="AES256")
    transfer = {
        **{k: state[k] for k in ("region", "bucket", "instance", "secret_arn")},
        "prefix": prefix, "remote": "/opt/decider-open-models/ac-control/" + run.name,
        "input_archive_sha256": hashlib.sha256(buffer.getvalue()).hexdigest(),
        "transferred_files": list(files), "commands": [],
    }
    remote = shlex.quote(transfer["remote"])
    script = f"""set -eu
mkdir -p {remote}
aws s3 cp {shlex.quote('s3://' + transfer['bucket'] + '/input/' + prefix + '/input.tar.gz')} {remote}/input.tar.gz --only-show-errors
tar -xzf {remote}/input.tar.gz -C {remote}
"""
    submit(run, transfer, "probe", script)


def submit(run, transfer, phase, prelude=""):
    remote = shlex.quote(transfer["remote"])
    uri = shlex.quote("s3://" + transfer["bucket"] + "/output/" + transfer["prefix"] + "/results")
    script = prelude + f"""
set +e
python3 {remote}/run_ablation.py --experiments {remote}/experiments.json --plan {remote}/plan.json --output {remote}/results --phase {phase} --secret-arn {shlex.quote(transfer['secret_arn'])} --s3-output {uri}
run_status=$?
aws s3 sync {remote}/results {uri} --only-show-errors
upload_status=$?
if [ "$upload_status" -ne 0 ]; then exit "$upload_status"; fi
exit "$run_status"
"""
    response = boto3.client("ssm", region_name=transfer["region"]).send_command(
        InstanceIds=[transfer["instance"]], DocumentName="AWS-RunShellScript",
        Parameters={"commands": [script], "executionTimeout": ["7200"]},
        Comment="AC prompt comparison: existing Decider Liquid H2O; inference only",
    )
    transfer["commands"].append({"phase": phase, "id": response["Command"]["CommandId"]})
    (run / "transfer.json").write_text(json.dumps(transfer, indent=2) + "\n")
    print(json.dumps(transfer["commands"][-1]))


def collect(run, transfer):
    command = transfer["commands"][-1]
    response = boto3.client("ssm", region_name=transfer["region"]).get_command_invocation(
        CommandId=command["id"], InstanceId=transfer["instance"],
    )
    data = {k: response.get(k) for k in (
        "Status", "ResponseCode", "ExecutionStartDateTime", "ExecutionEndDateTime",
        "StandardOutputContent", "StandardErrorContent",
    )}
    (run / (command["phase"] + "_ssm.json")).write_text(json.dumps(data, indent=2) + "\n")
    s3 = boto3.client("s3", region_name=transfer["region"])
    prefix = "output/" + transfer["prefix"] + "/results/"
    count = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=transfer["bucket"], Prefix=prefix):
        for item in page.get("Contents", []):
            relative = Path(item["Key"].removeprefix(prefix))
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Unsafe path")
            target = run / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(transfer["bucket"], item["Key"], str(target))
            count += 1
    progress_path = run / (command["phase"] + "_progress.json")
    progress = json.loads(progress_path.read_text()) if progress_path.exists() else None
    print(json.dumps({"ssm": data, "files": count, "progress": progress}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "formal", "collect"])
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--deployment-state", type=Path,
                        default=HERE.parents[2] / "StrandsDeciderVLLM/.deployment/state.json")
    args = parser.parse_args()
    if args.action == "start":
        start(args.run, json.loads(args.deployment_state.read_text()))
    else:
        transfer = json.loads((args.run / "transfer.json").read_text())
        if args.action == "formal":
            submit(args.run, transfer, "formal")
        else:
            collect(args.run, transfer)
