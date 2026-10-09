"""Provision or update GPU resources at zero capacity; requests start them through the API."""

import argparse
import json
import time
from pathlib import Path

import boto3

if __package__:
    from .gpu_infrastructure import template
else:
    from gpu_infrastructure import template


def require_released(stack, autoscaling, ecs, dynamodb):
    """Reject updates that could interrupt inference or reset a running ASG to zero."""
    outputs = {row["OutputKey"]: row["OutputValue"] for row in stack["Outputs"]}
    parameters = {row["ParameterKey"]: row["ParameterValue"] for row in stack["Parameters"]}
    state = dynamodb.get_item(
        TableName=outputs["StateTableName"],
        Key={"pk": {"S": "GPU"}},
        ConsistentRead=True,
    ).get("Item", {})
    group = autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[outputs["AsgName"]])[
        "AutoScalingGroups"
    ][0]
    service = ecs.describe_services(
        cluster=parameters["ClusterName"], services=[outputs["ServiceName"]]
    )["services"][0]
    if (
        state.get("desired", {}).get("S", "stopped") != "stopped"
        or state.get("phase", {}).get("S", "stopped") not in ("stopped", "error")
        or group["DesiredCapacity"]
        or group["Instances"]
        or any(service[key] for key in ("desiredCount", "runningCount", "pendingCount"))
    ):
        raise RuntimeError("Release the GPU and wait for it to stop before updating its stack.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="us-east-2")
    parser.add_argument("--stack", default="strands-decider-demo")
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    cf = boto3.client("cloudformation", region_name=args.region)
    source = cf.describe_stacks(StackName=args.stack)["Stacks"][0]
    outputs = {row["OutputKey"]: row["OutputValue"] for row in source["Outputs"]}
    resources = {}
    for page in cf.get_paginator("list_stack_resources").paginate(StackName=args.stack):
        resources.update(
            {
                row["LogicalResourceId"]: row["PhysicalResourceId"]
                for row in page["StackResourceSummaries"]
            }
        )
    role = boto3.client("iam").get_role(RoleName=resources["ExecutionRole"])["Role"]["Arn"]
    values = {
        "VpcId": outputs["VpcId"],
        "PrivateRouteTableId": resources["PrivateRoutes"],
        "ApiSecurityGroup": resources["TaskSecurityGroup"],
        "EndpointSecurityGroup": resources["EndpointSecurityGroup"],
        "SubnetIds": ",".join(resources[key] for key in ["Subnet1", "Subnet2"]),
        "ClusterName": outputs["ClusterName"],
        "ExecutionRoleArn": role,
        "LogGroupName": outputs["LogGroupName"],
        "ModelRepositoryUri": outputs["ModelRepositoryUri"],
        "GpuImageTag": args.tag,
    }
    name = args.stack + "-gpu"
    options = {
        "StackName": name,
        "TemplateBody": json.dumps(template()),
        "Parameters": [
            {"ParameterKey": key, "ParameterValue": value} for key, value in values.items()
        ],
        "Capabilities": ["CAPABILITY_IAM"],
    }
    try:
        cf.create_stack(**options, Tags=[{"Key": "Project", "Value": "StrandsDecider"}])
    except cf.exceptions.AlreadyExistsException:
        require_released(
            cf.describe_stacks(StackName=name)["Stacks"][0],
            boto3.client("autoscaling", region_name=args.region),
            boto3.client("ecs", region_name=args.region),
            boto3.client("dynamodb", region_name=args.region),
        )
        try:
            cf.update_stack(**options)
        except Exception as error:
            if "No updates are to be performed" not in str(error):
                raise
    previous = None
    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline:
        stack = cf.describe_stacks(StackName=name)["Stacks"][0]
        status = stack["StackStatus"]
        if status != previous:
            print(status, flush=True)
            previous = status
        if status in ("CREATE_COMPLETE", "UPDATE_COMPLETE"):
            record = {
                "stack": name,
                "region": args.region,
                "image_tag": args.tag,
                "outputs": {row["OutputKey"]: row["OutputValue"] for row in stack["Outputs"]},
            }
            Path(".deployment/gpu-outputs.json").write_text(json.dumps(record, indent=2) + "\n")
            print(json.dumps(record), flush=True)
            return
        if "ROLLBACK" in status or status.endswith("FAILED"):
            raise RuntimeError(status)
        time.sleep(15)
    raise TimeoutError("GPU stack did not stabilize")


if __name__ == "__main__":
    main()
