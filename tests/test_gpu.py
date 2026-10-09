from unittest.mock import MagicMock

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from app.gpu_state import GpuState, TransitionConflict
from app.main import app
from deployment.deploy_gpu import require_released
from deployment.gpu_controller import reconcile
from deployment.gpu_infrastructure import template


def test_infrastructure_enforces_spot_only_cost_and_private_access():
    resources = template()["Resources"]
    group = resources["GpuAsg"]["Properties"]
    distribution = group["MixedInstancesPolicy"]["InstancesDistribution"]
    assert distribution["OnDemandBaseCapacity"] == 0
    assert distribution["OnDemandPercentageAboveBaseCapacity"] == 0
    assert float(distribution["SpotMaxPrice"]) <= 0.55
    assert int(group["MinSize"]) == int(group["DesiredCapacity"]) == 0
    assert int(group["MaxSize"]) == 1
    launch = resources["LaunchTemplate"]["Properties"]["LaunchTemplateData"]
    assert launch["BlockDeviceMappings"][0]["Ebs"]["DeleteOnTermination"] is True
    assert launch["MetadataOptions"]["HttpTokens"] == "required"
    ingress = resources["GpuSecurityGroup"]["Properties"]["SecurityGroupIngress"]
    assert all("SourceSecurityGroupId" in rule and "CidrIp" not in rule for rule in ingress)
    assert resources["GpuSubnet3"]["Properties"]["MapPublicIpOnLaunch"] is False


def test_gpu_deployment_rejects_pending_start_and_unreleased_capacity():
    ecs, asg, _ = clients()
    ddb = MagicMock()
    stack = {
        "Outputs": [
            {"OutputKey": key, "OutputValue": value}
            for key, value in {
                "StateTableName": "state",
                "AsgName": "asg",
                "ServiceName": "service",
            }.items()
        ],
        "Parameters": [{"ParameterKey": "ClusterName", "ParameterValue": "cluster"}],
    }
    ddb.get_item.return_value = {"Item": {"desired": {"S": "running"}, "phase": {"S": "starting"}}}
    with pytest.raises(RuntimeError, match="Release the GPU"):
        require_released(stack, asg, ecs, ddb)
    ddb.get_item.return_value = {"Item": {"desired": {"S": "stopped"}, "phase": {"S": "stopped"}}}
    require_released(stack, asg, ecs, ddb)
    asg.describe_auto_scaling_groups.return_value["AutoScalingGroups"][0]["Instances"] = [
        {"InstanceId": "i-still-terminating"}
    ]
    with pytest.raises(RuntimeError, match="Release the GPU"):
        require_released(stack, asg, ecs, ddb)


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


def clients(desired=0, running=0, pending=0, instances=None, capacity=0):
    ecs, asg, ec2 = MagicMock(), MagicMock(), MagicMock()
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
    asg.describe_auto_scaling_groups.return_value = {
        "AutoScalingGroups": [
            {
                "Instances": instances or [],
                "DesiredCapacity": capacity,
            }
        ]
    }
    return ecs, asg, ec2


def tick(store, aws, now):
    return reconcile(store, *aws, cluster="cluster", service="service", group="group", now=now)


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
    aws = clients(desired=1, running=1, capacity=1)
    assert tick(store, aws, 150)["action"] == "waiting_for_inference"
    aws[0].update_service.assert_not_called()
    aws[1].set_desired_capacity.assert_not_called()


def test_start_requests_exactly_one_instance_and_task(store):
    store.start(now=100)
    aws = clients()
    assert tick(store, aws, 101)["action"] == "starting"
    aws[0].update_service.assert_called_once_with(
        cluster="cluster", service="service", desiredCount=1
    )
    aws[1].set_desired_capacity.assert_called_once_with(
        AutoScalingGroupName="group", DesiredCapacity=1, HonorCooldown=False
    )


def test_manual_release_waits_for_task_then_terminates_instance(store):
    ready(store)
    store.stop(now=110)
    aws = clients(desired=1, running=1, capacity=1, instances=[{"InstanceId": "i-demo"}])
    assert tick(store, aws, 111)["action"] == "draining_tasks"
    aws[1].set_desired_capacity.assert_not_called()
    aws = clients(desired=0, running=1, capacity=1, instances=[{"InstanceId": "i-demo"}])
    assert tick(store, aws, 112)["action"] == "draining_tasks"
    aws[1].set_desired_capacity.assert_not_called()
    aws = clients(capacity=1, instances=[{"InstanceId": "i-demo"}])
    assert tick(store, aws, 113)["action"] == "stopping"
    aws[1].set_desired_capacity.assert_called_once_with(
        AutoScalingGroupName="group", DesiredCapacity=0, HonorCooldown=False
    )
    assert tick(store, clients(), 114)["action"] == "stopped"
    assert store.get()["instance_count"] == 0


def test_idle_release_only_after_30_minutes_and_no_active_request(store):
    ready(store)
    aws = clients(desired=1, running=1, capacity=1)
    tick(store, aws, 1899)
    assert store.get()["desired"] == "running"
    # Restore ready after mock reports no healthy task.
    store.update(
        "SET phase=:ready, endpoint=:url", {":ready": "ready", ":url": "http://10.78.1.2:8099"}
    )
    token, _ = store.acquire(120, now=1899)
    assert tick(store, clients(desired=1, running=1, capacity=1), 1901)["action"] == "starting"
    assert store.get()["desired"] == "running"
    store.release(token, now=1902)
    store.update("SET phase=:ready", {":ready": "ready"})
    aws = clients(desired=1, running=1, capacity=1)
    assert tick(store, aws, 3702)["action"] == "draining_tasks"
    assert store.get()["stop_reason"] == "idle"


def test_startup_timeout_releases_failed_spot_capacity(store):
    store.start(now=100)
    assert tick(store, clients(capacity=1), 1300)["action"] == "stopping"
    assert tick(store, clients(), 1301)["action"] == "error"
    assert store.get()["desired"] == "stopped"
    assert store.get()["stop_reason"] == "startup_timeout"


def test_ready_endpoint_only_comes_from_healthy_spot_task(store):
    store.start(now=100)
    aws = clients(desired=1, running=1, capacity=1, instances=[{"InstanceId": "i-demo"}])
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
    aws[2].describe_instances.return_value = {
        "Reservations": [
            {
                "Instances": [
                    {
                        "InstanceLifecycle": "spot",
                        "InstanceType": "g6.xlarge",
                        "PrivateIpAddress": "10.78.1.2",
                    }
                ]
            }
        ]
    }
    assert tick(store, aws, 110)["action"] == "ready"
    assert store.get()["endpoint"] == "http://10.78.1.2:8099"
    assert store.get()["last_activity"] == 110


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
        assert client.get("/api/gpu").json()["purchase_option"] == "spot"
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
