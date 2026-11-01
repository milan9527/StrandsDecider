"""Live AC comparisons using the frozen benchmark inputs, with no answer repair."""

import asyncio
import copy
import hashlib
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field
from starlette.concurrency import run_in_threadpool

from app.schemas import StrictModel

router = APIRouter(prefix="/api/ac-control", tags=["AC control"])
log = logging.getLogger(__name__)
DATA = json.loads(Path(__file__).with_name("ac_control_cases.json").read_text())
CASES = {row["id"]: row for row in DATA["cases"]}
TEMPLATE = DATA["template"]
ADAPTER = "2a87384a624545021fc6ca91cf5406ed42e518a8607f048ca264048f57a0d171"
GPT_MODEL = "us.openai.gpt-6.1-sol"
GPT_SYSTEM = (
    "Answer the supplied decision questions using the supplied state, including its task rules, "
    "and each question's instructions and candidate criteria. "
    "Return exactly one JSON object with the single key answers. Its value must be an object "
    "mapping EVERY supplied question ID to its selected candidate ID as a JSON string, "
    "including questions whose selected candidate is omit. "
    'Output shape: {"answers":{"QUESTION_ID":"CANDIDATE_ID"}}. '
    "Use only the supplied candidate IDs. Do not add explanations, probabilities, "
    "confidence estimates or Markdown."
)
PROVIDERS = [
    {"id": "liquid_lora", "name": "Liquid LoRA", "detail": "d1-2B · 空调领域微调"},
    {"id": "jev", "name": "Jev", "detail": "jev-latest · 实际版本随结果记录"},
    {"id": "gpt", "name": "GPT 6.1 Sol", "detail": "low effort"},
]
FIELD_NAMES = dict(zip(TEMPLATE["questions"], [
    "电源", "运行模式", "摄氏温度", "华氏温度", "温标", "风速", "静音风",
    "强力模式", "上下摆风", "室温检测", "左右摆风", "摆风角度", "水平风向",
    "节能", "净化", "跟随风", "8℃制热", "睡眠", "显示灯", "室内自清洁",
    "室外自清洁", "一键自清洁", "新风", "TMS", "健康风", "室外静音",
    "需求响应开关", "需求响应温差", "需求响应负载容量", "自动除霜清洁",
], strict=True))


class RunRequest(StrictModel):
    case_ids: list[str] = Field(min_length=1, max_length=20)
    mode: Literal["single", "serial30", "full30", "all"] = "full30"
    field: str = "t_power"
    order: Literal["original", "reversed"] = "original"


def payload_for(case_id, order="original"):
    payload = copy.deepcopy(TEMPLATE)
    state = json.loads(payload["state"])
    state["query"] = CASES[case_id]["query"]
    payload["state"] = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    if order == "reversed":
        for question in payload["questions"].values():
            question["criteria"] = dict(reversed(list(question["criteria"].items())))
    return payload


def expected_for(case_id):
    active = {c["cmdKey"]: str(c["cmdValue"]) for c in CASES[case_id]["expected"]}
    return {key: active.get(key, "omit") for key in TEMPLATE["questions"]}


def fingerprint(payload):
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def selections(raw, payload):
    answers = raw.get("answers") if isinstance(raw, dict) else None
    if not isinstance(answers, dict) or set(answers) != set(payload["questions"]):
        raise ValueError("返回字段不完整或包含多余字段")
    result = {}
    for key, answer in answers.items():
        value = answer.get("choice") if isinstance(answer, dict) else answer
        if not isinstance(value, str) or value not in payload["questions"][key]["criteria"]:
            raise ValueError("返回了候选集合之外的选项")
        result[key] = value
    return result


def score(expected, observed):
    fields = {}
    for key, wanted in expected.items():
        got = observed.get(key)
        fields[key] = (
            "unanswered" if got is None else "correct" if got == wanted else
            "extra" if wanted == "omit" else "missing" if got == "omit" else "wrong_value"
        )
    return {"correct": observed == expected, "matched": sum(v == "correct" for v in fields.values()),
            "total": len(expected), "fields": fields}


def gpt_decide(client, payload):
    response = client.converse(
        modelId=GPT_MODEL, system=[{"text": GPT_SYSTEM}],
        messages=[{"role": "user", "content": [
            {"text": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}]}],
        inferenceConfig={"maxTokens": 8192},
        additionalModelRequestFields={"reasoning": {"effort": "low"}},
    )
    if response.get("stopReason") != "end_turn":
        raise ValueError("GPT 返回未完成")
    text = "".join(c.get("text", "") for c in response["output"]["message"]["content"]).strip()
    # Match the benchmark transport's permitted Markdown envelope.
    import re
    fenced = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    decoded = json.loads(fenced[1] if fenced else text)
    if not isinstance(decoded, dict) or set(decoded) != {"answers"}:
        raise ValueError("GPT 输出格式无效")
    selections(decoded, payload)
    return {**decoded, "model": GPT_MODEL, "usage": response.get("usage"), "raw_output": text}


class ACRuns:
    def __init__(self):
        self.jobs, self.tasks = {}, set()
        self.url = os.getenv("AC_LORA_URL", "").rstrip("/")
        self.token = os.getenv("AC_LORA_TOKEN", "")

    async def close(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    def public(self, job):
        return copy.deepcopy({k: v for k, v in job.items() if not k.startswith("_")})

    def owned(self, job_id, owner):
        job = self.jobs.get(job_id)
        if not job or job["_owner"] != owner:
            raise HTTPException(404, "这轮记录不存在或已过期")
        return job

    def start(self, request, body):
        if len(set(body.case_ids)) != len(body.case_ids) or any(k not in CASES for k in body.case_ids):
            raise HTTPException(422, "请选择有效且不重复的场景")
        if body.field not in TEMPLATE["questions"]:
            raise HTTPException(422, "请选择有效的单步字段")
        if any(j["status"] == "running" for j in self.jobs.values()):
            raise HTTPException(409, "已有空调对比正在运行，请等待当前轮结束")
        self.jobs = {k: j for k, j in self.jobs.items() if time.monotonic() - j["_started"] < 7200}
        while len(self.jobs) >= 5:
            del self.jobs[next(iter(self.jobs))]
        layouts = ["single", "serial30", "full30"] if body.mode == "all" else [body.mode]
        records = []
        for case_id in body.case_ids:
            for layout in layouts:
                for provider in PROVIDERS:
                    records.append({"case_id": case_id, "layout": layout, "provider": provider["id"],
                                    "status": "queued", "calls": [], "choices": {}, "score": None,
                                    "elapsed_ms": None, "model": None})
        job = {"id": secrets.token_urlsafe(24), "_owner": request.state.user["username"],
               "_started": time.monotonic(), "version": DATA["version"], "source": "live",
               "status": "running", "cancel_requested": False, "config": body.model_dump(),
               "records": records, "completed": 0, "total": len(records), "elapsed_ms": None}
        self.jobs[job["id"]] = job
        task = asyncio.create_task(self.run(request, job))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return self.public(job)

    async def infer(self, request, provider, payload):
        if provider == "liquid_lora":
            if not self.url:
                raise HTTPException(503, "Liquid LoRA 服务尚未配置")
            headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
            response = await request.app.state.client.post(
                self.url + "/v1/systemone", json=payload, headers=headers, timeout=120)
            response.raise_for_status()
            raw = response.json()
            if raw.get("model") != "LiquidAI/d1-2B" or raw.get("adapter_sha256") != ADAPTER:
                raise ValueError("Liquid 返回的模型或微调检查点身份不符")
            return raw
        client = getattr(request.app.state, "jev" if provider == "jev" else "bedrock")
        if client is None:
            raise HTTPException(503, "模型服务尚未配置")
        slots = getattr(request.app.state, "jev_slots" if provider == "jev" else "bedrock_slots")
        async with slots:
            return await run_in_threadpool(client.system_one if provider == "jev"
                                           else lambda p: gpt_decide(client, p), payload)

    async def run(self, request, job):
        try:
            for record in job["records"]:
                if job["cancel_requested"]:
                    record["status"] = "cancelled"
                    continue
                config = job["config"]
                payload = payload_for(record["case_id"], config["order"])
                expected = expected_for(record["case_id"])
                keys = [config["field"]] if record["layout"] == "single" else list(payload["questions"])
                expected = {k: expected[k] for k in keys}
                groups = [keys] if record["layout"] == "full30" else [[k] for k in keys]
                record.update(status="running", expected=expected)
                started = time.perf_counter()
                for group in groups:
                    if job["cancel_requested"]:
                        break
                    wire = {"state": payload["state"],
                            "questions": {k: payload["questions"][k] for k in group}}
                    call = {"keys": group, "input_sha256": fingerprint(wire), "status": "running"}
                    record["calls"].append(call)
                    tick = time.perf_counter()
                    try:
                        raw = await self.infer(request, record["provider"], wire)
                        call["raw"] = raw
                        choices = selections(raw, wire)
                        if record["model"] is not None and record["model"] != raw.get("model"):
                            raise ValueError("同一任务内模型版本发生变化")
                        record["model"] = raw.get("model")
                        call.update(status="ok", choices=choices)
                        record["choices"].update(choices)
                    except Exception as exc:
                        log.warning("AC provider=%s error=%s", record["provider"], type(exc).__name__)
                        detail = getattr(exc, "detail", None)
                        call.update(status="error", error=detail if isinstance(detail, str)
                                    else "本次调用失败或响应无效，未重试或使用替代结果",
                                    error_type=type(exc).__name__)
                    finally:
                        call["elapsed_ms"] = (time.perf_counter() - tick) * 1000
                    # Stop this provider/task after an interface failure; never fill absent fields.
                    if call["status"] == "error":
                        break
                record["elapsed_ms"] = (time.perf_counter() - started) * 1000
                record["score"] = score(expected, record["choices"])
                record["status"] = ("cancelled" if job["cancel_requested"] else "error"
                                    if any(c["status"] == "error" for c in record["calls"]) else "done")
                job["completed"] += 1
        finally:
            job["status"] = "cancelled" if job["cancel_requested"] else "done"
            job["elapsed_ms"] = (time.monotonic() - job["_started"]) * 1000


@router.get("/catalog")
def catalog(request: Request):
    return {"version": DATA["version"], "providers": PROVIDERS, "cases": list(CASES.values()),
            "fields": FIELD_NAMES, "template": TEMPLATE,
            "candidate_orders": {k: list(q["criteria"]) for k, q in TEMPLATE["questions"].items()},
            "configured": {"liquid_lora": bool(request.app.state.ac_control.url),
                           "jev": request.app.state.jev is not None,
                           "gpt": request.app.state.bedrock is not None}}


@router.post("/runs", status_code=202)
async def start(body: RunRequest, request: Request):
    return request.app.state.ac_control.start(request, body)


@router.get("/runs/{job_id}")
async def result(job_id: str, request: Request):
    runs = request.app.state.ac_control
    return runs.public(runs.owned(job_id, request.state.user["username"]))


@router.post("/runs/{job_id}/cancel")
async def cancel(job_id: str, request: Request):
    runs = request.app.state.ac_control
    job = runs.owned(job_id, request.state.user["username"])
    if job["status"] == "running":
        job["cancel_requested"] = True
    return runs.public(job)
