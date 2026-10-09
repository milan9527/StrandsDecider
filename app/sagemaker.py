"""Signed SageMaker Runtime calls through the private VPC endpoint in AWS."""

import json
import os

import boto3
from botocore.config import Config


def create_runtime():
    return boto3.client(
        "sagemaker-runtime",
        region_name=os.getenv("AWS_REGION"),
        config=Config(connect_timeout=3, read_timeout=55, retries={"max_attempts": 0}),
    )


def invoke(runtime, upstream, payload):
    endpoint = upstream.removeprefix("sagemaker://")
    response = runtime.invoke_endpoint(
        EndpointName=endpoint,
        ContentType="application/json",
        Accept="application/json",
        Body=json.dumps(payload).encode(),
    )
    body = response["Body"]
    try:
        return json.loads(body.read())
    finally:
        body.close()
