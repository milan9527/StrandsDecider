import asyncio
import copy
import logging
import math
import os
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter

import httpx
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from app.auth import Auth
from app.auth import router as auth_router
from app.bedrock import create_client as create_bedrock
from app.crypto import router as crypto_router
from app.examples import EXAMPLES, GUARD_QUESTIONS, public_examples
from app.gpu import configured_gpu, inference_lease
from app.gpu import router as gpu_router
from app.policy import review, tool_state
from app.sagemaker import create_runtime
from app.sagemaker import invoke as invoke_sagemaker
from app.schemas import DecisionRequest, GuardRequest

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    app.state.auth = Auth()
    app.state.gpu = configured_gpu()
    app.state.upstream = os.getenv("STRANDS_DECIDER_URL", "http://127.0.0.1:8099").rstrip("/")
    app.state.lock = asyncio.Lock()
    app.state.model_timeout = float(os.getenv("DECIDER_TIMEOUT", "180"))
    app.state.sagemaker = create_runtime() if os.getenv("GPU_PROVIDER") == "sagemaker" else None
    app.state.bedrock = create_bedrock()
    app.state.bedrock_slots = asyncio.Semaphore(2)
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(app.state.model_timeout, connect=5),
        trust_env=False,
    ) as client:
        app.state.client = client
        try:
            yield
        finally:
            if app.state.sagemaker:
                app.state.sagemaker.close()
            if app.state.bedrock:
                app.state.bedrock.close()


app = FastAPI(
    title="Strands Decider · 决策实验室",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)
app.include_router(auth_router)
app.include_router(gpu_router)
app.include_router(crypto_router)


@app.middleware("http")
async def authenticate(request, call_next):
    return await request.app.state.auth.middleware(request, call_next)


if os.getenv("SERVE_FRONTEND", "true").lower() == "true":
    app.mount("/static", StaticFiles(directory=FRONTEND / "static"), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(FRONTEND / "index.html")


@app.get("/api/live", include_in_schema=False)
def liveness():
    return {"status": "ok"}


@app.get("/api/examples")
def examples():
    return public_examples()


@app.get("/api/health")
async def health(request: Request):
    upstream = request.app.state.upstream
    if request.app.state.gpu:
        state = await run_in_threadpool(request.app.state.gpu.get)
        if state["desired"] != "running" or state["phase"] != "ready" or not state.get("endpoint"):
            return {"connected": False, "message": "GPU 尚未就绪。示例回放仍可使用。"}
        upstream = state["endpoint"]
    try:
        if upstream.startswith("sagemaker://"):
            async with asyncio.timeout(4):
                data = await run_in_threadpool(
                    invoke_sagemaker,
                    request.app.state.sagemaker,
                    upstream,
                    {"operation": "health"},
                )
        else:
            response = await request.app.state.client.get(upstream + "/health", timeout=3)
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict) or data.get("status") != "ok" or not data.get("model"):
            raise ValueError("Not a Decider health response")
        return {"connected": True, "upstream": data}
    except (httpx.HTTPError, ValueError, ClientError, BotoCoreError, TimeoutError):
        return {"connected": False, "message": "模型服务未连接。示例回放仍可使用。"}


@app.get("/api/ready", include_in_schema=False)
async def readiness(request: Request):
    if request.app.state.gpu:
        # The API serves authentication, examples and lifecycle controls while the GPU is off.
        return {"status": "ready", "model": "on-demand-gpu"}
    status = await health(request)
    if not status["connected"]:
        raise HTTPException(503, "模型仍在启动")
    return {"status": "ready", "model": status["upstream"]["model"]}


@asynccontextmanager
async def decision_slot(lock):
    try:
        await asyncio.wait_for(lock.acquire(), timeout=5)
    except TimeoutError as exc:
        raise HTTPException(
            429, "模型正在处理其他请求，请稍后重试。", headers={"Retry-After": "5"}
        ) from exc
    try:
        yield
    finally:
        lock.release()


def probability(value):
    return isinstance(value, (float, int)) and math.isfinite(value) and 0 <= value <= 1


def validate_response(data, questions):
    """Reject malformed upstream output rather than making a policy decision from it."""
    if not isinstance(data, dict) or not isinstance(data.get("model"), str):
        raise ValueError("Missing model")
    answers = data.get("answers")
    if not isinstance(answers, dict) or set(answers) != set(questions):
        raise ValueError("Answer keys do not match questions")
    for key, q in questions.items():
        a = answers[key]
        if not isinstance(a, dict) or a.get("type") != q["type"]:
            raise ValueError("Answer type mismatch")
        if q["type"] == "noul":
            if not probability(a.get("noul")):
                raise ValueError("Invalid noul")
            continue
        probs = a.get("probabilities")
        keys = (
            set(q["criteria"])
            if q["type"] == "choice"
            else {str(i) for i in range(len(q["criteria"]))}
        )
        if (
            not isinstance(probs, dict)
            or set(probs) != keys
            or not all(probability(p) for p in probs.values())
            or not math.isclose(sum(probs.values()), 1, abs_tol=0.02)
            or not probability(a.get("confidence"))
        ):
            raise ValueError("Invalid distribution")
        if q["type"] == "choice" and a.get("choice") not in keys:
            raise ValueError("Invalid choice")
        if q["type"] == "score":
            score = a.get("score")
            if not isinstance(score, (int, float)) or not math.isfinite(score):
                raise ValueError("Invalid score")
            if not 0 <= score <= len(keys) - 1:
                raise ValueError("Score outside rubric")
            if a.get("legend") != {str(i): label for i, label in enumerate(q["criteria"])}:
                raise ValueError("Score legend mismatch")
    if "latency_ms" in data:
        value = data["latency_ms"]
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError("Invalid latency")
    if "usage" in data:
        usage = data["usage"]
        if not isinstance(usage, dict) or any(
            type(usage.get(key)) is not int or usage[key] < 0
            for key in ("input_tokens", "output_tokens")
        ):
            raise ValueError("Invalid usage")


async def call_model(request: Request, payload: dict):
    try:
        if request.state.model_upstream.startswith("sagemaker://"):
            result = await run_in_threadpool(
                invoke_sagemaker,
                request.app.state.sagemaker,
                request.state.model_upstream,
                payload,
            )
        else:
            response = await request.app.state.client.post(
                request.state.model_upstream + "/v1/systemone", json=payload
            )
            if response.status_code == 422:
                raise HTTPException(
                    422, "模型拒绝了请求，可能超出上下文窗口。请缩短输入或减少问题。"
                )
            response.raise_for_status()
            result = response.json()
        validate_response(result, payload["questions"])
        return result
    except ClientError as exc:
        if exc.response.get("OriginalStatusCode") == 422:
            raise HTTPException(422, "模型拒绝了请求，请缩短输入或减少问题。") from exc
        raise HTTPException(503, "SageMaker 模型暂不可用，请检查 GPU 状态后重试。") from exc
    except BotoCoreError as exc:
        raise HTTPException(503, "SageMaker 模型连接失败，请稍后重试。") from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(504, "模型响应超时，请稍后重试或缩短输入。") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            503, "无法连接 Strands Decider。请先启动模型服务，或切换到示例回放。"
        ) from exc
    except (ValueError, TypeError, KeyError) as exc:
        logger.warning("Invalid Decider response: %s", exc)
        raise HTTPException(502, "模型服务返回了不符合协议的数据，未执行后续决策。") from exc


async def live_decision(request: Request, payload: dict, *, measure_decisions=False):
    queued_at = perf_counter()
    decision_ms = {}
    # Keep the entire run in one slot; the engine owns mutable inference state.
    async with decision_slot(request.app.state.lock), inference_lease(request):
        started = perf_counter()
        try:
            # One deadline for the complete run, not a fresh timeout for every question.
            async with asyncio.timeout(request.app.state.model_timeout):
                if measure_decisions:
                    replies = []
                    answers = {}
                    for key, question in payload["questions"].items():
                        question_started = perf_counter()
                        reply = await call_model(
                            request, {"state": payload["state"], "questions": {key: question}}
                        )
                        decision_ms[key] = round((perf_counter() - question_started) * 1000, 3)
                        if replies and reply["model"] != replies[0]["model"]:
                            raise HTTPException(
                                502, "模型标识在本次运行中发生变化，未返回部分结果。"
                            )
                        replies.append(reply)
                        answers.update(reply["answers"])
                    result = {
                        "model": replies[0]["model"],
                        "answers": answers,
                        "latency_ms": (
                            round(sum(reply["latency_ms"] for reply in replies), 3)
                            if all("latency_ms" in reply for reply in replies)
                            else None
                        ),
                        "usage": (
                            {
                                key: sum(reply["usage"][key] for reply in replies)
                                for key in ("input_tokens", "output_tokens")
                            }
                            if all("usage" in reply for reply in replies)
                            else None
                        ),
                    }
                else:
                    result = await call_model(request, payload)
        except TimeoutError as exc:
            raise HTTPException(
                504, "本次运行超出总时间限制，请减少问题数量或缩短上下文后重试。"
            ) from exc
        finished = perf_counter()
    processing_ms = round((finished - started) * 1000, 3)
    return {
        **result,
        "source": "live",
        "round_trip_ms": processing_ms,
        "timings": {
            "execution": "individual" if measure_decisions else "batch",
            "decisions_ms": decision_ms if measure_decisions else None,
            "queue_ms": round((started - queued_at) * 1000, 3),
            "processing_ms": processing_ms,
            "backend_total_ms": round((finished - queued_at) * 1000, 3),
        },
    }


def fixture_response(answers):
    return {
        "model": "illustrative-fixture",
        "answers": copy.deepcopy(answers),
        "source": "example",
        "latency_ms": None,
        "usage": None,
        "timings": {"execution": "example", "decisions_ms": None},
        "notice": "预设示例数据，仅用于演示交互与策略；不是模型推理结果。",
    }


@app.post("/api/decide")
async def decide(body: DecisionRequest, request: Request):
    payload = body.wire_payload()
    if body.mode == "live":
        return await live_decision(request, payload, measure_decisions=body.measure_decisions)
    example = next((e for e in EXAMPLES if e["id"] == body.example_id), None)
    if example is None or payload != {
        "state": example["state"],
        "questions": example["questions"],
    }:
        raise HTTPException(
            409, "示例回放只支持原始预设。请重置示例，或切换到真实模型运行自定义输入。"
        )
    return fixture_response(example["answers"])


@app.post("/api/guard")
async def guard(body: GuardRequest, request: Request):
    state = tool_state(f"user: {body.message}", "get_weather", {"location": body.location})
    if body.mode == "example":
        if body.location != "Seattle" or body.message not in (
            "What's the weather?",
            "What's the weather in Seattle?",
        ):
            raise HTTPException(409, "示例回放支持两个预设场景；自定义对话请使用真实模型。")
        grounded = body.message == "What's the weather in Seattle?"
        result = fixture_response(
            {
                "args_grounded": {"type": "noul", "noul": 0.97 if grounded else 0.08},
                "premature": {"type": "noul", "noul": 0.04 if grounded else 0.94},
            }
        )
    else:
        result = await live_decision(
            request,
            {"state": state, "questions": GUARD_QUESTIONS},
            measure_decisions=body.measure_decisions,
        )
    return {
        **result,
        "policy": review(result["answers"], body.threshold),
        "request": {"state": state, "questions": GUARD_QUESTIONS},
        "tool_executed": False,
    }
