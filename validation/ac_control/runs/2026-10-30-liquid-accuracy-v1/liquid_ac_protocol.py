"""AC strategies with no evaluation answers or query-dependent candidate pruning."""

import copy
import json

from ablation_protocol import gate_payload, make_payload

STRATEGIES = ("baseline", "two_stage", "semantic_gate", "temperature_bundle", "bundle_examples")
TEMPERATURE_KEYS = ("t_temp", "t_temp_f", "t_temp_type")
TEMPERATURE_ACTION = "temperature_action"

# General semantic distinctions, fixed for every request.
SCOPES = {
    "t_power": "switching the whole air conditioner on or off; a feature switch is not main power",
    "t_work_mode": "changing the main mode to fan-only, heating, cooling, drying or automatic mode; independent features are not modes",
    "t_temp": "setting a supported target temperature in Celsius; frost protection and demand-response offset are separate functions",
    "t_temp_f": "setting a supported target temperature in Fahrenheit; do not convert Celsius requests",
    "t_temp_type": "the unit accompanying any supported temperature setpoint, or an explicit unit-only change",
    "t_fan_mute": "enabling or disabling quiet operation of the indoor unit; outdoor quiet is a different feature",
    "t_outdoor_mute": "enabling or disabling quiet operation of the outdoor unit; indoor quiet is a different feature",
    "t_up_down": "enabling or disabling continuous vertical/up-and-down oscillation",
    "t_swing_angle": "selecting a fixed vertical airflow position or automatic vertical position; continuous vertical oscillation uses the separate up-and-down switch",
    "t_swing_direction": "selecting an explicit horizontal airflow direction such as straight, left, right or both sides",
    "t_left_right": "enabling or disabling the basic left-and-right swing switch",
    "t_8heat": "enabling or disabling 8-degree frost-protection heating; this does not select Heat operating mode",
    "t_indoortemp_detection": "enabling or disabling Comfort Auto; this is separate from Auto operating mode",
    "t_purify": "enabling or disabling air purification; ventilation/fresh air and the display light are different functions",
    "t_dimmer": "switching the display/panel light on or off; this does not switch main power or purification",
    "t_fresh_air": "enabling or disabling fresh-air ventilation; healthy wind and purification are different functions",
    "t_health_fan": "enabling or disabling healthy wind; fresh-air ventilation is a different function",
    "t_tms": "enabling or disabling AI Smart/TMS; AI Wind human-sensing airflow is a different function",
    "t_swing_follow": "turning AI Wind off, towards people, or away from people; AI Smart/TMS is a different function",
    "t_dr_onoff": "explicitly enabling or disabling demand response",
    "t_dr_offset": "setting the demand-response temperature offset; target temperature and frost protection are different settings",
    "t_dr_mode": "setting the demand-response load/capacity percentage",
    TEMPERATURE_ACTION: "setting a supported Celsius or Fahrenheit target temperature including its required unit, or changing only the temperature unit",
}

EXAMPLES = [
    {"request": "Switch the appliance off, preserving all feature settings.",
     "action": "Main power OFF. An explicit OFF is an action; unmentioned features get no command."},
    {"request": "Keep the appliance's power unchanged.",
     "action": "No main power command. Keeping unchanged is not switching off."},
    {"request": "Make the target 19 degrees Celsius.",
     "action": "One Celsius setpoint action: temperature 19 plus Celsius unit. No Fahrenheit conversion or other action."},
    {"request": "Turn frost-protection heating off.",
     "action": "Only the frost-protection switch changes. No target-temperature or main-mode command."},
    {"request": "Deactivate outdoor quiet; leave indoor quiet as it is.",
     "action": "Only outdoor quiet OFF. No indoor-quiet command."},
    {"request": "Start air purification without changing ventilation.",
     "action": "Only purification ON. No fresh-air/ventilation or display-light command."},
]


def reverse_if(values, reverse):
    return dict(reversed(list(values.items()))) if reverse else values


def is_reversed(base):
    return list(next(iter(base["questions"].values()))["criteria"])[-1] == "omit"


def bundle_temperature(combined, reverse):
    """Model selects a complete semantic action; mapping is fixed by the catalogue."""
    state = json.loads(combined["state"])
    catalog = {command["key"]: command for command in state["commandSet"]}
    criteria = {"omit": "No supported target-temperature setting or temperature-unit change is requested."}
    mapping = {"omit": {}}
    for key, scale, unit in (("t_temp", "Celsius", "0"), ("t_temp_f", "Fahrenheit", "1")):
        command = catalog[key]
        for value in range(command["min"], command["max"] + 1):
            candidate = key + ":" + str(value)
            criteria[candidate] = f"Set the target temperature to {value} degrees {scale}, with the required {scale} unit."
            mapping[candidate] = {key: str(value), "t_temp_type": unit}
    for value, label in catalog["t_temp_type"]["options"].items():
        candidate = "unit:" + value
        criteria[candidate] = f"Change only the temperature unit to {label}; no new target temperature is requested."
        mapping[candidate] = {"t_temp_type": value}
    question = {
        "type": "choice",
        "instructions": (
            "Choose the complete temperature action requested by query. A setpoint and its unit "
            "are one action. Preserve the requested scale and number; never convert or approximate. "
            "Frost-protection heating and demand-response offset are not target temperatures. "
            "If the requested setpoint is outside the supported range, choose omit. "
            "Unit-only candidates apply only to an explicit unit-only change."
        ),
        "criteria": reverse_if(criteria, reverse),
    }
    questions = {}
    for key, original in combined["questions"].items():
        if key == "t_temp":
            questions[TEMPERATURE_ACTION] = question
        elif key not in TEMPERATURE_KEYS:
            questions[key] = original
    return {"state": combined["state"], "questions": questions}, mapping


def semantic_gate(values, reverse):
    state = json.loads(values["state"])
    catalog = {command["key"]: command for command in state["commandSet"]}
    questions = {}
    for key in values["questions"]:
        scope = SCOPES.get(key, "changing " + catalog.get(key, {}).get("name", key))
        criteria = {
            "omit": f"The current user query requests no change to this function, or explicitly keeps it unchanged: {scope}.",
            "apply": f"The current user query requests this function to change, including an explicit OFF or a required unit: {scope}.",
            "review": f"The query appears to request a change related to this function, but its exact applicability needs a second check: {scope}.",
        }
        questions[key] = {
            "type": "choice",
            "instructions": (
                f"Does the current query request {scope}? Judge only this function. "
                "Its availability in commandSet is not a request. An explicit disable/stop/off counts "
                "as a requested change. Unmentioned or explicitly unchanged functions get omit. "
                "Select all compatible requested functions independently. Use review only for "
                "a related change in the current query, not merely because a capability exists. "
                "Examples illustrate rules; only query describes the current user request."
            ),
            "criteria": reverse_if(criteria, reverse),
        }
    return {"state": values["state"], "questions": questions}


def prepare_strategy(base, strategy):
    if strategy not in STRATEGIES:
        raise ValueError("Unknown strategy")
    if strategy == "baseline":
        return {"first": copy.deepcopy(base), "values": None, "mapping": {}}
    values = make_payload(base, "two_stage")
    reverse = is_reversed(base)
    if strategy == "two_stage":
        return {"first": gate_payload(values, reverse), "values": values, "mapping": {}}
    mapping = {}
    if strategy in ("temperature_bundle", "bundle_examples"):
        values, mapping = bundle_temperature(values, reverse)
    if strategy == "bundle_examples":
        state = json.loads(values["state"])
        state["demonstrations"] = copy.deepcopy(EXAMPLES)
        state["rules"] += " Demonstrations are examples, not additional user requests; decide only the top-level query."
        values["state"] = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    return {"first": semantic_gate(values, reverse), "values": values, "mapping": mapping}


def second_stage(prepared, gate_choices):
    if set(gate_choices) != set(prepared["first"]["questions"]):
        raise ValueError("Gate must answer exactly its supplied questions")
    for key, choice in gate_choices.items():
        if choice not in prepared["first"]["questions"][key]["criteria"]:
            raise ValueError("Illegal gate choice")
    questions = {key: value for key, value in prepared["values"]["questions"].items()
                 if gate_choices[key] in ("apply", "review")}
    return {"state": prepared["values"]["state"], "questions": questions} if questions else None


def decode_commands(base, prepared, selections):
    """Expand declared action candidates; never inspect the user's text or references."""
    values = prepared["values"] or prepared["first"]
    commands = {}
    for key, value in selections.items():
        if key not in values["questions"] or value not in values["questions"][key]["criteria"]:
            raise ValueError("Selection outside supplied candidates")
        if value == "omit":
            continue
        expansion = prepared["mapping"][value] if key == TEMPERATURE_ACTION else {key: value}
        for raw_key, raw_value in expansion.items():
            if raw_key in commands and commands[raw_key] != raw_value:
                raise ValueError("Conflicting protocol actions")
            if raw_value not in base["questions"][raw_key]["criteria"] or raw_value == "omit":
                raise ValueError("Expanded action is not legal for the original capability")
            commands[raw_key] = raw_value
    return [{"cmdKey": key, "cmdValue": commands[key]} for key in base["questions"] if key in commands]
