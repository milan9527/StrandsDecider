"""Authenticated image decisions with a separate official vision backend."""

import asyncio
import base64
import binascii
import copy
import hashlib
import json
from pathlib import Path
from time import perf_counter
from typing import Literal

import httpx
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, model_validator
from starlette.concurrency import run_in_threadpool

from app.jev import JevError
from app.schemas import StrictModel
from app.vision_providers import GPT_MODEL, GPT_SYSTEM, bedrock_decide, jev_payload

ASSETS = Path(__file__).with_name("vision_assets")
DATA = json.loads((ASSETS / "catalog.json").read_text())
CASES = {c["id"]: c for c in DATA["cases"]}
GROUPS = {"payment": "支付状态", "support": "客服分流", "receipt": "凭证完整性"}
QUESTIONS = {group: next(c["request"]["questions"] for c in CASES.values() if c["group"] == group)
             for group in GROUPS}
router = APIRouter(prefix="/api/vision", tags=["Image decisions"])


class VisionRequest(StrictModel):
    provider: Literal["decider", "jev", "bedrock"] = "decider"
    mode: Literal["recorded", "live"] = "recorded"
    variant: Literal["original", "reverse", "no_image", "blank"] = "original"
    task: Literal["payment", "support", "receipt"] = "payment"
    case_id: str | None = Field(default=None, max_length=40)
    image: str | None = Field(default=None, max_length=2_800_000)

    @model_validator(mode="after")
    def one_source(self):
        if (self.case_id is None) == (self.image is None):
            raise ValueError("请选择预设图片或上传一张图片")
        if self.mode == "recorded" and self.image is not None:
            raise ValueError("上传图片需要实时推理，没有对应历史实测")
        return self


def decode_upload(value):
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(422, "图片编码无效，请重新选择 PNG、JPEG 或 WebP 图片") from exc
    if len(raw) > 2_000_000:
        raise HTTPException(413, "图片过大，请缩小后重试")
    valid = raw.startswith(b"\x89PNG\r\n\x1a\n") or raw.startswith(b"\xff\xd8\xff")
    valid = valid or (raw.startswith(b"RIFF") and raw[8:12] == b"WEBP")
    if not valid:
        raise HTTPException(422, "仅支持 PNG、JPEG 或 WebP 图片")
    return raw


def prepare(body):
    case = CASES.get(body.case_id) if body.case_id is not None else None
    if body.case_id is not None and case is None:
        raise HTTPException(404, "图片样例不存在")
    payload = copy.deepcopy(case["request"] if case else {
        "state": "请根据所附截图中的可见内容回答问题。", "questions": QUESTIONS[body.task],
    })
    original = (ASSETS / case["image"]).read_bytes() if case else decode_upload(body.image)
    image = (ASSETS / "blank.png").read_bytes() if body.variant == "blank" else original
    if body.variant != "no_image":
        payload["images"] = [base64.b64encode(image).decode()]
    if body.variant == "reverse":
        for question in payload["questions"].values():
            if question["type"] == "choice":
                question["criteria"] = dict(reversed(list(question["criteria"].items())))
    expected = case["expected"] if case and body.variant in ("original", "reverse") else None
    return case, payload, expected, {
        "sent": body.variant != "no_image",
        "sha256": hashlib.sha256(image).hexdigest() if body.variant != "no_image" else None,
        "bytes": len(image) if body.variant != "no_image" else 0,
    }


@router.get("/catalog")
def catalog():
    return {
        "captured_at": DATA["captured_at"],
        "providers": [
            {"id": "decider", "name": "Strands Decider", "model": "strands-decider-2B-hobson-v19-vision"},
            {"id": "jev", "name": "Jev", "model": "jev-latest"},
            {"id": "bedrock", "name": "GPT-6.1 Sol", "model": GPT_MODEL},
        ],
        "groups": [{"id": key, "title": title, "questions": QUESTIONS[key]} for key, title in GROUPS.items()],
        "cases": [{
            "id": c["id"], "title": c["title"], "group": c["group"],
            "image_url": "/static/vision/" + c["image"], "expected": c["expected"],
            "questions": c["request"]["questions"],
        } for c in CASES.values()],
    }


@router.get("/health")
async def health(request: Request):
    endpoint = request.app.state.vision_url
    if not endpoint:
        return {"connected": False, "message": "实时视觉服务未配置，可查看历史实测。"}
    try:
        response = await request.app.state.client.get(endpoint + "/health", timeout=3)
        response.raise_for_status()
        data = response.json()
        if data.get("vision") is not True or data.get("status") != "ok":
            raise ValueError("Not a vision service")
        return {"connected": True, "model": data["model"], "engine": "official-vision"}
    except (httpx.HTTPError, ValueError, KeyError):
        return {"connected": False, "message": "实时视觉服务暂不可用，可查看历史实测或稍后重试。"}


@router.post("/decide")
async def decide(body: VisionRequest, request: Request):
    from app.main import decision_slot, validate_response

    case, payload, expected, image_info = prepare(body)
    started = perf_counter()
    captured_at = None
    protocol = {}
    if body.mode == "recorded":
        if body.provider != "decider":
            raise HTTPException(404, "此模型尚无对应历史图片实测，请运行三模型实时对比")
        recorded = case["recordings"][body.variant]
        data = copy.deepcopy(recorded["response"])
        captured_at = recorded["captured_at"]
    elif body.provider == "decider":
        endpoint = request.app.state.vision_url
        if not endpoint:
            raise HTTPException(503, "实时视觉服务未配置，请先查看历史实测")
        async with decision_slot(request.app.state.vision_slots):
            try:
                async with asyncio.timeout(48):
                    response = await request.app.state.client.post(
                        endpoint + "/v1/systemone", json=payload, timeout=45,
                    )
                if response.status_code == 422:
                    raise HTTPException(422, "模型无法读取图片，请检查图片格式、大小及清晰度")
                if response.status_code == 429:
                    raise HTTPException(429, "Decider 图片服务繁忙，请稍后重试")
                response.raise_for_status()
                data = response.json()
            except (httpx.TimeoutException, TimeoutError) as exc:
                raise HTTPException(504, "图片推理超时，请稍后重试") from exc
            except (httpx.HTTPError, ValueError) as exc:
                raise HTTPException(502, "视觉服务暂时不可用，请稍后重试或查看历史实测") from exc
    elif body.provider == "jev":
        if request.app.state.jev is None:
            raise HTTPException(503, "Jev 尚未配置，请检查服务端密钥")
        try:
            wire = jev_payload(payload)
            protocol = {"endpoint": "/v1/systemone", "model": "jev-latest", "state": wire["state"],
                        "image_header": bool(wire.get("assets"))}
            async with decision_slot(request.app.state.jev_slots), asyncio.timeout(48):
                data = await run_in_threadpool(request.app.state.jev.system_one, wire)
        except JevError as exc:
            raise HTTPException(exc.status_code, exc.detail) from exc
        except TimeoutError as exc:
            raise HTTPException(504, "Jev 图片推理超时，未生成替代结果") from exc
        except ValueError as exc:
            raise HTTPException(422, "Jev 图片需使用 PNG 或 JPEG；网页上传会统一转换") from exc
    else:
        if request.app.state.bedrock is None:
            raise HTTPException(503, "Bedrock 尚未配置")
        try:
            protocol = {"api": "Converse", "modelId": GPT_MODEL, "system": GPT_SYSTEM, "reasoning": "low"}
            async with decision_slot(request.app.state.bedrock_slots), asyncio.timeout(45):
                data = await run_in_threadpool(bedrock_decide, request.app.state.bedrock, payload)
        except TimeoutError as exc:
            raise HTTPException(504, "GPT 图片推理超时，未生成替代结果") from exc
        except (ClientError, BotoCoreError) as exc:
            code = exc.response["Error"]["Code"] if isinstance(exc, ClientError) else type(exc).__name__
            status = 429 if code in ("ThrottlingException", "TooManyRequestsException") else 503
            raise HTTPException(status, f"Bedrock 图片推理暂不可用（{code}）") from exc
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(502, "GPT 未返回完整有效的图片判断，未生成替代结果") from exc
    if body.provider != "bedrock":
        try:
            validate_response(data, payload["questions"])
            if body.provider == "decider" and not data["model"].endswith("-vision"):
                raise ValueError("Unexpected text-only model identity")
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(502, "视觉模型返回格式异常，请稍后重试") from exc
    fingerprint = hashlib.sha256(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    return {
        "source": body.mode, "provider": body.provider, "captured_at": captured_at, "variant": body.variant,
        "case_id": body.case_id, "task": case["group"] if case else body.task,
        "model": data["model"], "answers": data["answers"], "expected": expected,
        "usage": data.get("usage"), "model_ms": data.get("latency_ms"),
        "backend_total_ms": round((perf_counter() - started) * 1000, 3) if body.mode == "live" else None,
        "provider_latency_ms": data.get("provider_latency_ms"),
        "input_fingerprint": fingerprint, "protocol": protocol, "raw_output": data.get("raw_output"),
        "request": {"state": payload["state"], "questions": payload["questions"], "image": image_info},
    }
