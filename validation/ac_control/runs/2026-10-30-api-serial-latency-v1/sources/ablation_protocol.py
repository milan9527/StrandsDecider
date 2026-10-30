"""Frozen prompt factors and model-driven gating; contains no test answers."""

import copy
import json

ARMS = ["baseline", "criteria_only", "rules_only", "combined", "two_stage"]
NEW_RULES = (
    "TASK: Translate query into only the command changes requested by the user. "
    "query is the user's request. commandSet is a capability catalogue, not a list of requested changes. "
    "Each question concerns exactly one command key. Choose omit when that command is neither "
    "requested nor a mandatory protocol companion. omit sends nothing; value 0 sends a real setting. "
    "Select every requested compatible command, using only supported values and ranges. "
    "Do not add defaults, conversions, or inferred power, mode, fan-speed or feature changes. "
    "Power and main operating mode are independent: turning power on or off alone requests no mode change. "
    "Comfort Auto is separate from Auto operating mode; 8-degree frost-protection heating is separate "
    "from Heat operating mode. A Celsius setpoint requires t_temp and t_temp_type=0; "
    "a Fahrenheit setpoint requires t_temp_f and t_temp_type=1. The user does not need to "
    "separately request the unit companion. When both vertical swing keys are available, "
    "a request to enable or disable continuous vertical swing uses t_up_down only; "
    "do not additionally emit t_swing_angle=0 for the same request. Fixed vertical positions "
    "use t_swing_angle. A generic horizontal swing toggle uses t_left_right; "
    "an explicitly requested horizontal direction uses t_swing_direction. "
    "An independent feature request does not change the main operating mode or other features."
)
MODE_CRITERIA = {
    "omit": "The user does not request a change to the main operating mode.",
    "0": "The user requests Fan or fan-only as the main operating mode.",
    "1": "The user requests Heat or heating as the main operating mode.",
    "2": "The user requests Cool or cooling as the main operating mode.",
    "3": "The user requests Dry or dehumidification as the main operating mode.",
    "4": "The user requests Auto as the main operating mode, rather than the separate Comfort Auto feature.",
}


def conditional_criteria(command):
    key, name = command["key"], command["name"]
    criteria = {"omit": f"The user requests no change to {name}."}
    if key == "t_work_mode":
        return MODE_CRITERIA.copy()
    if key == "t_power":
        return {
            "omit": "The user requests no change to the air conditioner's main power.",
            "0": "The user requests switching the air conditioner's main power off.",
            "1": "The user requests switching the air conditioner's main power on.",
        }
    if key == "t_temp_type":
        return {
            "omit": "Neither a Celsius or Fahrenheit setpoint nor a temperature-unit change is requested.",
            "0": "A Celsius setpoint is requested, or the user explicitly requests Celsius as the unit.",
            "1": "A Fahrenheit setpoint is requested, or the user explicitly requests Fahrenheit as the unit.",
        }
    if command["type"] == "range":
        criteria.update({
            str(v): f"Requested {name} is {v} {command['unit']}."
            for v in range(command["min"], command["max"] + 1)
        })
    else:
        allowed = command.get("userControllableValues", command["options"])
        criteria.update({
            value: f"The user requests {label} for {name}."
            for value, label in command["options"].items() if value in allowed
        })
    return criteria


def make_payload(base, arm):
    """Never reorder keys/candidates or remove capability mappings."""
    result = copy.deepcopy(base)
    state = json.loads(result["state"])
    if arm not in ARMS:
        raise ValueError(arm)
    if arm in {"rules_only", "combined", "two_stage"}:
        state["rules"] = NEW_RULES
        result["state"] = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    for command in state["commandSet"]:
        key = command["key"]
        question = result["questions"][key]
        if arm in {"criteria_only", "combined", "two_stage"}:
            rewritten = conditional_criteria(command)
            question["criteria"] = {v: rewritten[v] for v in question["criteria"]}
        if arm in {"rules_only", "combined", "two_stage"}:
            question["instructions"] = (
                f"Determine the requested change for {command['name']} ({key}) using query. "
                "Apply the command-selection rules in state. Available capabilities are not requests. "
                "Return omit if this key is not requested or required by the protocol."
            )
            # Retain the existing per-capability distinctions, replacing only
            # the ambiguous common framing around them.
            original = base["questions"][key]["instructions"]
            prefix_end = original.index("or omit if not requested. ") + len("or omit if not requested. ")
            note = original[prefix_end:].removesuffix(
                " Do not infer extra settings from another requested feature."
            )
            question["instructions"] += " " + note
            if key == "t_temp_type":
                question["instructions"] = (
                    "Choose the required temperature unit. A Celsius setpoint requires value 0; "
                    "a Fahrenheit setpoint requires value 1, even when no separate unit-change "
                    "command is spoken. Otherwise follow an explicitly requested unit change. "
                    "Choose omit only if no setpoint and no unit change is requested."
                )
            elif key == "t_swing_angle":
                question["instructions"] += (
                    " When t_up_down is available, continuous vertical swing uses t_up_down; "
                    "omit this key rather than duplicating that command as value 0."
                )
    return result


def gate_payload(combined, reverse=False):
    result = {"state": combined["state"], "questions": {}}
    catalog = {c["key"]: c for c in json.loads(combined["state"])["commandSet"]}
    for key in combined["questions"]:
        criteria = {
            "omit": "This command is not requested and is not a mandatory protocol companion.",
            "apply": "This command is requested or is a mandatory protocol companion.",
        }
        if reverse:
            criteria = dict(reversed(list(criteria.items())))
        result["questions"][key] = {
            "type": "choice",
            "instructions": (
                f"Should the response emit a command for {catalog[key]['name']} ({key})? "
                "Decide applicability only. "
                "Read query and the command-selection rules; capability definitions are not user requests. "
                "A required temperature-unit companion counts as applicable. "
                "Respect the distinctions between independent features and between swing keys in the rules. "
                "Choose apply or omit."
            ),
            "criteria": criteria,
        }
    return result


def selected_payload(combined, choices):
    if set(choices) != set(combined["questions"]) or not set(choices.values()) <= {"omit", "apply"}:
        raise ValueError("Gate must supply apply/omit for all 30 keys")
    questions = {
        k: v for k, v in combined["questions"].items() if choices[k] == "apply"
    }
    # Stage two retains omit so a false-positive gate does not force an action.
    return {"state": combined["state"], "questions": questions} if questions else None
