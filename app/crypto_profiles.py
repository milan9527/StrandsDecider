"""Scenario-scoped model inputs; no reference answers or execution policy changes."""

from typing import Literal

InputProfile = Literal["baseline", "optimized"]

SCOPED_CRITERIA = {
    "intake": {
        "payment_support": "Only case_type=pending or underpaid: route this deposit inquiry to payment support.",
        "refund_support": "Only case_type=refund: route this refund request to refund support.",
        "merchant_ops": "Only case_type=settlement: route this merchant payout inquiry to merchant operations.",
    },
    "verify": {
        "await_confirmations": "Only pending, underpaid or refund: confirmed=false. Check confirmations before checking a shortfall.",
        "request_topup": "Only pending, underpaid or refund: confirmed=true AND fully_paid=false.",
        "payment_verified": "Only pending, underpaid or refund: confirmed=true AND fully_paid=true.",
        "settlement_delayed": "Only settlement: settled=false AND settlement_overdue=true.",
        "settlement_pending": "Only settlement: settled=false AND settlement_overdue=false.",
        "settlement_verified": "Only settlement: settled=true.",
    },
    "approve": {
        "risk_review": "Any case_type: risk_flag=true. Risk takes precedence over all other approval choices.",
        "verify_destination": "Only refund: risk_flag=false AND refund_destination_verified=false.",
        "await_approval": "Only refund: risk_flag=false AND refund_destination_verified=true AND refund_approved=false. Never use this for pending, underpaid or settlement.",
        "approved": "For pending, underpaid or settlement: risk_flag=false is sufficient at this approval stage; refund approval is not applicable. For refund: risk_flag=false AND refund_destination_verified=true AND refund_approved=true. This does not authorize funds before the execute-stage conditions are met.",
    },
    "execute": {
        "hold": "Any case: risk_flag=true. Also pending/underpaid: payment_verified=false. Also refund: payment_verified=false OR refund_destination_verified=false OR refund_approved=false. Missing refund fields in other case types are NOT a reason to hold.",
        "credit_order": "Only pending or underpaid: risk_flag=false AND payment_verified=true. Refund approval is not applicable.",
        "refund_payment": "Only refund: risk_flag=false AND payment_verified=true AND refund_destination_verified=true AND refund_approved=true.",
        "escalate_settlement": "Only settlement: risk_flag=false AND settled=false AND settlement_overdue=true.",
        "wait_settlement": "Only settlement: risk_flag=false AND settled=false AND settlement_overdue=false.",
        "reconcile_settlement": "Only settlement: risk_flag=false AND settled=true.",
    },
    "close": {
        "resolve": "Any case_type: business_complete=true AND risk_flag=false. Receipt/confirmation applies to pending and underpaid; refunds additionally require a verified destination and approval; settlement requires settled=true.",
        "follow_up": "Any case_type: business_complete=false OR risk_flag=true. Continue following up on the applicable unmet condition.",
    },
}

COMMON_FIELDS = {"case_type", "customer_message", "risk_flag", "business_complete"}
PAYMENT_FIELDS = {
    "expected_amount",
    "received_amount",
    "shortfall",
    "fully_paid",
    "confirmations",
    "required_confirmations",
    "confirmed",
    "payment_verified",
}
REFUND_FIELDS = {"refund_destination_verified", "refund_approved"}
SETTLEMENT_FIELDS = {
    "settlement_minutes",
    "settlement_sla_minutes",
    "settlement_overdue",
    "settled",
}

PROFILE_NOTES = {
    "pending": "收款仅保留金额、确认数与风险事实；退款审批和商户结算不适用。",
    "underpaid": "少付仅保留金额差额、确认数与风险事实；退款审批和商户结算不适用。",
    "refund": "退款保留金额、确认数、地址验证与人工审批；商户结算不适用。",
    "settlement": "结算仅保留到账、SLA 与风险事实；收款确认数和退款审批不适用。",
}


def scoped_state(state):
    case = state["case_type"]
    fields = COMMON_FIELDS | (SETTLEMENT_FIELDS if case == "settlement" else PAYMENT_FIELDS)
    if case == "refund":
        fields |= REFUND_FIELDS
    return {key: value for key, value in state.items() if key in fields}


SCOPED_INSTRUCTIONS = (
    " First identify case_type and apply only criteria for that case type. "
    "pending and underpaid are incoming deposits, refund is a refund, and settlement is a "
    "merchant payout. Fields omitted for a different case type are not applicable, not failed "
    "checks. In particular, non-refund cases never require refund destination verification "
    "or refund approval. Approval and execution are separate stages: passing approval does "
    "not imply that funds have arrived."
)
