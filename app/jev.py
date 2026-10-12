"""Jev System One adapter. Credentials and outbound access stay on the server."""

import json
import logging
import os
from pathlib import Path
from threading import Lock

import boto3
import httpx
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    ConnectionClosedError,
    ConnectTimeoutError,
    ReadTimeoutError,
)

MODEL = "jev-latest"
ENDPOINT = "https://api.typesafe.ai/v1/systemone"
logger = logging.getLogger(__name__)


class JevError(Exception):
    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def upstream_error(status):
    if status in (401, 403):
        return JevError(503, "Jev 认证失败，请管理员检查服务端密钥配置。")
    if status == 429:
        return JevError(429, "Jev 请求限流，请稍后重试。")
    if status in (408, 504):
        return JevError(504, "Jev 本次决策超时，未生成替代结果。")
    if status in (400, 413, 422):
        return JevError(422, "Jev 拒绝了输入，请缩短内容或检查候选条件。")
    return JevError(503, "Jev 暂不可用，未生成替代结果。")


class JevClient:
    def __init__(self, *, api_key=None, function_name=None):
        self.function_name = function_name
        self.client_lock = Lock()
        self.http = (
            httpx.Client(
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=httpx.Timeout(35, connect=5),
                follow_redirects=False,
                trust_env=False,
            )
            if api_key and not function_name
            else None
        )

    def close(self):
        if self.http:
            self.http.close()

    def invoke_bridge(self, body):
        # Only reconnect if the TCP connection was never established. Retrying a
        # read timeout or an HTTP error could submit a paid model request twice.
        for attempt in range(2):
            # A request owns its client and socket. Do not reuse an idle Lambda
            # connection or close a connection another concurrent request uses.
            with self.client_lock:
                runtime = boto3.client(
                    "lambda",
                    region_name=os.getenv("AWS_REGION", "us-east-1"),
                    config=Config(connect_timeout=3, read_timeout=42, retries={"max_attempts": 0}),
                )
            try:
                reply = runtime.invoke(
                    FunctionName=self.function_name,
                    InvocationType="RequestResponse",
                    Payload=json.dumps(body, ensure_ascii=False).encode(),
                )
                stream = reply["Payload"]
                try:
                    raw = stream.read(1_048_577)
                finally:
                    stream.close()
                return reply.get("FunctionError"), raw
            except ConnectTimeoutError as exc:
                logger.warning("Jev bridge connect timeout; attempt=%s", attempt + 1)
                if attempt == 1:
                    raise JevError(
                        503, "Jev 转发服务连接失败，本步未提交模型请求，请重试。"
                    ) from exc
            finally:
                runtime.close()

    def decide(self, payload):
        # MODEL is server-owned, not a caller-provided URL or model override.
        body = {**payload, "model": MODEL}
        try:
            if self.function_name:
                function_error, raw = self.invoke_bridge(body)
                if function_error or len(raw) > 1_048_576:
                    logger.warning("Jev bridge returned a function error or oversized response")
                    raise JevError(503, "Jev 转发服务暂不可用，请稍后重试。")
                envelope = json.loads(raw)
                if envelope.get("status") != 200:
                    status = envelope.get("status")
                    logger.warning(
                        "Jev upstream status=%s", status if isinstance(status, int) else "invalid"
                    )
                    raise upstream_error(envelope.get("status"))
                data = envelope["data"]
            elif self.http:
                with self.http.stream("POST", ENDPOINT, json=body) as response:
                    if response.status_code != 200:
                        logger.warning("Jev upstream status=%s", response.status_code)
                        raise upstream_error(response.status_code)
                    chunks = bytearray()
                    for chunk in response.iter_bytes():
                        chunks.extend(chunk)
                        if len(chunks) > 1_048_576:
                            raise ValueError("Response too large")
                    data = json.loads(chunks)
            else:
                raise JevError(503, "Jev 尚未配置，请管理员配置服务端密钥。")
            # Same System One response contract as Decider, including the full candidate set.
            from app.main import validate_response

            validate_response(data, payload["questions"])
            if not data["model"] or len(data["model"]) > 120:
                raise ValueError("Invalid model version")
            answer = data["answers"]["action"]
            return {
                "model": data["model"],
                "choice": answer["choice"],
                "confidence": answer["confidence"],
                "probabilities": answer["probabilities"],
                "usage": data.get("usage"),
                "estimated_request_usd": None,
                "model_reported_ms": data.get("latency_ms"),
            }
        except (httpx.TimeoutException, ReadTimeoutError) as exc:
            logger.warning("Jev response timeout; type=%s", type(exc).__name__)
            raise upstream_error(504) from exc
        except ConnectionClosedError as exc:
            logger.warning("Jev bridge connection closed before a complete response")
            raise JevError(503, "Jev 连接中断，本步结果未确认，请重试。") from exc
        except (httpx.HTTPError, ClientError, BotoCoreError) as exc:
            # Exception messages can contain upstream content; record type only.
            logger.warning("Jev transport failure; type=%s", type(exc).__name__)
            raise upstream_error(503) from exc
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            logger.warning("Jev invalid response; type=%s", type(exc).__name__)
            raise JevError(502, "Jev 未返回有效候选动作或概率，本步未应用。") from exc


def create_client():
    function_name = os.getenv("JEV_FUNCTION_NAME", "").strip()
    if function_name:
        return JevClient(function_name=function_name)
    key = os.getenv("JEV_API_KEY", "").strip()
    key_file = os.getenv("JEV_API_KEY_FILE", "").strip()
    if not key and key_file:
        key = Path(key_file).expanduser().read_text().strip()
    return JevClient(api_key=key) if key else None
