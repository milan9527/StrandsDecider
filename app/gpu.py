"""Authenticated controls for the Spot GPU lifecycle; local CPU usage remains supported."""

import os
import time
from contextlib import asynccontextmanager

import boto3
from botocore.config import Config
from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.gpu_state import GpuState, TransitionConflict

router = APIRouter(prefix="/api/gpu")


def configured_gpu():
    table = os.getenv("GPU_STATE_TABLE")
    if not table:
        return None
    client = boto3.client(
        "dynamodb",
        region_name=os.getenv("AWS_REGION"),
        config=Config(connect_timeout=3, read_timeout=3, retries={"max_attempts": 2}),
    )
    return GpuState(client, table)


def can_manage(request):
    managers = {name.strip() for name in os.getenv("GPU_MANAGERS", "admin").split(",")}
    return request.state.user["username"] in managers


def public_state(state, manager):
    now = int(time.time())
    return {
        "enabled": True,
        "can_manage": manager,
        "phase": state["phase"],
        "desired": state["desired"],
        "instance_type": state.get("instance_type"),
        "instance_options": ["g6.xlarge", "g6.2xlarge", "g5.xlarge"],
        "spot_max_usd_per_hour": 0.55,
        "purchase_option": "spot",
        "instance_count": int(state.get("instance_count", 0)),
        "busy": int(state.get("busy_until", 0)) > now,
        "idle_minutes": 30,
        "idle_remaining_seconds": max(0, int(state.get("last_activity", now)) + 1800 - now),
        "stop_reason": state.get("stop_reason", ""),
    }


@router.get("")
async def status(request: Request):
    store = request.app.state.gpu
    if store is None:
        return {"enabled": False, "can_manage": False}
    return public_state(await run_in_threadpool(store.get), can_manage(request))


async def change(request, action):
    if request.app.state.gpu is None:
        raise HTTPException(409, "当前环境未启用 GPU 按需管理。")
    if not can_manage(request):
        raise HTTPException(403, "只有管理员可以启动或释放 GPU。")
    try:
        state = await run_in_threadpool(getattr(request.app.state.gpu, action))
    except TransitionConflict as error:
        raise HTTPException(409, "GPU 状态正在变化，请刷新后重试。") from error
    return public_state(state, True)


@router.post("/start", status_code=202)
async def start(request: Request):
    return await change(request, "start")


@router.post("/stop", status_code=202)
async def stop(request: Request):
    return await change(request, "stop")


@asynccontextmanager
async def inference_lease(request):
    store = request.app.state.gpu
    if store is None:
        request.state.model_upstream = request.app.state.upstream
        yield
        return
    try:
        token, endpoint = await run_in_threadpool(
            store.acquire, int(request.app.state.model_timeout) + 90
        )
    except TransitionConflict as error:
        state = await run_in_threadpool(store.get)
        if state["desired"] == "running" and state["phase"] == "ready":
            raise HTTPException(429, "GPU 正在处理其他请求，请稍后重试。") from error
        raise HTTPException(503, "GPU 尚未就绪，请先启动 GPU 并等待状态变为就绪。") from error
    request.state.model_upstream = endpoint
    failed = True
    try:
        yield
        failed = False
    finally:
        # A disconnected HTTP client doesn't cancel the CUDA worker. Retain a grace lease.
        await run_in_threadpool(store.release, token, cooldown=90 if failed else 0)
