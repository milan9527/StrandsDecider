"""IAM-only Lambda bridge to Jev; no function URL, arbitrary URL or credential in responses."""

import http.client
import json
import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError

_key = None


def handler(event, context):
    global _key
    connection = None
    try:
        if (
            not isinstance(event, dict)
            or set(event) != {"model", "state", "questions"}
            or event["model"] != "jev-latest"
            or not isinstance(event["state"], str)
            or not isinstance(event["questions"], dict)
            or set(event["questions"]) != {"action"}
        ):
            return {"status": 422}
        question = event["questions"]["action"]
        if (
            not isinstance(question, dict)
            or set(question) != {"type", "instructions", "criteria"}
            or question["type"] != "choice"
            or not isinstance(question["instructions"], str)
            or not isinstance(question["criteria"], dict)
            or not 2 <= len(question["criteria"]) <= 24
            or any(
                not isinstance(k, str) or not isinstance(v, str)
                for k, v in question["criteria"].items()
            )
        ):
            return {"status": 422}
        body = json.dumps(event, ensure_ascii=False).encode()
        if len(body) > 65_536:
            return {"status": 413}
        if _key is None:
            _key = (
                boto3.client("secretsmanager")
                .get_secret_value(SecretId=os.environ["JEV_SECRET_ARN"])["SecretString"]
                .strip()
            )
        if not _key:
            return {"status": 503}
        connection = http.client.HTTPSConnection("api.typesafe.ai", timeout=30)
        connection.request(
            "POST",
            "/v1/systemone",
            body=body,
            headers={"Authorization": f"Bearer {_key}", "Content-Type": "application/json"},
        )
        response = connection.getresponse()
        if response.status != 200:
            if response.status in (401, 403):
                _key = None  # Pick up a rotated credential on the next request.
            return {"status": response.status}
        raw = response.read(1_048_577)
        if len(raw) > 1_048_576:
            return {"status": 502}
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {"status": 502}
        # Don't forward arbitrary provider metadata; the API validates the answer.
        return {
            "status": 200,
            "data": {k: data[k] for k in ("model", "answers", "usage", "latency_ms") if k in data},
        }
    except TimeoutError:
        return {"status": 504}
    except (OSError, ValueError, KeyError, TypeError, ClientError, BotoCoreError):
        return {"status": 503}
    finally:
        if connection:
            connection.close()
