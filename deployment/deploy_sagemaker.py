"""Build a thin adapter over the verified CUDA image and deploy SageMaker control resources."""

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from app.gpu_state import GpuState
from deployment.sagemaker_infrastructure import template


def activate(session, base_stack, outputs):
    """Switch only after the old compute and its scheduled controller are stopped."""
    cf = session.client("cloudformation")
    ec2 = session.client("ec2")
    reservations = ec2.describe_instances(
        Filters=[
            {"Name": "tag:DeciderGpuStack", "Values": [base_stack + "-gpu"]},
            {"Name": "instance-state-name", "Values": ["pending", "running", "stopping"]},
        ]
    )["Reservations"]
    if reservations:
        raise RuntimeError("Stop the existing EC2 GPU before activating SageMaker")
    old = cf.describe_stacks(StackName=base_stack + "-gpu")["Stacks"][0]
    old_outputs = {row["OutputKey"]: row["OutputValue"] for row in old["Outputs"]}
    service = session.client("ecs").describe_services(
        cluster=base_stack, services=[old_outputs["ServiceName"]]
    )["services"][0]
    if any(service[key] for key in ("desiredCount", "runningCount", "pendingCount")):
        raise RuntimeError("Stop the existing ECS model tasks first")
    schedule = cf.describe_stack_resource(
        StackName=base_stack + "-gpu", LogicalResourceId="Schedule"
    )["StackResourceDetail"]["PhysicalResourceId"]
    if session.client("events").describe_rule(Name=schedule)["State"] != "DISABLED":
        raise RuntimeError("Disable the old EC2 controller before activating SageMaker")
    store = GpuState(session.client("dynamodb"), outputs["StateTableName"])
    if store.get().get("provider") != "sagemaker":
        store.update(
            "SET provider=:provider, phase=:off, stop_reason=:empty "
            "REMOVE endpoint, startup_stage, last_error_code, last_error_message",
            {":provider": "sagemaker", ":off": "stopped", ":empty": "", ":now": int(time.time())},
            condition="desired=:off AND busy_until<=:now",
        )
    store.start()
    result = session.client("lambda").invoke(FunctionName=outputs["ControllerName"], Payload=b"{}")
    response = json.loads(result["Payload"].read())
    if result.get("FunctionError"):
        raise RuntimeError(response)
    print(json.dumps(response), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--stack", default="strands-decider-demo")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--base-tag", default="20261009-gpu1")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument(
        "--activate",
        action="store_true",
        help="Switch from the stopped EC2 GPU and start SageMaker",
    )
    args = parser.parse_args()
    session = boto3.Session(region_name=args.region)
    cf = session.client("cloudformation")
    source = cf.describe_stacks(StackName=args.stack)["Stacks"][0]
    outputs = {x["OutputKey"]: x["OutputValue"] for x in source["Outputs"]}
    resources = {
        x["LogicalResourceId"]: x["PhysicalResourceId"]
        for page in cf.get_paginator("list_stack_resources").paginate(StackName=args.stack)
        for x in page["StackResourceSummaries"]
    }
    gpu = cf.describe_stacks(StackName=args.stack + "-gpu")["Stacks"][0]
    gpu_outputs = {x["OutputKey"]: x["OutputValue"] for x in gpu["Outputs"]}
    repository = outputs["ModelRepositoryUri"]
    image = repository + ":" + args.tag
    try:
        existing = cf.describe_stacks(StackName=args.stack + "-sagemaker")["Stacks"][0]
    except cf.exceptions.ClientError as error:
        if "does not exist" not in error.response["Error"]["Message"]:
            raise
        existing = None
    if existing:
        previous = {p["ParameterKey"]: p["ParameterValue"] for p in existing["Parameters"]}
        if previous.get("ModelImage") != image:
            try:
                session.client("sagemaker").describe_endpoint(EndpointName=args.stack + "-decider")
            except ClientError as error:
                if "Could not find endpoint" not in error.response["Error"]["Message"]:
                    raise
            else:
                raise RuntimeError("Stop the SageMaker GPU before changing its model image")
    if not args.skip_build:
        subprocess.run(
            [
                "docker",
                "build",
                "--platform",
                "linux/amd64",
                "--build-arg",
                "MODEL_IMAGE=" + repository + ":" + args.base_tag,
                "-f",
                "deployment/sagemaker.Dockerfile",
                "-t",
                image,
                ".",
            ],
            check=True,
        )
        # ECR credentials go to stdin, never into command arguments or logs.
        token = subprocess.check_output(
            ["aws", "ecr", "get-login-password", "--region", args.region]
        )
        subprocess.run(
            ["docker", "login", "--username", "AWS", "--password-stdin", repository.split("/")[0]],
            input=token,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(["docker", "push", image], check=True)
    account = session.client("sts").get_caller_identity()["Account"]
    values = {
        "VpcId": outputs["VpcId"],
        "SubnetId": resources["Subnet1"],
        "EndpointSecurityGroup": resources["EndpointSecurityGroup"],
        "ModelRepositoryArn": f"arn:aws:ecr:{args.region}:{account}:repository/{args.stack}-model",
        "ModelImage": image,
        "StateTableName": gpu_outputs["StateTableName"],
        "EndpointName": args.stack + "-decider",
        "ModelRevision": hashlib.sha256(args.tag.encode()).hexdigest()[:12],
    }
    options = {
        "StackName": args.stack + "-sagemaker",
        "TemplateBody": json.dumps(template()),
        "Parameters": [{"ParameterKey": k, "ParameterValue": v} for k, v in values.items()],
        "Capabilities": ["CAPABILITY_IAM"],
    }
    try:
        cf.create_stack(**options, Tags=[{"Key": "Project", "Value": "StrandsDecider"}])
    except cf.exceptions.AlreadyExistsException:
        try:
            cf.update_stack(**options)
        except Exception as error:
            if "No updates are to be performed" not in str(error):
                raise
    last = None
    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline:
        stack = cf.describe_stacks(StackName=options["StackName"])["Stacks"][0]
        status = stack["StackStatus"]
        if status != last:
            print(status, flush=True)
            last = status
        if status in ("CREATE_COMPLETE", "UPDATE_COMPLETE"):
            result = {x["OutputKey"]: x["OutputValue"] for x in stack["Outputs"]}
            Path(".deployment/sagemaker-outputs.json").write_text(
                json.dumps(result, indent=2) + "\n"
            )
            print(json.dumps(result), flush=True)
            if args.activate:
                activate(session, args.stack, result)
            return
        if "ROLLBACK" in status or status.endswith("FAILED"):
            raise RuntimeError(status)
        time.sleep(10)
    raise TimeoutError("SageMaker stack did not stabilize")


if __name__ == "__main__":
    main()
