from unittest.mock import MagicMock

import boto3
import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from moto import mock_aws

from app.gpu_state import GpuState, TransitionConflict
from app.main import app
from deployment.deploy_gpu import require_released
from deployment.gpu_controller import reconcile
from deployment.gpu_infrastructure import template


def test_infrastructure_uses_reusable_ondemand_gpu_and_private_cache():
    resources = template()["Resources"]
    assert not any(
        item["Type"] == "AWS::AutoScaling::AutoScalingGroup" for item in resources.values()
    )
    launch = resources["LaunchTemplate"]["Properties"]["LaunchTemplateData"]
    assert launch["InstanceType"] == "g6.xlarge"
    assert "InstanceMarketOptions" not in launch
    assert launch["BlockDeviceMappings"][0]["Ebs"]["DeleteOnTermination"] is True
    assert launch["BlockDeviceMappings"][0]["Ebs"]["VolumeSize"] == 80
    assert launch["MetadataOptions"]["HttpTokens"] == "required"
    ingress = resources["GpuSecurityGroup"]["Properties"]["SecurityGroupIngress"]
    assert all("SourceSecurityGroupId" in rule and "CidrIp" not in rule for rule in ingress)
    task = resources["GpuTask"]["Properties"]
    assert task["Volumes"][0]["Host"]["SourcePath"] == "/opt/decider-cache"
    assert resources["GpuService"]["Properties"]["LaunchType"] == "EC2"
    assert "ec2:TerminateInstances" not in str(resources["ControllerRole"])
    assert "ec2:StopInstances" in str(resources["ControllerRole"])


def test_gpu_deployment_blocks_running_instances_but_allows_stopped_cache():
    ecs, ec2 = clients()
    ddb, asg = MagicMock(), MagicMock()
    stack = {
        "StackName": "owner",
        "Outputs": [
            {"OutputKey": k, "OutputValue": v}
            for k, v in {"StateTableName": "state", "ServiceName": "service"}.items()
        ],
        "Parameters": [{"ParameterKey": "ClusterName", "ParameterValue": "cluster"}],
    }
    ddb.get_item.return_value = {"Item": {"desired": {"S": "stopped"}, "phase": {"S": "stopped"}}}
    require_released(stack, asg, ecs, ddb, ec2)
    ec2.describe_instances.return_value = {"Reservations": [{"Instances": [instance()]}]}
    with pytest.raises(RuntimeError, match="Release the GPU"):
        require_released(stack, asg, ecs, ddb, ec2)


@pytest.fixture
def store():
    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-2")
        client.create_table(
            TableName="gpu-state",
            BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
        )
        state = GpuState(client, "gpu-state")
        state.get()
        yield state


def ready(store, now=100):
    store.start(now=now)
    store.update(
        "SET phase=:ready, endpoint=:url",
        {":ready": "ready", ":url": "http://10.78.1.2:8099"},
    )


def instance(status="running"):
    return {
        "InstanceId": "i-demo",
        "InstanceType": "g6.xlarge",
        "State": {"Name": status},
        "PrivateIpAddress": "10.78.1.2",
    }


def clients(desired=0, running=0, pending=0, instance=None):
    ecs, ec2 = MagicMock(), MagicMock()
    ecs.describe_services.return_value = {
        "services": [
            {
                "desiredCount": desired,
                "runningCount": running,
                "pendingCount": pending,
                "taskDefinition": "definition",
            }
        ]
    }
    ecs.list_tasks.return_value = {"taskArns": []}
    ec2.describe_instances.return_value = {
        "Reservations": [{"Instances": [instance]}] if instance else []
    }
    ec2.run_instances.return_value = {"Instances": [{"InstanceId": "i-demo"}]}
    return ecs, ec2


def tick(store, aws, now):
    return reconcile(
        store,
        *aws,
        cluster="cluster",
        service="service",
        owner="owner",
        launch_template="lt-demo",
        subnets=["subnet-a", "subnet-b"],
        now=now,
    )


def test_start_is_idempotent_and_never_starts_while_releasing(store):
    first = store.start(now=100)
    assert store.start(now=101) == first
    store.stop(now=102)
    with pytest.raises(TransitionConflict):
        store.start(now=103)


def test_lease_excludes_other_inference_and_stop_blocks_new_requests(store):
    ready(store)
    token, endpoint = store.acquire(120, now=101)
    assert endpoint == "http://10.78.1.2:8099"
    with pytest.raises(TransitionConflict):
        store.acquire(120, now=102)
    store.stop(now=103)
    store.release(token, now=104)
    with pytest.raises(TransitionConflict):
        store.acquire(120, now=105)


def test_expired_worker_cannot_release_a_new_lease(store):
    ready(store)
    old, _ = store.acquire(10, now=101)
    new, _ = store.acquire(10, now=112)
    store.release(old, now=113)
    assert store.get()["lease_token"] == new
    assert store.get()["busy_until"] == 122


def test_failed_request_keeps_shutdown_grace_period(store):
    ready(store)
    token, _ = store.acquire(140, now=101)
    store.release(token, cooldown=90, now=110)
    store.stop(now=111)
    aws = clients(desired=1, running=1, instance=instance())
    assert tick(store, aws, 150)["action"] == "waiting_for_inference"
    aws[0].update_service.assert_not_called()
    aws[1].stop_instances.assert_not_called()


def test_first_start_creates_only_one_ondemand_instance(store):
    store.start(now=100)
    aws = clients()
    assert tick(store, aws, 101)["action"] == "creating"
    call = aws[1].run_instances.call_args.kwargs
    assert call["MinCount"] == call["MaxCount"] == 1
    assert "InstanceMarketOptions" not in call
    assert store.get()["instance_id"] == "i-demo"


def test_definite_capacity_failure_moves_to_next_az_with_persisted_token(store):
    store.start(now=100)
    aws = clients()
    aws[1].run_instances.side_effect = [
        ClientError({"Error": {"Code": "InsufficientInstanceCapacity"}}, "RunInstances"),
        {"Instances": [{"InstanceId": "i-demo"}]},
    ]
    assert tick(store, aws, 101)["action"] == "creating"
    first, second = [call.kwargs for call in aws[1].run_instances.call_args_list]
    assert first["SubnetId"] == "subnet-a" and second["SubnetId"] == "subnet-b"
    assert first["ClientToken"] == second["ClientToken"]


def test_next_instance_type_uses_new_token_only_after_all_azs_fail(store):
    store.start(now=100)
    aws = clients()
    failure = ClientError({"Error": {"Code": "InsufficientInstanceCapacity"}}, "RunInstances")
    aws[1].run_instances.side_effect = [failure, failure, {"Instances": [{"InstanceId": "i-demo"}]}]
    assert tick(store, aws, 101)["action"] == "creating"
    first, second, third = [call.kwargs for call in aws[1].run_instances.call_args_list]
    assert first["InstanceType"] == second["InstanceType"] == "g6.xlarge"
    assert third["InstanceType"] == "g6.2xlarge"
    assert third["ClientToken"] != first["ClientToken"]
    assert store.get()["instance_type"] == "g6.2xlarge"


def test_ambiguous_launch_retries_same_token_and_same_az(store):
    store.start(now=100)
    aws = clients()
    aws[1].run_instances.side_effect = TimeoutError("response lost")
    with pytest.raises(TimeoutError):
        tick(store, aws, 101)
    original = aws[1].run_instances.call_args.kwargs
    aws[1].run_instances.side_effect = None
    assert tick(store, aws, 102)["action"] == "creating"
    assert aws[1].run_instances.call_args.kwargs == original


def test_restart_reuses_stopped_instance_without_recreating_disk(store):
    store.start(now=100)
    aws = clients(instance=instance("stopped"))
    assert tick(store, aws, 101)["action"] == "resuming"
    aws[1].start_instances.assert_called_once_with(InstanceIds=["i-demo"])
    aws[1].run_instances.assert_not_called()
    assert store.get()["instance_id"] == "i-demo"


def test_restart_capacity_error_is_visible_and_rotates_type_on_same_instance(store):
    store.start(now=100)
    aws = clients(instance=instance("stopped"))
    aws[1].start_instances.side_effect = ClientError(
        {"Error": {"Code": "InsufficientInstanceCapacity"}}, "StartInstances"
    )
    assert tick(store, aws, 101)["action"] == "waiting_for_capacity"
    state = store.get()
    assert state["startup_stage"] == "waiting_capacity"
    assert state["last_error_code"] == "InsufficientInstanceCapacity"
    assert state["starting_at"] == 100
    assert state["instance_id"] == "i-demo"
    assert state["instance_count"] == 0 and state["instance_state"] == "stopped"
    aws[1].modify_instance_attribute.assert_called_once_with(
        InstanceId="i-demo", InstanceType={"Value": "g6.2xlarge"}
    )
    aws[1].run_instances.assert_not_called()
    aws[1].terminate_instances.assert_not_called()

    next_node = {**instance("stopped"), "InstanceType": "g6.2xlarge"}
    resumed = clients(instance=next_node)
    assert tick(store, resumed, 160)["action"] == "resuming"
    resumed[1].start_instances.assert_called_once_with(InstanceIds=["i-demo"])
    assert store.get()["startup_stage"] == "booting"
    assert "last_error_code" not in store.get()
    assert store.get()["starting_at"] == 100


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("response lost"),
        ClientError({"Error": {"Code": "UnauthorizedOperation"}}, "StartInstances"),
    ],
)
def test_restart_does_not_change_hardware_after_ambiguous_or_permission_error(store, error):
    store.start(now=100)
    aws = clients(instance=instance("stopped"))
    aws[1].start_instances.side_effect = error
    with pytest.raises(type(error)):
        tick(store, aws, 101)
    aws[1].modify_instance_attribute.assert_not_called()
    aws[1].run_instances.assert_not_called()


def test_capacity_timeout_preserves_reason_and_new_request_clears_it(store):
    store.start(now=100)
    aws = clients(instance=instance("stopped"))
    aws[1].start_instances.side_effect = ClientError(
        {"Error": {"Code": "InsufficientInstanceCapacity"}}, "StartInstances"
    )
    tick(store, aws, 101)
    assert tick(store, clients(instance=instance("stopped")), 1300)["action"] == "error"
    state = store.get()
    assert state["desired"] == "stopped" and state["instance_id"] == "i-demo"
    assert state["startup_stage"] == "waiting_capacity"
    assert state["last_error_code"] == "InsufficientInstanceCapacity"
    state = store.start(now=1400)
    assert "last_error_code" not in state and "startup_stage" not in state


def test_capacity_details_are_exposed_to_the_authenticated_ui():
    from app.gpu import public_state

    status = public_state(
        {
            "desired": "running",
            "phase": "starting",
            "startup_stage": "waiting_capacity",
            "last_error_code": "InsufficientInstanceCapacity",
        },
        True,
    )
    assert status["startup_stage"] == "waiting_capacity"
    assert status["last_error_code"] == "InsufficientInstanceCapacity"
    assert status["startup_remaining_seconds"] == 1200


def test_manual_stop_drains_tasks_then_stops_without_termination(store):
    ready(store)
    store.stop(now=110)
    aws = clients(desired=1, running=1, instance=instance())
    assert tick(store, aws, 111)["action"] == "draining_tasks"
    aws[1].stop_instances.assert_not_called()
    assert tick(store, clients(running=1, instance=instance()), 112)["action"] == "draining_tasks"
    aws = clients(instance=instance())
    assert tick(store, aws, 113)["action"] == "stopping"
    aws[1].stop_instances.assert_called_once_with(InstanceIds=["i-demo"])
    aws[1].terminate_instances.assert_not_called()
    assert tick(store, clients(instance=instance("stopped")), 114)["action"] == "stopped"
    assert store.get()["instance_count"] == 0 and store.get()["instance_id"] == "i-demo"


def test_idle_timeout_stops_instance_but_retains_its_identity(store):
    ready(store)
    aws = clients(desired=1, running=1, instance=instance())
    token, _ = store.acquire(120, now=1899)
    assert tick(store, aws, 1901)["action"] == "starting"
    assert store.get()["desired"] == "running"
    store.release(token, now=1902)
    store.update("SET phase=:ready", {":ready": "ready"})
    assert tick(store, aws, 3702)["action"] == "draining_tasks"
    assert store.get()["stop_reason"] == "idle"


def test_startup_timeout_stops_a_failed_instance_without_deleting_disk(store):
    store.start(now=100)
    assert tick(store, clients(instance=instance()), 1300)["action"] == "stopping"
    assert tick(store, clients(instance=instance("stopped")), 1301)["action"] == "error"
    assert store.get()["desired"] == "stopped" and store.get()["instance_id"] == "i-demo"


def test_ready_endpoint_requires_healthy_task_on_the_owned_ondemand_instance(store):
    store.start(now=100)
    aws = clients(desired=1, running=1, instance=instance())
    aws[0].list_tasks.return_value = {"taskArns": ["task"]}
    aws[0].describe_tasks.return_value = {
        "tasks": [
            {
                "lastStatus": "RUNNING",
                "healthStatus": "HEALTHY",
                "taskDefinitionArn": "definition",
                "containerInstanceArn": "container",
            }
        ]
    }
    aws[0].describe_container_instances.return_value = {
        "containerInstances": [{"ec2InstanceId": "i-demo"}]
    }
    assert tick(store, aws, 110)["action"] == "ready"
    assert store.get()["endpoint"] == "http://10.78.1.2:8099"
    assert store.get()["last_activity"] == 110


def test_controller_rejects_unexpected_spot_capacity(store):
    store.start(now=100)
    node = {**instance(), "InstanceLifecycle": "spot"}
    aws = clients(instance=node)
    with pytest.raises(RuntimeError, match="On-Demand"):
        tick(store, aws, 101)
    aws[1].run_instances.assert_not_called()


def test_gpu_controls_require_login_and_manager_and_api_stays_ready(store, monkeypatch):
    monkeypatch.setenv("GPU_MANAGERS", "admin")
    with TestClient(app) as client:
        app.state.gpu = store
        assert client.get("/api/gpu").status_code == 401
        assert client.get("/api/ready").status_code == 200
        client.headers["X-Decider-Client"] = "web"
        assert (
            client.post(
                "/api/auth/login",
                json={
                    "username": "tester",
                    "password": "test-password-with-entropy",
                },
            ).status_code
            == 200
        )
        assert client.post("/api/gpu/start").status_code == 403
        monkeypatch.setenv("GPU_MANAGERS", "tester")
        assert client.post("/api/gpu/start").status_code == 202
        assert client.get("/api/gpu").json()["purchase_option"] == "on-demand"
        assert client.get("/api/health").json()["connected"] is False
        assert client.get("/api/examples").status_code == 200
        body = {
            "mode": "live",
            "state": "hello",
            "questions": {"ok": {"type": "noul", "instructions": "Is this a greeting?"}},
        }
        assert client.post("/api/decide", json=body).status_code == 503
        assert client.post("/api/gpu/stop").status_code == 202
        assert store.get()["desired"] == "stopped"
