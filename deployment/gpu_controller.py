"""Start and stop one reusable On-Demand EC2 GPU, preserving its root disk."""

import os
import time
import uuid

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.gpu_state import GpuState, TransitionConflict

INSTANCE_TYPES = ("g6.xlarge", "g6.2xlarge", "g5.xlarge")


def reconcile(store, ecs, ec2, *, cluster, service, owner, launch_template, subnets, now=None):
    now = int(time.time()) if now is None else now
    state = store.get()
    generation = state["requested_at"]

    def update(expression, values):
        nonlocal state
        state = store.update(
            expression,
            {**values, ":generation": generation, ":expected": state["desired"]},
            condition="requested_at=:generation AND desired=:expected",
        )
        return state

    if state["desired"] == "running" and int(state.get("busy_until", 0)) <= now:
        idle = state["phase"] == "ready" and int(state["last_activity"]) <= now - 1800
        timed_out = (
            state["phase"] == "starting" and int(state.get("starting_at", now)) <= now - 1200
        )
        if idle or timed_out:
            try:
                state = store.update(
                    "SET desired=:off, phase=:stopping, stop_reason=:reason REMOVE endpoint",
                    {
                        ":off": "stopped",
                        ":stopping": "stopping",
                        ":reason": "idle" if idle else "startup_timeout",
                        ":run": "running",
                        ":generation": generation,
                        ":now": now,
                        ":activity": state["last_activity"],
                    },
                    condition="desired=:run AND requested_at=:generation AND busy_until<=:now AND last_activity=:activity",
                )
            except TransitionConflict:
                return {"action": "activity_changed"}

    description = ecs.describe_services(cluster=cluster, services=[service])["services"][0]
    reservations = ec2.describe_instances(
        Filters=[
            {"Name": "tag:DeciderGpuStack", "Values": [owner]},
            {
                "Name": "instance-state-name",
                "Values": ["pending", "running", "stopping", "stopped"],
            },
        ]
    )["Reservations"]
    instances = [instance for group in reservations for instance in group["Instances"]]
    if len(instances) > 1:
        raise RuntimeError("More than one managed GPU exists; refusing to create more capacity")
    instance = instances[0] if instances else None
    if instance:
        if (
            instance.get("InstanceLifecycle") == "spot"
            or instance["InstanceType"] not in INSTANCE_TYPES
        ):
            raise RuntimeError("Expected one supported On-Demand GPU")
        update(
            "SET instance_id=:id, instance_type=:type, instance_state=:status, instance_count=:count",
            {
                ":id": instance["InstanceId"],
                ":type": instance["InstanceType"],
                ":status": instance["State"]["Name"],
                ":count": 0 if instance["State"]["Name"] == "stopped" else 1,
            },
        )

    if state["desired"] == "stopped":
        if int(state.get("busy_until", 0)) > now:
            return {"action": "waiting_for_inference"}
        if description["desiredCount"] != 0:
            ecs.update_service(cluster=cluster, service=service, desiredCount=0)
            return {"action": "draining_tasks"}
        if description["runningCount"] or description["pendingCount"]:
            return {"action": "draining_tasks"}
        if instance and instance["State"]["Name"] != "stopped":
            if instance["State"]["Name"] == "running":
                ec2.stop_instances(InstanceIds=[instance["InstanceId"]])
            update("SET phase=:phase REMOVE endpoint", {":phase": "stopping"})
            return {"action": "stopping"}
        phase = "error" if state.get("stop_reason") == "startup_timeout" else "stopped"
        update(
            "SET phase=:phase, instance_count=:zero REMOVE endpoint",
            {":phase": phase, ":zero": 0},
        )
        return {"action": phase}

    if not instance:
        # If a known instance was externally terminated, permit a fresh launch.
        if state.get("instance_id"):
            known = ec2.describe_instances(InstanceIds=[state["instance_id"]])["Reservations"]
            known = [item for group in known for item in group["Instances"]]
            if not known or known[0]["State"]["Name"] != "terminated":
                return {"action": "waiting_for_instance"}
            update(
                "SET instance_count=:zero REMOVE instance_id, launch_token, launch_subnet, launch_type",
                {":zero": 0},
            )
        update(
            "SET launch_token=if_not_exists(launch_token,:token), "
            "launch_subnet=if_not_exists(launch_subnet,:first), "
            "launch_type=if_not_exists(launch_type,:first)",
            {":token": uuid.uuid4().hex, ":first": 0},
        )
        # Bound each invocation; the next scheduled tick resumes from the saved choice.
        for _ in range(3):
            index = int(state["launch_subnet"]) % len(subnets)
            type_index = int(state["launch_type"]) % len(INSTANCE_TYPES)
            instance_type = INSTANCE_TYPES[type_index]
            try:
                launched = ec2.run_instances(
                    LaunchTemplate={"LaunchTemplateId": launch_template, "Version": "$Latest"},
                    SubnetId=subnets[index],
                    InstanceType=instance_type,
                    MinCount=1,
                    MaxCount=1,
                    ClientToken=state["launch_token"],
                )["Instances"][0]
            except ClientError as error:
                if error.response["Error"]["Code"] not in (
                    "InsufficientInstanceCapacity",
                    "InsufficientHostCapacity",
                ):
                    raise
                # Only definite failures may move to another AZ or instance type.
                # Ambiguous failures keep exactly the same idempotency token and request.
                if index + 1 == len(subnets):
                    update(
                        "SET launch_subnet=:first, launch_type=:type, launch_token=:token",
                        {
                            ":first": 0,
                            ":type": (type_index + 1) % len(INSTANCE_TYPES),
                            ":token": uuid.uuid4().hex,
                        },
                    )
                else:
                    update("SET launch_subnet=:next", {":next": index + 1})
                continue
            update(
                "SET instance_id=:id, instance_type=:type, instance_state=:status, instance_count=:one",
                {
                    ":id": launched["InstanceId"],
                    ":type": instance_type,
                    ":status": "pending",
                    ":one": 1,
                },
            )
            return {"action": "creating"}
        return {"action": "waiting_for_capacity"}

    if instance["State"]["Name"] == "stopped":
        ec2.start_instances(InstanceIds=[instance["InstanceId"]])
        update(
            "SET phase=:phase, instance_state=:status, instance_count=:one REMOVE endpoint",
            {":phase": "starting", ":status": "pending", ":one": 1},
        )
        return {"action": "resuming"}
    if instance["State"]["Name"] != "running":
        return {"action": "starting"}
    if description["desiredCount"] != 1:
        ecs.update_service(cluster=cluster, service=service, desiredCount=1)
    tasks = ecs.list_tasks(cluster=cluster, serviceName=service, desiredStatus="RUNNING")[
        "taskArns"
    ]
    healthy = []
    if tasks:
        healthy = [
            task
            for task in ecs.describe_tasks(cluster=cluster, tasks=tasks)["tasks"]
            if task["lastStatus"] == "RUNNING"
            and task.get("healthStatus") == "HEALTHY"
            and task["taskDefinitionArn"] == description["taskDefinition"]
        ]
    if healthy:
        container = ecs.describe_container_instances(
            cluster=cluster, containerInstances=[healthy[0]["containerInstanceArn"]]
        )["containerInstances"][0]
        if container["ec2InstanceId"] != instance["InstanceId"]:
            raise RuntimeError("The model task is not on the managed GPU")
        expression = "SET phase=:ready, endpoint=:endpoint"
        values = {":ready": "ready", ":endpoint": f"http://{instance['PrivateIpAddress']}:8099"}
        if state["phase"] != "ready":
            expression += ", last_activity=:now"
            values[":now"] = now
        update(expression, values)
        return {"action": "ready"}
    expression = "SET phase=:starting REMOVE endpoint"
    values = {":starting": "starting"}
    if state["phase"] != "starting":
        expression = "SET phase=:starting, starting_at=:now REMOVE endpoint"
        values[":now"] = now
    update(expression, values)
    return {"action": "starting"}


def handler(event, context):
    config = Config(connect_timeout=3, read_timeout=12, retries={"max_attempts": 2})
    store = GpuState(boto3.client("dynamodb", config=config), os.environ["GPU_STATE_TABLE"])
    try:
        return reconcile(
            store,
            boto3.client("ecs", config=config),
            boto3.client("ec2", config=config),
            cluster=os.environ["GPU_CLUSTER"],
            service=os.environ["GPU_SERVICE"],
            owner=os.environ["GPU_OWNER"],
            launch_template=os.environ["GPU_LAUNCH_TEMPLATE"],
            subnets=[subnet for subnet in os.environ["GPU_SUBNETS"].split(",") if subnet],
        )
    except TransitionConflict:
        return {"action": "state_changed"}
