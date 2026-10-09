"""Create/delete one SageMaker GPU endpoint, with leases and idle shutdown."""

import os
import time

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.gpu_state import GpuState, TransitionConflict


def reconcile(store, sm, *, endpoint_name, endpoint_config, now=None):
    now = int(time.time()) if now is None else now
    state = store.get()
    if state.get("provider") != "sagemaker":
        return {"action": "inactive"}
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

    try:
        endpoint = sm.describe_endpoint(EndpointName=endpoint_name)
    except ClientError as error:
        if (
            error.response["Error"]["Code"] == "ValidationException"
            and "Could not find endpoint" in error.response["Error"]["Message"]
        ):
            endpoint = None
        else:
            raise
    status = endpoint["EndpointStatus"] if endpoint else "Absent"
    update(
        "SET endpoint_status=:status, instance_count=:count",
        {
            ":status": status,
            ":count": sum(
                v.get("CurrentInstanceCount", 0) for v in endpoint.get("ProductionVariants", [])
            )
            if endpoint
            else 0,
        },
    )

    if state["desired"] == "stopped":
        if int(state.get("busy_until", 0)) > now:
            return {"action": "waiting_for_inference"}
        if endpoint:
            if status != "Deleting":
                try:
                    sm.delete_endpoint(EndpointName=endpoint_name)
                except ClientError as error:
                    # SageMaker cannot cancel an in-progress CreateEndpoint.
                    # Keep the stop request and delete after AWS reaches a terminal state.
                    if (
                        error.response["Error"]["Code"] == "ValidationException"
                        and "Cannot update in-progress endpoint"
                        in error.response["Error"]["Message"]
                    ):
                        update("SET phase=:phase REMOVE endpoint", {":phase": "stopping"})
                        return {"action": "waiting_for_creation_before_delete"}
                    raise
            update("SET phase=:phase REMOVE endpoint", {":phase": "stopping"})
            return {"action": "deleting"}
        phase = (
            "error"
            if state.get("stop_reason") in ("startup_timeout", "startup_failed")
            else "stopped"
        )
        update("SET phase=:phase REMOVE endpoint", {":phase": phase})
        return {"action": phase}

    if endpoint is None:
        update("SET startup_stage=:stage", {":stage": "provisioning"})
        try:
            sm.create_endpoint(
                EndpointName=endpoint_name,
                EndpointConfigName=endpoint_config,
                Tags=[{"Key": "Project", "Value": "StrandsDecider"}],
            )
        except ClientError as error:
            # Endpoint names are unique. A lost Create response must never create a second GPU.
            if (
                error.response["Error"]["Code"] == "ValidationException"
                and "already exist" in error.response["Error"]["Message"].lower()
            ):
                return {"action": "creating"}
            update(
                "SET desired=:off, phase=:error, stop_reason=:reason, "
                "last_error_code=:code, last_error_message=:message REMOVE endpoint",
                {
                    ":off": "stopped",
                    ":error": "error",
                    ":reason": "startup_failed",
                    ":code": error.response["Error"]["Code"],
                    ":message": error.response["Error"]["Message"][:700],
                },
            )
            return {"action": "error"}
        return {"action": "creating"}
    if status == "Failed":
        update(
            "SET desired=:off, phase=:phase, stop_reason=:reason, "
            "last_error_code=:code, last_error_message=:message REMOVE endpoint",
            {
                ":off": "stopped",
                ":phase": "stopping",
                ":reason": "startup_failed",
                ":code": "EndpointFailed",
                ":message": endpoint.get("FailureReason", "SageMaker endpoint failed")[:700],
            },
        )
        sm.delete_endpoint(EndpointName=endpoint_name)
        return {"action": "deleting_failed_endpoint"}
    if status == "InService":
        expression = "SET phase=:ready, endpoint=:endpoint"
        values = {":ready": "ready", ":endpoint": "sagemaker://" + endpoint_name}
        if state["phase"] != "ready":
            expression += ", last_activity=:now"
            values[":now"] = now
        expression += " REMOVE startup_stage, last_error_code, last_error_message, last_error_at"
        update(expression, values)
        return {"action": "ready"}
    update(
        "SET phase=:starting, startup_stage=:stage REMOVE endpoint",
        {":starting": "starting", ":stage": "provisioning"},
    )
    return {"action": "starting"}


def handler(event, context):
    config = Config(connect_timeout=3, read_timeout=12, retries={"max_attempts": 2})
    store = GpuState(boto3.client("dynamodb", config=config), os.environ["GPU_STATE_TABLE"])
    try:
        return reconcile(
            store,
            boto3.client("sagemaker", config=config),
            endpoint_name=os.environ["ENDPOINT_NAME"],
            endpoint_config=os.environ["ENDPOINT_CONFIG"],
        )
    except TransitionConflict:
        return {"action": "state_changed"}
