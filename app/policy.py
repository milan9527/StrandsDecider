"""The workflow owns the policy; the model supplies probabilities."""

import json


def tool_state(conversation: str, name: str, arguments: dict) -> str:
    return (
        "A conversation between a user and an AI assistant is below, followed by a "
        "tool call the assistant now wants to make.\n\n"
        f"--- CONVERSATION ---\n{conversation}\n\n"
        f"--- PROPOSED TOOL CALL ---\ntool: {name}\n"
        f"arguments: {json.dumps(arguments, ensure_ascii=False)}"
    )


def review(answers: dict, threshold: float = 0.45) -> dict:
    if answers["args_grounded"]["noul"] < threshold:
        action, reason = "Guide", "城市参数缺乏用户提供的依据，应先向用户确认。"
        feedback = (
            "The arguments are not grounded in what the user said. Ask the user to confirm them."
        )
    elif answers["premature"]["noul"] >= threshold:
        action, reason = "Guide", "调用时机过早，应先补充必要信息。"
        feedback = "It is too early to call this tool. Clarify with the user first."
    else:
        action, reason = "Proceed", "参数有依据且调用时机合适，策略允许执行工具。"
        feedback = ""
    return {"action": action, "reason": reason, "threshold": threshold, "feedback": feedback}
