"""Authenticated controls for a reusable On-Demand GPU; local CPU usage stays supported."""

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
    sagemaker = state.get("provider") == "sagemaker"
    instance_type = "ml.g6.xlarge" if sagemaker else state.get("instance_type") or "g6.xlarge"
    prices = (
        {"ml.g6.xlarge": 1.1267}
        if sagemaker
        else {"g6.xlarge": 0.8048, "g6.2xlarge": 0.9776, "g5.xlarge": 1.006}
    )
    options = list(prices) if sagemaker else state.get("instance_options", list(prices))
    idle_seconds = 1800 if sagemaker else int(state.get("idle_timeout_seconds", 1800))
    return {
        "enabled": True,
        "can_manage": manager,
        "phase": state["phase"],
        "desired": state["desired"],
        "provider": "sagemaker" if sagemaker else "ec2",
        "instance_type": instance_type,
        "instance_options": options,
        "maximum_instance_usd_per_hour": max(prices[kind] for kind in options),
        "instance_id": None if sagemaker else state.get("instance_id"),
        "instance_state": state.get("endpoint_status")
        if sagemaker
        else state.get("instance_state"),
        "purchase_option": "on-demand",
        "instance_usd_per_hour": prices[instance_type],
        "disk_gib": 80,
        "disk_usd_per_month": 6.4,
        "disk_retained": bool(state.get("instance_id")),
        "retained_ec2_instance_id": state.get("instance_id") if sagemaker else None,
        "instance_count": int(state.get("instance_count", 0)),
        "busy": int(state.get("busy_until", 0)) > now,
        "idle_auto_stop": idle_seconds > 0,
        "idle_minutes": idle_seconds // 60,
        "idle_remaining_seconds": max(0, int(state.get("last_activity", now)) + idle_seconds - now)
        if idle_seconds
        else None,
        "stop_reason": state.get("stop_reason", ""),
        "startup_stage": state.get("startup_stage", ""),
        "last_error_code": state.get("last_error_code", ""),
        "last_error_message": state.get("last_error_message", ""),
        "endpoint_status": state.get("endpoint_status", ""),
        "startup_elapsed_seconds": max(0, now - int(state.get("starting_at", now))),
        "startup_remaining_seconds": max(0, int(state.get("starting_at", now)) + 1200 - now),
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
        raise HTTPException(403, "只有管理员可以启动或停止 GPU。")
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
