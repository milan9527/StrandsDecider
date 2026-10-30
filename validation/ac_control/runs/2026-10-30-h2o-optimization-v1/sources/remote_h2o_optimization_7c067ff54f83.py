"""Run H2O trials sequentially on the existing GPU host and collect evidence."""

import argparse
import hashlib
import json
import shlex
from pathlib import Path

import boto3


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def collect(run, transfer):
    ssm = boto3.client("ssm", region_name=transfer["region"])
    command = transfer["commands"][-1]
    invocation = ssm.get_command_invocation(CommandId=command["id"], InstanceId=transfer["instance"])
    save(run / (command["variant"] + "_ssm.json"), {k: invocation.get(k) for k in (
        "Status", "ResponseCode", "ExecutionStartDateTime", "ExecutionEndDateTime",
        "StandardOutputContent", "StandardErrorContent",
    )})
    s3 = boto3.client("s3", region_name=transfer["region"])
    prefix = "output/" + transfer["prefix"] + "/results/"
    count = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=transfer["bucket"], Prefix=prefix):
        for item in page.get("Contents", []):
            relative = Path(item["Key"].removeprefix(prefix))
            assert not relative.is_absolute() and ".." not in relative.parts
            target = run / relative
            data = s3.get_object(Bucket=transfer["bucket"], Key=item["Key"])["Body"].read()
            if relative.as_posix() in ("plan.json", "payload.json", "cases.json") and target.exists():
                assert target.read_bytes() == data, "Frozen input changed remotely"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            count += 1
    variants = {}
    for path in sorted((run / "variants").glob("*/run.json")):
        metadata = json.loads(path.read_text())
        variants[path.parent.name] = {k: metadata.get(k) for k in ("status", "actual_calls", "errors", "last")}
    print(json.dumps({"ssm_status": invocation["Status"], "files": count,
                      "variants": variants}, ensure_ascii=False, indent=2))


def submit(args, transfer):
    ssm = boto3.client("ssm", region_name=transfer["region"])
    previous = transfer["commands"][-1]
    state = ssm.get_command_invocation(CommandId=previous["id"], InstanceId=transfer["instance"])["Status"]
    if state not in ("Success", "Failed", "Cancelled", "TimedOut"):
        raise RuntimeError("Previous command is still active; refusing overlapping work")
    assert args.variant and args.variant not in [c["variant"] for c in transfer["commands"]]
    assert "/" not in args.variant and ".." not in args.variant
    root = transfer["remote"]
    s3 = boto3.client("s3", region_name=transfer["region"])
    controller = Path(__file__).resolve().parents[2] / "deployment/open_models/tune_h2o_runtime.py"
    key = "input/" + transfer["prefix"] + "/controller-" + args.variant + ".py"
    s3.put_object(Bucket=transfer["bucket"], Key=key, Body=controller.read_bytes(),
                  ServerSideEncryption="AES256")
    uri = "s3://" + transfer["bucket"] + "/output/" + transfer["prefix"] + "/results"
    script = [
        "set -eu",
        "trap " + shlex.quote("aws s3 sync " + shlex.quote(root) + " " + shlex.quote(uri)
                             + " --only-show-errors") + " EXIT",
        "aws s3 cp " + shlex.quote("s3://" + transfer["bucket"] + "/" + key) + " "
        + shlex.quote(root + "/tune_h2o_runtime.py") + " --only-show-errors",
    ]
    if args.action == "trial":
        script.append(shlex.join([
            "python3", root + "/tune_h2o_runtime.py", "configure", "--root", root,
            "--variant", args.variant, "--sequences", str(args.sequences),
            "--graphs", args.graphs, "--gdn-tokens", str(args.gdn_tokens),
            "--timeout", str(args.timeout),
        ]))
    if args.action in ("trial", "benchmark"):
        invocation = shlex.join([
            "python3", root + "/run_h2o_optimization.py", "--run", root, "--variant", args.variant,
            "--attention", args.attention, "--phase", args.phase, "--s3-output", uri,
        ])
        restore = shlex.join(["python3", root + "/tune_h2o_runtime.py", "rollback", "--root", root])
        script.append("if " + invocation + "; then :; else trial_status=$?; "
                      + restore + '; exit "$trial_status"; fi')
    elif args.action in ("accept", "rollback"):
        script.append(shlex.join(["python3", root + "/tune_h2o_runtime.py", args.action, "--root", root]))
    response = ssm.send_command(
        InstanceIds=[transfer["instance"]], DocumentName="AWS-RunShellScript",
        Parameters={"commands": ["\n".join(script)], "executionTimeout": ["2400"]},
        Comment="H2O AC optimization: serial trial with rollback, preserve other resident services",
    )
    transfer["commands"].append({
        "variant": args.variant, "action": args.action, "id": response["Command"]["CommandId"],
        "controller_sha256": hashlib.sha256(controller.read_bytes()).hexdigest(),
        "controller_input_key": key,
    })
    save(args.run / "transfer.json", transfer)
    print(json.dumps(transfer["commands"][-1]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["collect", "trial", "benchmark", "accept", "rollback"])
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--variant")
    parser.add_argument("--sequences", type=int, choices=[1, 2, 4], default=1)
    parser.add_argument("--graphs", choices=["off", "on"], default="off")
    parser.add_argument("--gdn-tokens", type=int, choices=[0, 2048, 4096], default=0)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--attention", choices=["bidirectional", "causal"], default="bidirectional")
    parser.add_argument("--phase", choices=["all", "performance", "quality"], default="all")
    args = parser.parse_args()
    transfer = json.loads((args.run / "transfer.json").read_text())
    if args.action == "collect":
        collect(args.run, transfer)
    else:
        submit(args, transfer)
