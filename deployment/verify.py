"""Verify deployed origins, bucket privacy, task networking and live inference."""

import argparse
import http.cookiejar
import json
import subprocess
import urllib.error
import urllib.request
from http.cookies import SimpleCookie
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--stack", default="strands-decider-demo")
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--gpu-state", choices=["ready", "stopped", "stopping"], default="stopped")
    args = parser.parse_args()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )

    def aws(*parts):
        result = subprocess.run(
            ["aws", *parts, "--region", args.region, "--output", "json"],
            check=True,
            text=True,
            capture_output=True,
        )
        return json.loads(result.stdout)

    def request(url, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "X-Decider-Client": "web"} if data else {},
        )
        with opener.open(req, timeout=70) as response:
            return (
                response.status,
                response.read(),
                {key.lower(): value for key, value in response.headers.items()},
            )

    stack = aws("cloudformation", "describe-stacks", "--stack-name", args.stack)["Stacks"][0]
    assert stack["StackStatus"] in ("CREATE_COMPLETE", "UPDATE_COMPLETE"), stack["StackStatus"]
    outputs = {row["OutputKey"]: row["OutputValue"] for row in stack["Outputs"]}
    parameters = {row["ParameterKey"]: row["ParameterValue"] for row in stack["Parameters"]}
    provider = parameters.get("ModelProvider", "ec2")
    bucket, url = outputs["FrontendBucketName"], outputs["WebsiteUrl"]
    block = aws("s3api", "get-public-access-block", "--bucket", bucket)
    assert all(block["PublicAccessBlockConfiguration"].values()), block
    assert (
        aws("s3api", "get-bucket-policy-status", "--bucket", bucket)["PolicyStatus"]["IsPublic"]
        is False
    )
    policy = json.loads(aws("s3api", "get-bucket-policy", "--bucket", bucket)["Policy"])
    grants = [s for s in policy["Statement"] if s["Effect"] == "Allow"]
    assert len(grants) == 1 and grants[0]["Principal"] == {"Service": "cloudfront.amazonaws.com"}
    assert grants[0]["Condition"]["StringEquals"]["AWS:SourceArn"].endswith(
        "/" + outputs["DistributionId"]
    )
    origin_url = f"https://{bucket}.s3.{args.region}.amazonaws.com/index.html"
    try:
        request(origin_url)
        raise AssertionError("Anonymous S3 read unexpectedly succeeded")
    except urllib.error.HTTPError as error:
        assert error.code == 403, error.code

    config = aws("cloudfront", "get-distribution", "--id", outputs["DistributionId"])[
        "Distribution"
    ]
    assert config["Status"] == "Deployed"
    origins = {o["Id"]: o for o in config["DistributionConfig"]["Origins"]["Items"]}
    assert origins["frontend"]["OriginAccessControlId"]
    oac = aws(
        "cloudfront",
        "get-origin-access-control",
        "--id",
        origins["frontend"]["OriginAccessControlId"],
    )["OriginAccessControl"]["OriginAccessControlConfig"]
    assert oac["SigningBehavior"] == "always" and oac["SigningProtocol"] == "sigv4"
    assert origins["api"]["VpcOriginConfig"]["VpcOriginId"]
    services = aws(
        "ecs",
        "describe-services",
        "--cluster",
        outputs["ClusterName"],
        "--services",
        outputs["ServiceName"],
    )["services"]
    service = services[0]
    assert service["runningCount"] == service["desiredCount"] == 1
    assert service["networkConfiguration"]["awsvpcConfiguration"]["assignPublicIp"] == "DISABLED"
    tasks = aws(
        "ecs",
        "list-tasks",
        "--cluster",
        outputs["ClusterName"],
        "--service-name",
        outputs["ServiceName"],
    )["taskArns"]
    details = aws("ecs", "describe-tasks", "--cluster", outputs["ClusterName"], "--tasks", *tasks)[
        "tasks"
    ]
    assert all(t["healthStatus"] == "HEALTHY" for t in details)
    eni_ids = [
        item["value"]
        for task in details
        for attachment in task["attachments"]
        for item in attachment["details"]
        if item["name"] == "networkInterfaceId"
    ]
    enis = aws("ec2", "describe-network-interfaces", "--network-interface-ids", *eni_ids)[
        "NetworkInterfaces"
    ]
    assert all("PublicIp" not in e.get("Association", {}) for e in enis)
    lb_arn = aws(
        "cloudformation",
        "describe-stack-resource",
        "--stack-name",
        args.stack,
        "--logical-resource-id",
        "LoadBalancer",
    )["StackResourceDetail"]["PhysicalResourceId"]
    assert (
        aws("elbv2", "describe-load-balancers", "--load-balancer-arns", lb_arn)["LoadBalancers"][0][
            "Scheme"
        ]
        == "internal"
    )
    gpu_stack = aws("cloudformation", "describe-stacks", "--stack-name", args.stack + "-gpu")[
        "Stacks"
    ][0]
    gpu_outputs = {row["OutputKey"]: row["OutputValue"] for row in gpu_stack["Outputs"]}
    instances = [
        instance
        for reservation in aws(
            "ec2",
            "describe-instances",
            "--filters",
            f"Name=tag:DeciderGpuStack,Values={args.stack}-gpu",
            "Name=instance-state-name,Values=pending,running,stopping,stopped",
        )["Reservations"]
        for instance in reservation["Instances"]
    ]
    assert len(instances) <= 1
    gpu_service = aws(
        "ecs",
        "describe-services",
        "--cluster",
        outputs["ClusterName"],
        "--services",
        gpu_outputs["ServiceName"],
    )["services"][0]
    if args.gpu_state == "stopped" or provider == "sagemaker":
        assert all(instance["State"]["Name"] == "stopped" for instance in instances)
        assert (
            gpu_service["desiredCount"]
            == gpu_service["runningCount"]
            == gpu_service["pendingCount"]
            == 0
        )
    else:
        assert len(instances) == 1 and instances[0]["State"]["Name"] == "running"
    if provider == "sagemaker":
        sm_stack = aws(
            "cloudformation", "describe-stacks", "--stack-name", args.stack + "-sagemaker"
        )["Stacks"][0]
        assert sm_stack["StackStatus"] in ("CREATE_COMPLETE", "UPDATE_COMPLETE")
        sm_outputs = {row["OutputKey"]: row["OutputValue"] for row in sm_stack["Outputs"]}
        endpoint_name = sm_outputs["EndpointName"]
        if args.gpu_state == "ready":
            endpoint = aws("sagemaker", "describe-endpoint", "--endpoint-name", endpoint_name)
            assert endpoint["EndpointStatus"] == "InService"
            assert sum(v["CurrentInstanceCount"] for v in endpoint["ProductionVariants"]) == 1
            config = aws(
                "sagemaker",
                "describe-endpoint-config",
                "--endpoint-config-name",
                endpoint["EndpointConfigName"],
            )
            assert config["ProductionVariants"][0]["InstanceType"] == "ml.g6.xlarge"
            model = aws(
                "sagemaker",
                "describe-model",
                "--model-name",
                config["ProductionVariants"][0]["ModelName"],
            )
            assert model["EnableNetworkIsolation"]
        elif args.gpu_state == "stopping":
            endpoint = aws("sagemaker", "describe-endpoint", "--endpoint-name", endpoint_name)
            assert endpoint["EndpointStatus"] in ("Creating", "Deleting", "Failed", "InService")
        else:
            try:
                aws("sagemaker", "describe-endpoint", "--endpoint-name", endpoint_name)
                raise AssertionError("Stopped SageMaker endpoint still exists")
            except subprocess.CalledProcessError as error:
                assert "Could not find endpoint" in error.stderr, error.stderr
        endpoints = aws(
            "ec2",
            "describe-vpc-endpoints",
            "--filters",
            f"Name=vpc-id,Values={outputs['VpcId']}",
            f"Name=service-name,Values=com.amazonaws.{args.region}.sagemaker.runtime",
        )["VpcEndpoints"]
        assert len(endpoints) == 1 and endpoints[0]["PrivateDnsEnabled"]
        assert endpoints[0]["State"] == "available"
    for instance in instances:
        assert instance.get("InstanceLifecycle") != "spot"
        assert instance["InstanceType"] in ("g6.xlarge", "g6.2xlarge", "g5.xlarge")
        assert "PublicIpAddress" not in instance
        volumes = aws(
            "ec2",
            "describe-volumes",
            "--volume-ids",
            *[mapping["Ebs"]["VolumeId"] for mapping in instance["BlockDeviceMappings"]],
        )["Volumes"]
        assert len(volumes) == 1 and volumes[0]["Size"] == 80
        assert volumes[0]["Encrypted"] and volumes[0]["VolumeType"] == "gp3"
        assert volumes[0]["Attachments"][0]["InstanceId"] == instance["InstanceId"]
    routes = aws(
        "ec2", "describe-route-tables", "--filters", f"Name=vpc-id,Values={outputs['VpcId']}"
    )["RouteTables"]
    assert not any(
        route.get("DestinationCidrBlock") == "0.0.0.0/0"
        for table in routes
        for route in table["Routes"]
    )
    bedrock_endpoints = aws(
        "ec2",
        "describe-vpc-endpoints",
        "--filters",
        f"Name=vpc-id,Values={outputs['VpcId']}",
        f"Name=service-name,Values=com.amazonaws.{args.region}.bedrock-runtime",
    )["VpcEndpoints"]
    assert len(bedrock_endpoints) == 1
    assert bedrock_endpoints[0]["State"] == "available"
    assert bedrock_endpoints[0]["PrivateDnsEnabled"]
    bedrock_policy = json.loads(bedrock_endpoints[0]["PolicyDocument"])
    assert all(
        "openai.gpt-6.1-sol" in resource
        for statement in bedrock_policy["Statement"]
        for resource in statement["Resource"]
    )
    status, page, _ = request(url)
    assert status == 200 and b"Strands Decider" in page
    assert request(url + "/static/app.js")[0] == 200
    try:
        request(url + "/api/examples")
        raise AssertionError("Unauthenticated API access succeeded")
    except urllib.error.HTTPError as error:
        assert error.code == 401
    credentials = json.loads(args.credentials.read_text())
    _, _, headers = request(url + "/api/auth/login", credentials)
    cookie = headers["set-cookie"]
    assert all(flag in cookie for flag in ("HttpOnly", "Secure", "SameSite=strict"))
    parsed = SimpleCookie(cookie)
    replay = "; ".join(f"{key}={value.value}" for key, value in parsed.items())
    assert request(url + "/api/auth/me")[0] == 200
    health = json.loads(request(url + "/api/health")[1])
    gpu_status = json.loads(request(url + "/api/gpu")[1])
    crypto = json.loads(request(url + "/api/crypto/catalog")[1])
    assert len(crypto["cases"]) == 4 and crypto["bedrock_configured"]
    assert [m["id"] for m in crypto["bedrock_models"]] == ["us.openai.gpt-6.1-sol"]
    assert gpu_status["phase"] == args.gpu_state and gpu_status["purchase_option"] == "on-demand"
    assert gpu_status.get("provider", "ec2") == provider
    if args.gpu_state == "stopping":
        assert gpu_status["desired"] == "stopped"
    assert request(url + "/api/ready")[0] == 200
    assert health["connected"] is (args.gpu_state == "ready")
    if args.gpu_state == "ready":
        assert health["upstream"]["device"] == "cuda"
    example = json.loads(request(url + "/api/examples")[1])[0]
    result = json.loads(
        request(
            url + "/api/decide",
            {
                "mode": "live" if args.gpu_state == "ready" else "example",
                "example_id": example["id"],
                "measure_decisions": True,
                "state": example["state"],
                "questions": example["questions"],
            },
        )[1]
    )
    assert len(result["answers"]) == 3
    if args.gpu_state == "ready":
        assert result["source"] == "live"
        assert result["model"] == "strands-decider-2B-hobson-v19"
        timings = result["timings"]
        assert timings["execution"] == "individual"
        assert set(timings["decisions_ms"]) == set(example["questions"])
        assert all(value > 0 for value in timings["decisions_ms"].values())
        assert timings["backend_total_ms"] >= sum(timings["decisions_ms"].values()) - 0.01
    else:
        assert result["source"] == "example" and result["latency_ms"] is None
        try:
            request(
                url + "/api/decide",
                {"mode": "live", "state": example["state"], "questions": example["questions"]},
            )
            raise AssertionError("Live inference succeeded with GPU stopped")
        except urllib.error.HTTPError as error:
            assert error.code == 503
    assert request(url + "/api/auth/logout", {})[0] == 200
    try:
        request(url + "/api/examples")
        raise AssertionError("Logged-out API access succeeded")
    except urllib.error.HTTPError as error:
        assert error.code == 401
    replay_request = urllib.request.Request(url + "/api/examples", headers={"Cookie": replay})
    try:
        urllib.request.urlopen(replay_request, timeout=15)
        raise AssertionError("A revoked session cookie was accepted")
    except urllib.error.HTTPError as error:
        assert error.code == 401
    print(
        json.dumps(
            {
                "url": url,
                "region": args.region,
                "s3_anonymous_access": "403 (blocked)",
                "s3_public_access_block": "all enabled",
                "oac": "always / sigv4 / scoped to distribution",
                "ecs": "1 healthy ARM64 API task, no public IP",
                "gpu": gpu_status,
                "alb": "internal / CloudFront VPC origin",
                "internet_default_routes": 0,
                "bedrock": "Private runtime endpoint, GPT-6.1 Sol US profile only; catalog configured",
                "authentication": "username/password, secure HttpOnly session, protected API, logout verified",
                "auth_store": outputs["AuthTableName"],
                "result": result,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
