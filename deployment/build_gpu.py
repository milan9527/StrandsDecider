"""Build the x86 CUDA image in a temporary, scoped CodeBuild environment."""

import argparse
import json
import subprocess
import time
import zipfile
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--stack", default="strands-decider-demo")
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    session = boto3.Session(region_name=args.region)
    cf = session.client("cloudformation")
    build = session.client("codebuild")
    s3 = session.client("s3")
    account = session.client("sts").get_caller_identity()["Account"]
    registry = f"{account}.dkr.ecr.{args.region}.amazonaws.com"
    image = f"{registry}/{args.stack}-model:{args.tag}"
    name = args.stack + "-gpu-build"
    arn = f"arn:aws:ecr:{args.region}:{account}:repository/{args.stack}-model"
    spec = {
        "version": "0.2",
        "phases": {
            "build": {
                "commands": [
                    'aws s3 sync "s3://$SOURCE_BUCKET/models/" .deployment/models/ --only-show-errors',
                    f"aws ecr get-login-password | docker login --username AWS --password-stdin {registry}",
                    f"docker build -f deployment/gpu.Dockerfile -t {image} .",
                    f"docker push {image}",
                ]
            }
        },
    }
    template = {
        "Resources": {
            "Bucket": {
                "Type": "AWS::S3::Bucket",
                "Properties": {
                    "PublicAccessBlockConfiguration": dict.fromkeys(
                        [
                            "BlockPublicAcls",
                            "BlockPublicPolicy",
                            "IgnorePublicAcls",
                            "RestrictPublicBuckets",
                        ],
                        True,
                    ),
                    "BucketEncryption": {
                        "ServerSideEncryptionConfiguration": [
                            {"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
                        ]
                    },
                },
            },
            "Role": {
                "Type": "AWS::IAM::Role",
                "Properties": {
                    "AssumeRolePolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Principal": {"Service": "codebuild.amazonaws.com"},
                                "Action": "sts:AssumeRole",
                            }
                        ],
                    },
                    "Policies": [
                        {
                            "PolicyName": "ScopedImageBuild",
                            "PolicyDocument": {
                                "Version": "2012-10-17",
                                "Statement": [
                                    {
                                        "Effect": "Allow",
                                        "Action": ["s3:GetObject"],
                                        "Resource": {"Fn::Sub": "${Bucket.Arn}/*"},
                                    },
                                    {
                                        "Effect": "Allow",
                                        "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
                                        "Resource": {"Fn::GetAtt": ["Bucket", "Arn"]},
                                    },
                                    {
                                        "Effect": "Allow",
                                        "Action": "ecr:GetAuthorizationToken",
                                        "Resource": "*",
                                    },
                                    {
                                        "Effect": "Allow",
                                        "Action": [
                                            "ecr:BatchCheckLayerAvailability",
                                            "ecr:GetDownloadUrlForLayer",
                                            "ecr:BatchGetImage",
                                            "ecr:InitiateLayerUpload",
                                            "ecr:UploadLayerPart",
                                            "ecr:CompleteLayerUpload",
                                            "ecr:PutImage",
                                        ],
                                        "Resource": arn,
                                    },
                                    {
                                        "Effect": "Allow",
                                        "Action": [
                                            "logs:CreateLogGroup",
                                            "logs:CreateLogStream",
                                            "logs:PutLogEvents",
                                        ],
                                        "Resource": f"arn:aws:logs:{args.region}:{account}:log-group:/aws/codebuild/{name}:*",
                                    },
                                ],
                            },
                        }
                    ],
                },
            },
            "Project": {
                "Type": "AWS::CodeBuild::Project",
                "Properties": {
                    "Name": name,
                    "ServiceRole": {"Fn::GetAtt": ["Role", "Arn"]},
                    "Artifacts": {"Type": "NO_ARTIFACTS"},
                    "Source": {
                        "Type": "S3",
                        "Location": {"Fn::Sub": "${Bucket}/source.zip"},
                        "BuildSpec": json.dumps(spec),
                    },
                    "Environment": {
                        "Type": "LINUX_CONTAINER",
                        "ComputeType": "BUILD_GENERAL1_LARGE",
                        "Image": "aws/codebuild/standard:7.0",
                        "PrivilegedMode": True,
                        "EnvironmentVariables": [
                            {"Name": "SOURCE_BUCKET", "Value": {"Ref": "Bucket"}}
                        ],
                    },
                    "TimeoutInMinutes": 60,
                },
            },
        },
        "Outputs": {"Bucket": {"Value": {"Ref": "Bucket"}}},
    }
    try:
        cf.create_stack(
            StackName=name, TemplateBody=json.dumps(template), Capabilities=["CAPABILITY_IAM"]
        )
        waiter = "stack_create_complete"
    except cf.exceptions.AlreadyExistsException:
        try:
            cf.update_stack(
                StackName=name, TemplateBody=json.dumps(template), Capabilities=["CAPABILITY_IAM"]
            )
            waiter = "stack_update_complete"
        except Exception as error:
            if "No updates are to be performed" not in str(error):
                raise
            waiter = None
    if waiter:
        cf.get_waiter(waiter).wait(StackName=name)
    stack = cf.describe_stacks(StackName=name)["Stacks"][0]
    bucket = next(row["OutputValue"] for row in stack["Outputs"] if row["OutputKey"] == "Bucket")
    subprocess.run(
        [
            "uv",
            "export",
            "--locked",
            "--no-dev",
            "--no-hashes",
            "--no-emit-project",
            "--extra",
            "model",
            "-o",
            "deployment/model-requirements.txt",
        ],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        [
            "aws",
            "s3",
            "sync",
            str(ROOT / ".deployment/models"),
            f"s3://{bucket}/models/",
            "--region",
            args.region,
            "--only-show-errors",
        ],
        check=True,
    )
    archive = ROOT / ".deployment/gpu-source.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        for path in [
            ".dockerignore",
            "deployment/gpu.Dockerfile",
            "deployment/model_server.py",
            "deployment/model-requirements.txt",
        ]:
            zipped.write(ROOT / path, path)
    s3.upload_file(str(archive), bucket, "source.zip")
    result = build.start_build(projectName=name)["build"]
    record = {"build_id": result["id"], "stack": name, "bucket": bucket, "image": image}
    (ROOT / ".deployment/gpu-build.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record), flush=True)
    previous = None
    while True:
        result = build.batch_get_builds(ids=[record["build_id"]])["builds"][0]
        status = (result["buildStatus"], result.get("currentPhase"))
        if status != previous:
            print(status, flush=True)
            previous = status
        if result["buildStatus"] != "IN_PROGRESS":
            if result["buildStatus"] != "SUCCEEDED":
                raise RuntimeError(f"Build failed; inspect {result.get('logs', {})}")
            break
        time.sleep(15)
    print("GPU image published: " + image, flush=True)
    # The image contains all weights. Remove temporary copies and build resources.
    subprocess.run(
        [
            "aws",
            "s3",
            "rm",
            f"s3://{bucket}/",
            "--recursive",
            "--region",
            args.region,
            "--only-show-errors",
        ],
        check=True,
    )
    cf.delete_stack(StackName=name)
    print("Temporary build resources are being deleted.", flush=True)


if __name__ == "__main__":
    main()
