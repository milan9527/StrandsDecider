"""Bounded, feedback-driven sandbox runs. State is carried by the authenticated page."""

from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from pydantic import Field

from app.crypto import (
    STAGES,
    Decision,
    Event,
    ExecutionFeedback,
    Snapshot,
    Stage,
    Transition,
    apply,
    decision,
    event,
    facts,
    reply_text,
)
from app.schemas import StrictModel

router = APIRouter(prefix="/api/crypto/loop", tags=["Payment feedback loop"])
STAGE_IDS = [row["id"] for row in STAGES]
MAX_DECISIONS = 20
MAX_TICKS = 32
MAX_NO_PROGRESS = 2
EventName = Literal["confirm", "topup", "verify_address", "approve", "clear_risk", "settle"]
EVENT_LABELS = {
    "confirm": "链上确认达标",
    "topup": "补足差额",
    "verify_address": "验证退款地址",
    "approve": "人工审批通过",
    "clear_risk": "人工解除风险",
    "settle": "结算到账",
}


class LoopLedger(StrictModel):
    type: Literal["credit_order", "refund_payment", "reconcile_settlement"]
    amount: str = Field(max_length=40)
    simulated: Literal[True] = True
    operation_id: str = Field(max_length=100)


class LoopState(StrictModel):
    run_id: UUID = Field(default_factory=uuid4)
    snapshot: Snapshot
    next_stage: Stage = "intake"
    status: Literal["running", "waiting", "complete", "handoff"] = "running"
    reason: str = Field(default="", max_length=800)
    decisions: int = Field(default=0, ge=0, le=MAX_DECISIONS)
    ticks: int = Field(default=0, ge=0, le=MAX_TICKS)
    no_progress: int = Field(default=0, ge=0, le=MAX_NO_PROGRESS)
    feedback: list[ExecutionFeedback] = Field(default_factory=list, max_length=8)
    waiting_events: list[EventName] = Field(default_factory=list, max_length=6)
    ledger: LoopLedger | None = None


class LoopRequest(StrictModel):
    state: LoopState
    provider: Literal["decider", "bedrock"]
    mode: Literal["live", "replay"] = "live"
    auto_events: bool = False


def target(s):
    return {
        "refund": ("refunded", "refund_payment"),
        "settlement": ("settled", "reconcile_settlement"),
    }.get(s.scenario, ("paid", "credit_order"))


def done(state):
    order, action = target(state.snapshot)
    return bool(
        state.ledger
        and state.ledger.type == action
        and state.snapshot.order_status == order
        and state.snapshot.ticket_status == "resolved"
        and not state.snapshot.review_pending
        and facts(state.snapshot)["business_complete"]
    )


def missing_events(s, stage):
    """Observable prerequisites, independent of the model/reference answer."""
    if s.risk_flag:
        return ["clear_risk"]
    if stage == "verify":
        if s.scenario == "settlement":
            return [] if s.settled else ["settle"]
        return [
            name
            for name, missing in (
                ("confirm", s.confirmations < s.required_confirmations),
                ("topup", s.received < s.expected),
            )
            if missing
        ]
    if s.scenario == "refund" and stage in ("approve", "execute"):
        return [
            name
            for name, missing in (
                ("verify_address", not s.address_verified),
                ("approve", not s.approved),
            )
            if missing
        ]
    return []


def remember(state, stage, status, reason, requested="", actual=""):
    state.reason = reason
    state.feedback = [
        *state.feedback,
        ExecutionFeedback(
            stage=stage,
            status=status,
            reason=reason,
            requested_action=requested,
            actual_action=actual,
        ),
    ][-8:]


def rewind(state, stage):
    state.next_stage = stage
    # Keep only stages that actually ran before the node being reconsidered.
    prefix = STAGE_IDS[: STAGE_IDS.index(stage)]
    state.snapshot.completed = [s for s in prefix if s in state.snapshot.completed]


def retry(state, stage, reason):
    state.no_progress += 1
    state.status = "handoff" if state.no_progress >= MAX_NO_PROGRESS else "running"
    rewind(state, stage)
    if state.status == "handoff":
        return reason + " 同一步连续两次未取得进展，已转人工；未用规则替换模型选择。"
    return reason + " 将携带实际结果重新判断此步骤。"


@router.post("/tick")
async def tick(body: LoopRequest, request: Request):
    state = body.state.model_copy(deep=True)
    result = {"decision": None, "record": None, "event": None}

    def response():
        return {
            **result,
            "state": state.model_dump(mode="json"),
            "limits": {"max_decisions": MAX_DECISIONS, "max_ticks": MAX_TICKS},
            "external_action_executed": False,
        }

    if state.status in ("complete", "handoff"):
        return response()
    if state.ticks >= MAX_TICKS or state.decisions >= MAX_DECISIONS:
        state.status = "handoff"
        state.reason = "已达到本轮调用预算，停止自动处理并转人工。"
        return response()

    if state.status == "waiting":
        # Re-evaluate prerequisites, never trust a client-supplied event list.
        events = missing_events(state.snapshot, state.next_stage)
        state.waiting_events = events
        if events:
            if not body.auto_events or events[0] == "clear_risk":
                return response()
            before = state.snapshot.model_copy(deep=True)
            name = events[0]
            changed = event(Event(snapshot=before, event=name))
            state.snapshot = Snapshot(**changed["snapshot"])
            state.snapshot.completed = [s for s in before.completed if s == "intake"]
            state.next_stage = "verify" if "intake" in before.completed else "intake"
            state.ticks += 1
            state.no_progress = 0
            state.status = "running"
            state.waiting_events = []
            reason = f"模拟器已推进「{EVENT_LABELS[name]}」；这是模拟业务证据更新，不是模型执行的真实交易或审批。请按最新事实重新核验。"
            remember(state, "event", "simulated_event", reason, actual=name)
            result["event"] = {
                "name": name,
                "before": before.model_dump(mode="json"),
                "after": state.snapshot.model_dump(mode="json"),
                "message": reason,
                "source": "simulator",
            }
            return response()
        state.status = "running"

    stage = state.next_stage
    # A completed financial action is never submitted a second time in this run.
    if stage == "execute" and state.ledger:
        state.next_stage = "close"
        stage = "close"
    chosen = await decision(
        Decision(
            snapshot=state.snapshot,
            stage=stage,
            provider=body.provider,
            mode=body.mode,
            execution_feedback=state.feedback,
        ),
        request,
    )
    applied = apply(Transition(snapshot=state.snapshot, stage=stage, choice=chosen["choice"]))
    state.decisions += 1
    state.ticks += 1
    state.snapshot = Snapshot(**applied["snapshot"])
    result["decision"] = chosen
    result["record"] = {"stage": stage, **applied}
    reason = applied["safety_reason"] or "本步实际执行结果已记录。"
    feedback_status = "succeeded"
    if applied["ledger_entry"]:
        state.ledger = LoopLedger(
            **applied["ledger_entry"],
            operation_id=f"{state.run_id}:{applied['ledger_entry']['type']}",
        )
        result["record"]["ledger_entry"] = state.ledger.model_dump()

    missing = missing_events(state.snapshot, stage) if stage != "intake" else []
    if missing:
        state.status = "waiting"
        state.waiting_events = missing
        state.no_progress = 0
        state.snapshot.ticket_status = "waiting"
        rewind(state, stage)
        reason = f"业务条件尚未满足，等待：{'、'.join(EVENT_LABELS[name] for name in missing)}。不能通过重复调用模型补齐外部证据。"
        feedback_status = "waiting_external"
        result["record"]["customer_reply"] = reply_text(state.snapshot)
    elif stage == "approve" and state.snapshot.review_pending:
        reason = retry(
            state,
            "approve",
            "当前无风险；非退款业务不要求退款审批，退款业务的地址及审批证据也已满足。此次待复核选择未推进业务。",
        )
        feedback_status = "retry"
    elif stage == "execute" and not state.ledger:
        reason = retry(state, "execute", "资金条件已具备，但实际没有生成账本记录。" + reason)
        feedback_status = "retry"
    elif stage == "close":
        if done(state):
            state.status = "complete"
            reason = "模拟订单、对应账本与工单结案均已确认，业务闭环完成。"
        else:
            reason = retry(
                state,
                "close" if state.ledger else "execute",
                "实际业务尚未结案，请根据已记录的订单与资金状态修正后续选择。",
            )
            feedback_status = "retry"
    else:
        state.no_progress = 0
        state.next_stage = STAGE_IDS[STAGE_IDS.index(stage) + 1]
    if state.status == "handoff":
        feedback_status = "handoff"
    remember(
        state,
        stage,
        feedback_status,
        reason,
        requested=chosen["choice"],
        actual=applied["action"],
    )
    result["record"]["loop_feedback"] = state.feedback[-1].model_dump()
    return response()
