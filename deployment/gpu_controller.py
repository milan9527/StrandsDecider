"""Scheduled reconciler. Only this function changes Spot capacity or ECS desired count."""

import os
import time

import boto3

from app.gpu_state import GpuState, TransitionConflict


def reconcile(store, ecs, autoscaling, ec2, *, cluster, service, group, now=None):
    now = int(time.time()) if now is None else now
    state = store.get()
    generation = state["requested_at"]

    def update(expression, values):
        return store.update(
            expression,
            {**values, ":generation": generation, ":expected": state["desired"]},
            condition="requested_at=:generation AND desired=:expected",
        )

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
    capacity = autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[group])[
        "AutoScalingGroups"
    ][0]
    count = len(capacity["Instances"])
    if state["desired"] == "stopped":
        if int(state.get("busy_until", 0)) > now:
            return {"action": "waiting_for_inference"}
        if description["desiredCount"] != 0:
            ecs.update_service(cluster=cluster, service=service, desiredCount=0)
            return {"action": "draining_tasks"}
        if description["runningCount"] or description["pendingCount"]:
            return {"action": "draining_tasks"}
        if capacity["DesiredCapacity"] != 0:
            autoscaling.set_desired_capacity(
                AutoScalingGroupName=group, DesiredCapacity=0, HonorCooldown=False
            )
            return {"action": "stopping"}
        phase = (
            "stopping"
            if count
            else ("error" if state.get("stop_reason") == "startup_timeout" else "stopped")
        )
        update(
            "SET phase=:phase, instance_count=:count REMOVE endpoint",
            {":phase": phase, ":count": count},
        )
        return {"action": phase}

    if capacity["DesiredCapacity"] != 1:
        autoscaling.set_desired_capacity(
            AutoScalingGroupName=group, DesiredCapacity=1, HonorCooldown=False
        )
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
        instance = ec2.describe_instances(InstanceIds=[container["ec2InstanceId"]])["Reservations"][
            0
        ]["Instances"][0]
        # A hard guard: this service must never silently use On-Demand capacity.
        if instance.get("InstanceLifecycle") != "spot":
            raise RuntimeError("GPU capacity is not Spot")
        endpoint = f"http://{instance['PrivateIpAddress']}:8099"
        expression = (
            "SET phase=:ready, endpoint=:endpoint, instance_count=:count, instance_type=:type"
        )
        values = {
            ":ready": "ready",
            ":endpoint": endpoint,
            ":count": count,
            ":type": instance["InstanceType"],
        }
        if state["phase"] != "ready":
            expression += ", last_activity=:now"
            values[":now"] = now
        update(expression, values)
        return {"action": "ready"}
    expression = "SET phase=:starting, instance_count=:count REMOVE endpoint"
    values = {":starting": "starting", ":count": count}
    if state["phase"] != "starting":
        expression = "SET phase=:starting, instance_count=:count, starting_at=:now REMOVE endpoint"
        values[":now"] = now
    update(expression, values)
    return {"action": "starting"}


def handler(event, context):
    store = GpuState(boto3.client("dynamodb"), os.environ["GPU_STATE_TABLE"])
    try:
        return reconcile(
            store,
            boto3.client("ecs"),
            boto3.client("autoscaling"),
            boto3.client("ec2"),
            cluster=os.environ["GPU_CLUSTER"],
            service=os.environ["GPU_SERVICE"],
            group=os.environ["GPU_ASG"],
        )
    except TransitionConflict:
        return {"action": "state_changed"}
