"""IAM-only Lambda bridge to Jev; no function URL, arbitrary URL or credential in responses."""

import base64
import binascii
import http.client
import json
import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError

_key = None


def valid_request(event):
    if (
        not isinstance(event, dict)
        or not {"model", "state", "questions"} <= set(event) <= {"model", "state", "questions", "assets"}
        or event["model"] != "jev-latest"
        or not isinstance(event["state"], str)
        or len(event["state"]) > 32_768
        or not isinstance(event["questions"], dict)
        or not 1 <= len(event["questions"]) <= 8
    ):
        return False
    for key, question in event["questions"].items():
        if (
            not isinstance(key, str) or not 1 <= len(key) <= 80
            or not isinstance(question, dict)
            or not {"type", "instructions"} <= set(question) <= {"type", "instructions", "criteria"}
            or question["type"] not in ("choice", "noul")
            or not isinstance(question["instructions"], str)
            or len(question["instructions"]) > 8192
        ):
            return False
        criteria = question.get("criteria")
        if question["type"] == "choice":
            if not isinstance(criteria, dict) or not 2 <= len(criteria) <= 24:
                return False
        elif criteria is not None and (not isinstance(criteria, dict) or set(criteria) != {"true", "false"}):
            return False
        if criteria is not None and any(
            not isinstance(k, str) or not isinstance(v, str) or len(k) > 100 or len(v) > 8192
            for k, v in criteria.items()
        ):
            return False
    if "assets" in event:
        assets = event["assets"]
        if not isinstance(assets, dict) or len(assets) != 1:
            return False
        for reference, asset in assets.items():
            if (
                not isinstance(reference, str) or not 16 <= len(reference) <= 100
                or event["state"].count(reference) != 1
                or not isinstance(asset, dict) or set(asset) != {"type", "format", "data_base64"}
                or asset["type"] != "image" or asset["format"] not in ("png", "jpeg")
                or not isinstance(asset["data_base64"], str) or len(asset["data_base64"]) > 2_666_668
            ):
                return False
            try:
                raw = base64.b64decode(asset["data_base64"], validate=True)
            except (binascii.Error, ValueError):
                return False
            if not raw or len(raw) > 2_000_000:
                return False
            if asset["format"] == "png" and not raw.startswith(b"\x89PNG\r\n\x1a\n"):
                return False
            if asset["format"] == "jpeg" and not raw.startswith(b"\xff\xd8\xff"):
                return False
    return True


def handler(event, context):
    global _key
    connection = None
    try:
        if not valid_request(event):
            return {"status": 422}
        body = json.dumps(event, ensure_ascii=False).encode()
        if len(body) > (2_800_000 if event.get("assets") else 65_536):
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
        headers = {"Authorization": f"Bearer {_key}", "Content-Type": "application/json"}
        if event.get("assets"):
            headers["TypeSafe-Danger-Zone-Images"] = "true"
        connection.request(
            "POST",
            "/v1/systemone",
            body=body,
            headers=headers,
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
