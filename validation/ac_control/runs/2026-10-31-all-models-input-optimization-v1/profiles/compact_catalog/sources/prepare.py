"""Freeze specification-derived requests separately from offline references."""

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "docs/AC_Control_Test_Spec.md"
OMIT = "omit"

# General capability semantics from section 2.1, independent of test queries.
NOTES = {
    "t_power": "Main appliance power only; not the switch for an individual feature.",
    "t_work_mode": "Main operating mode. Auto mode is different from Comfort Auto.",
    "t_temp": "Celsius setpoint only. A Celsius temperature requires t_temp_type=0 too.",
    "t_temp_f": "Fahrenheit setpoint only. A Fahrenheit temperature requires t_temp_type=1 too. Do not convert to Celsius.",
    "t_temp_type": "Required companion of a temperature setting: Celsius=0, Fahrenheit=1.",
    "t_fan_speed": "Fan speed. Turbo/Super is a separate function, not a fan speed.",
    "t_fan_mute": "Indoor unit quiet only; different from outdoor quiet.",
    "t_super": "Super/Turbo/powerful/rapid cooling or heating function; separate from fan speed.",
    "t_up_down": "Continuous up-and-down swing switch; fixed vertical positions use t_swing_angle.",
    "t_indoortemp_detection": "Comfort Auto based on indoor temperature detection; different from Auto operating mode.",
    "t_left_right": "Basic left-and-right swing switch; specific horizontal directions use t_swing_direction.",
    "t_swing_angle": "Vertical airflow position. Use the option value, not the position number in its label.",
    "t_swing_direction": "Horizontal airflow direction. Splayed/both-sides airflow is value 2.",
    "t_eco": "Energy saving/Eco function; not an operating mode value.",
    "t_purify": "Air purification; different from the LED display/Dimmer.",
    "t_swing_follow": "AI Wind human-sensing airflow; different from AI Smart/TMS.",
    "t_8heat": "8-degree Celsius frost-protection heating; different from Heat operating mode.",
    "t_sleep": "Sleep profile selection.",
    "t_dimmer": "LED display/panel light; different from air purification. Off=0, On=1.",
    "t_indoor_selfclean": "Clean only the indoor unit.",
    "t_outdoor_selfclean": "Clean only the outdoor unit.",
    "t_onekey_selfclean": "Combined one-key indoor/outdoor self-clean function.",
    "t_fresh_air": "Fresh air/ventilation function; different from Healthy Wind.",
    "t_tms": "General AI Smart/TMS function; different from AI Wind.",
    "t_health_fan": "Healthy Wind function; different from Fresh Air.",
    "t_outdoor_mute": "Outdoor unit quiet only; different from indoor Quiet.",
    "t_dr_onoff": "Demand Response main switch.",
    "t_dr_offset": "Demand Response temperature offset.",
    "t_dr_mode": "Demand Response load/capacity percentage.",
    "t_auto_defrost_clean": "Only values 0 and 1 are user-controllable. Values 2, 3 and 4 describe running status and must never be commanded.",
}
RULES = (
    "Select all and only the compatible settings explicitly requested by query. "
    "Use only the supplied commandSet keys and legal values. "
    "Do not add implied power, mode, fan speed or feature changes. "
    "Do not approximate unsupported values. "
    "A Celsius setpoint requires both t_temp and t_temp_type=0; "
    "a Fahrenheit setpoint requires both t_temp_f and t_temp_type=1. "
    "If a command is not requested (and is not the required temperature-unit companion), "
    "choose omit; omit means no command, while value 0 is an actual setting."
)


def wire(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def sha(value):
    return hashlib.sha256(wire(value).encode()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def read_spec(path=SPEC):
    text = path.read_text()
    section = text.split("### 2.2", 1)[1].split("## 3.", 1)[0]
    capabilities = json.loads(re.search(r"```json\n(.*?)\n```", section, re.S)[1])
    cases = []
    for match in re.finditer(
        r"#### ([SM]\d{2}) — ([^\n]+)\n(.*?)(?=\n#### |\n### |\n## |\Z)", text, re.S
    ):
        case_id, title, body = match.groups()
        cases.append({
            "id": case_id,
            "title": title,
            "category": "single" if case_id.startswith("S") else "multi",
            "query": re.search(r"```text\n(.*?)\n```", body, re.S)[1],
            "expected": json.loads(re.search(r"```json\n(.*?)\n```", body, re.S)[1]),
        })
    if len(capabilities["commandSet"]) != 30 or len(cases) != 20:
        raise ValueError("Expected the specified 30 capabilities and 20 cases")
    if set(NOTES) != {c["key"] for c in capabilities["commandSet"]}:
        raise ValueError("Capability notes do not match the specification")
    return capabilities, cases


def payload(query, capabilities, reverse=False):
    questions = {}
    for command in capabilities["commandSet"]:
        key, name = command["key"], command["name"]
        criteria = {OMIT: f"Do not send {key}: {name} is not requested."}
        if command["type"] == "enum":
            allowed = command.get("userControllableValues", command["options"])
            criteria.update({
                value: f"Set {name} to {label}."
                for value, label in command["options"].items() if value in allowed
            })
        else:
            # All specified test queries request integers. Enumerate the entire
            # integer interval without extracting a number from the query.
            criteria.update({
                str(value): f"{value} {command['unit']}"
                for value in range(command["min"], command["max"] + 1)
            })
        if reverse:
            criteria = dict(reversed(list(criteria.items())))
        questions[key] = {
            "type": "choice",
            "instructions": (
                f"For {name} ({key}), select the value explicitly requested in query, "
                f"or omit if not requested. {NOTES[key]} "
                "Do not infer extra settings from another requested feature."
            ),
            "criteria": criteria,
        }
    return {
        # A compact JSON string avoids upstream pretty-print expansion. The
        # exact standard commandSet, including status-only values, is retained.
        "state": wire({"query": query, **capabilities, "rules": RULES}),
        "questions": questions,
    }


def prepare(output, spec=SPEC):
    capabilities, cases = read_spec(spec)
    output.mkdir(parents=True, exist_ok=False)
    (output / "spec.md").write_bytes(spec.read_bytes())
    requests = [
        {"case_id": case["id"], "variant": variant,
         "payload": payload(case["query"], capabilities, variant == "reversed")}
        for case in cases for variant in ("original", "reversed")
    ]
    for request in requests:
        request["input_sha256"] = sha(request["payload"])
    save(output / "command_set.json", capabilities)
    save(output / "references.json", cases)
    save(output / "requests.json", requests)
    save(output / "plan.json", {
        "prepared_at": datetime.now(UTC).isoformat(),
        "spec_sha256": hashlib.sha256(spec.read_bytes()).hexdigest(),
        "requests_sha256": sha(requests),
        "references_sha256": sha(cases),
        "cases": len(cases),
        "variants": ["original", "reversed"],
        "formal_http_requests": len(requests),
        "questions_per_request": 30,
        "primary_result": "original candidate order, 20 cases",
        "robustness_result": "reversed candidate order, same 20 cases; not independent samples",
        "range_representation": "All integers in each legal interval; fractional values untested",
        "decoder": "One choice per key; omit is removed. No other repair, defaults or unit completion.",
        "retry_policy": "No automatic retries; transport and format failures remain failures.",
        "timing": "Service latency_ms (includes queue/preprocessing) and client HTTP round trip; not pure GPU time.",
        "source_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(__file__).parent.glob("*.py"))
        },
    })
    print(f"Prepared {len(cases)} cases, {len(requests)} requests at {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--spec", type=Path, default=SPEC)
    args = parser.parse_args()
    prepare(args.output, args.spec)
