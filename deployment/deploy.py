"""Deploy with AWS CLI, Docker and uv. The generated stack owns all AWS resources."""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from infrastructure import template

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / ".deployment"


def run(command, **kwargs):
    print("+", " ".join(command), flush=True)
    return subprocess.run(command, cwd=ROOT, check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-2"))
    parser.add_argument("--stack", default="strands-decider-demo")
    parser.add_argument("--tag", default=datetime.now(UTC).strftime("%Y%m%d-%H%M%S"))
    parser.add_argument(
        "--skip-build", action="store_true", help="Use existing local images with --tag"
    )
    parser.add_argument("--frontend-only", action="store_true")
    parser.add_argument("--api-only", action="store_true", help="Keep the existing model image")
    args = parser.parse_args()
    STATE.mkdir(exist_ok=True)
    template_path = ROOT / "deployment" / "cloudformation.json"
    template_path.write_text(json.dumps(template(), indent=2) + "\n")

    def aws(*parts, raw=False):
        command = ["aws", *parts, "--region", args.region, "--output", "json"]
        result = subprocess.run(command, text=True, capture_output=True, cwd=ROOT)
        if result.returncode:
            raise RuntimeError(result.stderr.strip())
        if raw:
            return result.stdout.strip()
        return json.loads(result.stdout) if result.stdout.strip() else {}

    def stack():
        try:
            return aws("cloudformation", "describe-stacks", "--stack-name", args.stack)["Stacks"][0]
        except RuntimeError as exc:
            if "does not exist" in str(exc):
                return None
            raise

    def wait_stack():
        deadline = time.monotonic() + 2400
        previous = None
        while time.monotonic() < deadline:
            current = stack()
            status = current["StackStatus"]
            if status != previous:
                print(f"CloudFormation: {status}", flush=True)
                previous = status
            if status in ("CREATE_COMPLETE", "UPDATE_COMPLETE"):
                return current
            if "ROLLBACK" in status or status.endswith("FAILED"):
                events = aws("cloudformation", "describe-stack-events", "--stack-name", args.stack)
                failures = [
                    {key: item.get(key) for key in ("LogicalResourceId", "ResourceStatusReason")}
                    for item in events["StackEvents"]
                    if item["ResourceStatus"].endswith("FAILED")
                ]
                raise RuntimeError(f"{status}: {json.dumps(failures, ensure_ascii=False)}")
            time.sleep(15)
        raise TimeoutError("CloudFormation did not stabilize within 40 minutes")

    current = stack()
    if args.api_only and current is None:
        parser.error("--api-only requires an existing stack")
    image_names = ("api",) if args.api_only else ("api", "model")
    if args.frontend_only:
        if current is None or current["StackStatus"] not in ("CREATE_COMPLETE", "UPDATE_COMPLETE"):
            raise RuntimeError("Frontend-only deployment requires a completed stack")
    else:
        if current is None:
            zones = aws("ec2", "describe-availability-zones")["AvailabilityZones"]
            excluded = {"use1-az3", "usw1-az2", "apne1-az3", "cac1-az3"}
            zones = [
                z["ZoneName"]
                for z in zones
                if z["State"] == "available" and z["ZoneId"] not in excluded
            ]
            prefix = aws(
                "ec2",
                "describe-managed-prefix-lists",
                "--filters",
                "Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing",
            )["PrefixLists"][0]["PrefixListId"]
            values = {
                "ImageTag": args.tag,
                "DesiredCount": "0",
                "AvailabilityZone1": zones[0],
                "AvailabilityZone2": zones[1],
                "CloudFrontPrefixListId": prefix,
            }
            parameters = [{"ParameterKey": k, "ParameterValue": v} for k, v in values.items()]
            aws(
                "cloudformation",
                "create-stack",
                "--stack-name",
                args.stack,
                "--template-body",
                f"file://{template_path}",
                "--parameters",
                json.dumps(parameters),
                "--capabilities",
                "CAPABILITY_IAM",
                "--tags",
                "Key=Project,Value=StrandsDecider",
                "Key=Environment,Value=demo",
            )
        elif "ROLLBACK" in current["StackStatus"]:
            raise RuntimeError(
                "The existing stack has rolled back; inspect its events before retrying."
            )

        if not args.skip_build:
            for name in image_names:
                extra = ["--extra", "model"] if name == "model" else []
                run(
                    [
                        "uv",
                        "export",
                        "--locked",
                        "--no-dev",
                        "--no-hashes",
                        "--no-emit-project",
                        *extra,
                        "-o",
                        f"deployment/{name}-requirements.txt",
                    ],
                    stdout=subprocess.DEVNULL,
                )
            if not args.api_only:
                run(["uv", "run", "--extra", "model", "python", "deployment/package_model.py"])
            for name in image_names:
                run(
                    [
                        "docker",
                        "build",
                        "--platform",
                        "linux/arm64",
                        "-f",
                        f"deployment/{name}.Dockerfile",
                        "-t",
                        f"strands-decider-{name}:{args.tag}",
                        ".",
                    ]
                )
        # Publish while CloudFront is still provisioning; ECR is ready much sooner.
        repository_names = [f"{args.stack}-api", f"{args.stack}-model"]
        deadline = time.monotonic() + 300
        while True:
            try:
                repositories = aws(
                    "ecr", "describe-repositories", "--repository-names", *repository_names
                )["repositories"]
                break
            except RuntimeError as exc:
                if "RepositoryNotFoundException" not in str(exc) or time.monotonic() > deadline:
                    raise
                time.sleep(10)
        image_repositories = {r["repositoryName"]: r["repositoryUri"] for r in repositories}
        registry = image_repositories[repository_names[0]].split("/")[0]
        password = subprocess.run(
            ["aws", "ecr", "get-login-password", "--region", args.region],
            text=True,
            capture_output=True,
            check=True,
        ).stdout
        run(
            ["docker", "login", "--username", "AWS", "--password-stdin", registry],
            input=password,
            text=True,
        )
        for name in image_names:
            image = f"{image_repositories[f'{args.stack}-{name}']}:{args.tag}"
            run(["docker", "tag", f"strands-decider-{name}:{args.tag}", image])
            run(["docker", "push", image])

        current = wait_stack()
        parameters = [
            (
                {"ParameterKey": "ImageTag", "UsePreviousValue": True}
                if args.api_only
                else {"ParameterKey": "ImageTag", "ParameterValue": args.tag}
            ),
            {"ParameterKey": "ApiImageTag", "ParameterValue": args.tag},
            {"ParameterKey": "DesiredCount", "ParameterValue": "1"},
            *[
                {"ParameterKey": name, "UsePreviousValue": True}
                for name in (
                    "AvailabilityZone1",
                    "AvailabilityZone2",
                    "CloudFrontPrefixListId",
                )
            ],
        ]
        try:
            aws(
                "cloudformation",
                "update-stack",
                "--stack-name",
                args.stack,
                "--template-body",
                f"file://{template_path}",
                "--parameters",
                json.dumps(parameters),
                "--capabilities",
                "CAPABILITY_IAM",
            )
            current = wait_stack()
        except RuntimeError as exc:
            if "No updates are to be performed" not in str(exc):
                raise

    outputs = {o["OutputKey"]: o["OutputValue"] for o in current["Outputs"]}
    bucket = outputs["FrontendBucketName"]
    run(
        [
            "aws",
            "s3",
            "sync",
            "frontend/",
            f"s3://{bucket}/",
            "--delete",
            "--cache-control",
            "public,max-age=3600",
            "--exclude",
            "index.html",
            "--region",
            args.region,
        ]
    )
    run(
        [
            "aws",
            "s3",
            "cp",
            "frontend/index.html",
            f"s3://{bucket}/index.html",
            "--cache-control",
            "no-cache,no-store,must-revalidate",
            "--content-type",
            "text/html",
            "--region",
            args.region,
        ]
    )
    invalidation = aws(
        "cloudfront",
        "create-invalidation",
        "--distribution-id",
        outputs["DistributionId"],
        "--paths",
        "/*",
    )["Invalidation"]["Id"]
    record = {
        "region": args.region,
        "stack": args.stack,
        "image_tag": next(
            p["ParameterValue"] for p in current["Parameters"] if p["ParameterKey"] == "ImageTag"
        ),
        "outputs": outputs,
        "api_image_tag": next(
            (
                p["ParameterValue"]
                for p in current["Parameters"]
                if p["ParameterKey"] == "ApiImageTag"
            ),
            args.tag,
        ),
        "invalidation_id": invalidation,
    }
    (STATE / "outputs.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2), flush=True)
    print(f"Website: {outputs['WebsiteUrl']}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Deployment failed: {error}", file=sys.stderr)
        sys.exit(1)
