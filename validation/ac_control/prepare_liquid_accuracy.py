"""Freeze development inputs and unused validation inputs before Liquid trials."""

import argparse
import hashlib
import json
from pathlib import Path

from liquid_ac_protocol import STRATEGIES, prepare_strategy
from prepare import payload
from run_resident import save, sha, stamp

HERE = Path(__file__).resolve().parent
SOURCES = ("liquid_ac_protocol.py", "liquid_ac_client.py", "run_liquid_accuracy.py",
           "ablation_protocol.py", "run_ablation.py", "run_resident.py")
VALIDATION = [
    ("L01", "single", "Shut down the AC, leaving its mode and all feature settings alone.", {"t_power": "0"}),
    ("L02", "single", "Select cooling as the operating mode. Make no other changes.", {"t_work_mode": "2"}),
    ("L03", "single", "I'd like a target of 22 degrees Celsius.", {"t_temp": "22", "t_temp_type": "0"}),
    ("L04", "single", "Make the setpoint 75 degrees Fahrenheit.", {"t_temp_f": "75", "t_temp_type": "1"}),
    ("L05", "single", "Quiet down the outdoor unit; keep indoor quiet at its current setting.", {"t_outdoor_mute": "1"}),
    ("L06", "single", "Darken the display panel without touching the main power.", {"t_dimmer": "0"}),
    ("L07", "single", "Deactivate energy-saving mode while keeping the operating mode as it is.", {"t_eco": "0"}),
    ("L08", "multi", "Start fresh-air ventilation and disable healthy wind.", {"t_fresh_air": "1", "t_health_fan": "0"}),
    ("L09", "single", "Turn AI Smart on; preserve the current AI Wind setting.", {"t_tms": "1"}),
    ("L10", "single", "Stop the 8-degree frost-protection function without changing the main mode.", {"t_8heat": "0"}),
    ("L11", "single", "Enable automatic defrost cleaning.", {"t_auto_defrost_clean": "1"}),
    ("L12", "single", "Set demand-response load capacity to 63 percent; leave its offset unchanged.", {"t_dr_mode": "63"}),
    ("L13", "multi", "Heat to 29 degrees Celsius using medium-low fan speed.", {"t_work_mode": "1", "t_temp": "29", "t_temp_type": "0", "t_fan_speed": "6"}),
    ("L14", "multi", "Cool to 67 degrees Fahrenheit and use medium fan speed.", {"t_work_mode": "2", "t_temp_f": "67", "t_temp_type": "1", "t_fan_speed": "7"}),
    ("L15", "multi", "Switch off both the air conditioner and its display light.", {"t_power": "0", "t_dimmer": "0"}),
    ("L16", "multi", "Stop vertical oscillation and direct the horizontal airflow all left.", {"t_up_down": "0", "t_swing_direction": "4"}),
    ("L17", "multi", "Put vertical airflow at Position 4 and enable indoor quiet.", {"t_swing_angle": "5", "t_fan_mute": "1"}),
    ("L18", "single", "Start cleaning the indoor unit only, leaving outdoor cleaning unchanged.", {"t_indoor_selfclean": "1"}),
    ("L19", "multi", "Choose the elder sleep profile and turn the panel light off.", {"t_sleep": "2", "t_dimmer": "0"}),
    ("L20", "multi", "Turn demand response on, set its offset to 4 degrees and its capacity to 37 percent.", {"t_dr_onoff": "1", "t_dr_offset": "4", "t_dr_mode": "37"}),
    ("L21", "multi", "Start the up-and-down oscillation and send horizontal air to both sides.", {"t_up_down": "1", "t_swing_direction": "2"}),
    ("L22", "single", "Activate purification while preserving the fresh-air setting.", {"t_purify": "1"}),
    ("L23", "single", "Keep every setting exactly as it is.", {}),
    ("L24", "single", "Set the target temperature to 35 degrees Celsius.", {}),
]


def prepare(root):
    root.mkdir(parents=True, exist_ok=False)
    previous = HERE / "runs/2026-10-30-api-ablation-v1/references.json"
    refs = json.loads(previous.read_text())
    capabilities = json.loads((HERE / "runs/2026-10-30-v1/command_set.json").read_text())
    catalog = {command["key"]: command for command in capabilities["commandSet"]}
    refs.extend({
        "id": key, "category": category, "query": query, "dataset": "validation",
        "expected": [{"cmdKey": command, "cmdValue": value} for command, value in expected.items()],
        "reference_basis": "Frozen AC protocol; explicit supported changes only; an unsupported setpoint emits no temperature or unit command.",
    } for key, category, query, expected in VALIDATION)
    for ref in refs:
        for command in ref["expected"]:
            key, value = command["cmdKey"], str(command["cmdValue"])
            entry = catalog[key]
            legal = entry.get("userControllableValues", entry.get("options")) if entry["type"] == "enum" else [
                str(n) for n in range(entry["min"], entry["max"] + 1)]
            assert value in legal
    datasets = {}
    for phase in ("development", "validation"):
        records = []
        for case in refs:
            if (case["dataset"] == "validation") != (phase == "validation"):
                continue
            for order in ("original", "reversed"):
                base = payload(case["query"], capabilities, order == "reversed")
                # Force strategy construction before any inference; no input-dependent pruning.
                for strategy in STRATEGIES:
                    prepare_strategy(base, strategy)
                records.append({
                    "case_id": case["id"], "dataset": case["dataset"], "category": case["category"],
                    "order": order, "payload": base, "input_sha256": sha(base),
                })
        datasets[phase] = records
        save(root / (phase + "_cases.json"), records)
    save(root / "references.json", refs)
    save(root / "command_set.json", capabilities)
    sources = root / "sources"
    sources.mkdir()
    for name in SOURCES:
        (sources / name).write_bytes((HERE / name).read_bytes())
    save(root / "plan.json", {
        "prepared_at": stamp(), "model": "LiquidAI/d1-2B", "strategies": list(STRATEGIES),
        "development_observations": len(datasets["development"]) * len(STRATEGIES),
        "validation_cases": len(VALIDATION), "orders": ["original", "reversed"],
        "development_sha256": sha(datasets["development"]), "validation_sha256": sha(datasets["validation"]),
        "references_sha256": sha(refs), "capabilities_sha256": sha(capabilities),
        "source_sha256": {name: hashlib.sha256((sources / name).read_bytes()).hexdigest() for name in SOURCES},
        "old_reference_source_sha256": hashlib.sha256(previous.read_bytes()).hexdigest(),
        "selection_policy": (
            "Select before seeing validation outputs. New strategy must improve development original "
            "exact matches versus two_stage, not lower spec or diagnostic original counts, and not "
            "lower total reversed exact matches. Rank by original exact count, then reversed exact "
            "count, fewer missing pairs, fewer extra pairs, lower mean client time. "
            "Validate selected candidate against baseline and two_stage. Recommend only if validation "
            "original exact count improves over two_stage and reversed count is no worse; otherwise "
            "retain two_stage and report the failed generalization."
        ),
        "validation_policy": "24 queries authored with known error categories, frozen before trials; unused for selection, not an external blind benchmark. No further tuning after validation.",
        "request_policy": "All30 capabilities retained in every state; all legal numeric values retained. Bundles declare the changed action schema and expand only a model-selected action.",
        "timing_policy": "One warmup per strategy; external requests strictly serial. Alternate strategy order per case. Record each stage, end-to-end wall time and HTTP sum.",
        "automatic_retries": 0, "external_concurrency": 1,
    })
    print(json.dumps({"run": str(root), "development_observations": 300, "validation_cases": 24}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    prepare(parser.parse_args().run)
