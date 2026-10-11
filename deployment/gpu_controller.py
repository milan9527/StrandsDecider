"""Start and stop one reusable On-Demand EC2 GPU, preserving its root disk."""

import os
import time
import uuid

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.gpu_state import GpuState, TransitionConflict

INSTANCE_TYPES = ("g6.xlarge", "g6.2xlarge", "g5.xlarge")
CAPACITY_ERRORS = ("InsufficientInstanceCapacity", "InsufficientHostCapacity")


def reconcile(
    store,
    ecs,
    ec2,
    *,
    cluster,
    service,
    owner,
    launch_template,
    subnets,
    instance_types=INSTANCE_TYPES,
    idle_timeout_seconds=1800,
    now=None,
):
    now = int(time.time()) if now is None else now
    state = store.get()
    if state.get("provider") == "sagemaker":
        return {"action": "inactive"}
    if not instance_types or any(kind not in INSTANCE_TYPES for kind in instance_types):
        raise ValueError("Unsupported GPU instance types")
    if idle_timeout_seconds < 0:
        raise ValueError("Idle timeout must be nonnegative")
    generation = state["requested_at"]

    def update(expression, values):
        nonlocal state
        state = store.update(
            expression,
            {**values, ":generation": generation, ":expected": state["desired"]},
            condition="requested_at=:generation AND desired=:expected",
        )
        return state

    def capacity_wait(error):
        update(
            "SET startup_stage=:stage, last_error_code=:code, last_error_at=:now",
            {
                ":stage": "waiting_capacity",
                ":code": error.response["Error"]["Code"],
                ":now": now,
            },
        )

    if (
        state.get("instance_options") != list(instance_types)
        or state.get("idle_timeout_seconds") != idle_timeout_seconds
    ):
        update(
            "SET instance_options=:types, idle_timeout_seconds=:idle",
            {":types": list(instance_types), ":idle": idle_timeout_seconds},
        )

    if state["desired"] == "running" and int(state.get("busy_until", 0)) <= now:
        idle = (
            idle_timeout_seconds > 0
            and state["phase"] == "ready"
            and int(state["last_activity"]) <= now - idle_timeout_seconds
        )
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
            type_index = int(state["launch_type"]) % len(instance_types)
            instance_type = instance_types[type_index]
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
                if error.response["Error"]["Code"] not in CAPACITY_ERRORS:
                    raise
                capacity_wait(error)
                # Only definite failures may move to another AZ or instance type.
                # Ambiguous failures keep exactly the same idempotency token and request.
                if index + 1 == len(subnets):
                    update(
                        "SET launch_subnet=:first, launch_type=:type, launch_token=:token",
                        {
                            ":first": 0,
                            ":type": (type_index + 1) % len(instance_types),
                            ":token": uuid.uuid4().hex,
                        },
                    )
                else:
                    update("SET launch_subnet=:next", {":next": index + 1})
                continue
            update(
                "SET instance_id=:id, instance_type=:type, instance_state=:status, "
                "instance_count=:one, startup_stage=:stage REMOVE last_error_code, last_error_at",
                {
                    ":id": launched["InstanceId"],
                    ":type": instance_type,
                    ":status": "pending",
                    ":one": 1,
                    ":stage": "booting",
                },
            )
            return {"action": "creating"}
        return {"action": "waiting_for_capacity"}

    if instance["State"]["Name"] == "stopped":
        if instance["InstanceType"] not in instance_types:
            ec2.modify_instance_attribute(
                InstanceId=instance["InstanceId"], InstanceType={"Value": instance_types[0]}
            )
            update("SET instance_type=:type", {":type": instance_types[0]})
            return {"action": "resizing_stopped_instance"}
        try:
            ec2.start_instances(InstanceIds=[instance["InstanceId"]])
        except ClientError as error:
            if error.response["Error"]["Code"] not in CAPACITY_ERRORS:
                raise
            capacity_wait(error)
            # A stopped EBS-backed instance can change GPU type without replacing its disk.
            # Only a definite capacity rejection permits this change; ambiguous errors retry
            # the same instance/type. The next scheduled tick attempts the new type.
            next_type = instance_types[
                (instance_types.index(instance["InstanceType"]) + 1) % len(instance_types)
            ]
            if next_type != instance["InstanceType"]:
                ec2.modify_instance_attribute(
                    InstanceId=instance["InstanceId"], InstanceType={"Value": next_type}
                )
            update("SET instance_type=:type", {":type": next_type})
            return {"action": "waiting_for_capacity"}
        update(
            "SET phase=:phase, instance_state=:status, instance_count=:one, "
            "startup_stage=:stage REMOVE endpoint, last_error_code, last_error_at",
            {":phase": "starting", ":status": "pending", ":one": 1, ":stage": "booting"},
        )
        return {"action": "resuming"}
    if instance["State"]["Name"] != "running":
        update(
            "SET startup_stage=:stage REMOVE last_error_code, last_error_at",
            {":stage": "booting"},
        )
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
        expression += " REMOVE startup_stage, last_error_code, last_error_at"
        update(expression, values)
        return {"action": "ready"}
    expression = "SET phase=:starting, startup_stage=:stage"
    values = {":starting": "starting", ":stage": "loading_model"}
    if state["phase"] != "starting":
        expression += ", starting_at=:now"
        values[":now"] = now
    expression += " REMOVE endpoint, last_error_code, last_error_at"
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
            instance_types=tuple(
                os.getenv("GPU_INSTANCE_TYPES", ",".join(INSTANCE_TYPES)).split(",")
            ),
            idle_timeout_seconds=int(os.getenv("GPU_IDLE_TIMEOUT_SECONDS", "1800")),
        )
    except TransitionConflict:
        return {"action": "state_changed"}
