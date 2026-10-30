"""Freeze isolated prompt interventions and a separate diagnostic extension set."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from ablation_protocol import ARMS, gate_payload, make_payload
from prepare import payload, save, sha

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "runs/2026-10-30-v1"
RESIDENT = HERE / "runs/2026-10-30-resident-v1"


def extension(catalog):
    definitions = [
        ("N01", "仅开机，保持模式", "single",
         "Please power on the AC without changing its operating mode.", {"t_power": "1"}),
        ("N02", "舒适自动与主模式区分", "single",
         "Enable Comfort Auto; leave the operating mode unchanged.", {"t_indoortemp_detection": "1"}),
        ("N03", "防冻制热与主模式区分", "single",
         "Enable 8-degree frost protection; leave the operating mode unchanged.", {"t_8heat": "1"}),
        ("N04", "关闭室内静音，保持室外设置", "single",
         "Stop indoor quiet mode, but leave outdoor quiet unchanged.", {"t_fan_mute": "0"}),
        ("N05", "新表达摄氏温度组合", "multi",
         "Use heating at 25 degrees Celsius with low fan speed.",
         {"t_work_mode": "1", "t_temp": "25", "t_temp_type": "0", "t_fan_speed": "5"}),
        ("N06", "新表达华氏温度组合", "multi",
         "Use cooling at 72 degrees Fahrenheit with medium-high fan speed.",
         {"t_work_mode": "2", "t_temp_f": "72", "t_temp_type": "1", "t_fan_speed": "8"}),
        ("N07", "灯光净化，保持电源", "multi",
         "Switch off the display light and switch on air purification; leave the main power setting unchanged.",
         {"t_dimmer": "0", "t_purify": "1"}),
        ("N08", "新数值需求响应", "multi",
         "Enable demand response with a 7-degree temperature offset and 45 percent load capacity.",
         {"t_dr_onoff": "1", "t_dr_offset": "7", "t_dr_mode": "45"}),
        ("N09", "垂直摆风与水平直吹", "multi",
         "Enable vertical oscillation and point horizontal airflow straight ahead.",
         {"t_up_down": "1", "t_swing_direction": "0"}),
        ("N10", "新风与健康风区分", "single",
         "Enable fresh air while keeping healthy wind unchanged.", {"t_fresh_air": "1"}),
    ]
    return [{
        "id": key, "title": title, "category": category, "dataset": "extension",
        "query": query,
        "expected": [{"cmdName": catalog[k]["name"], "cmdKey": k, "cmdValue": v}
                     for k, v in expected.items()],
        "reference_basis": "AC spec section 2 command mapping, explicit-only changes and mandatory temperature unit; unchanged settings emit nothing.",
    } for key, title, category, query, expected in definitions]


def prepare(output):
    output.mkdir(parents=True, exist_ok=False)
    cap = json.loads((BASELINE / "command_set.json").read_text())
    references = json.loads((BASELINE / "references.json").read_text())
    for case in references:
        case["dataset"] = "spec"
    references.extend(extension({c["key"]: c for c in cap["commandSet"]}))
    baseline_rows = json.loads((BASELINE / "requests.json").read_text())
    baseline_lookup = {(r["case_id"], r["variant"]): r["payload"] for r in baseline_rows}
    experiments = []
    for case_index, case in enumerate(references):
        variants = ["original", "reversed"] if case["dataset"] == "spec" else ["original"]
        for variant in variants:
            base = baseline_lookup.get((case["id"], variant))
            if base is None:
                base = payload(case["query"], cap, variant == "reversed")
            # Rotate arm execution order within each case to distribute drift.
            arms = ARMS[case_index % len(ARMS):] + ARMS[:case_index % len(ARMS)]
            for arm in arms:
                combined = make_payload(base, arm)
                first = gate_payload(combined, variant == "reversed") if arm == "two_stage" else combined
                experiments.append({
                    "case_id": case["id"], "dataset": case["dataset"], "variant": variant,
                    "arm": arm, "first_payload": first, "first_sha256": sha(first),
                    "value_payload": combined if arm == "two_stage" else None,
                    "value_sha256": sha(combined) if arm == "two_stage" else None,
                    "reuse_baseline": arm == "baseline" and case["dataset"] == "spec",
                })
    save(output / "experiments.json", experiments)
    save(output / "references.json", references)
    save(output / "command_set.json", cap)
    sources = ["prepare.py", "ablation_protocol.py", "prepare_ablation.py", "run_ablation.py",
               "run_resident.py", "analyze.py", "analyze_ablation.py", "compare_resident.py"]
    source_dir = output / "sources"
    source_dir.mkdir()
    for name in sources:
        (source_dir / name).write_bytes((HERE / name).read_bytes())
    save(output / "plan.json", {
        "prepared_at": datetime.now(UTC).isoformat(),
        "arms": ARMS, "models": ["decider", "liquid", "h2o"],
        "spec_cases": 20, "spec_orders": ["original", "reversed"],
        "extension_cases": 10, "extension_orders": ["original"],
        "extension_status": "Diagnostic queries authored after observing baseline errors; frozen before new calls, not a blind external holdout.",
        "experiments_sha256": sha(experiments), "references_sha256": sha(references),
        "command_set_sha256": sha(cap),
        "baseline_requests_sha256": sha(baseline_rows),
        "observations_per_model": len(experiments),
        "new_observations_per_model": sum(not r["reuse_baseline"] for r in experiments),
        "maximum_new_http_calls_per_model": sum(
            2 if r["arm"] == "two_stage" else 1 for r in experiments if not r["reuse_baseline"]
        ),
        "baseline_files": {
            provider: str(path.relative_to(HERE))
            for provider, path in {
                "decider": BASELINE / "formal_receipts.jsonl",
                "liquid": RESIDENT / "liquid/formal_receipts.jsonl",
                "h2o": RESIDENT / "h2o/formal_receipts.jsonl",
            }.items()
        },
        "baseline_sha256": {
            provider: hashlib.sha256(path.read_bytes()).hexdigest()
            for provider, path in {
                "decider": BASELINE / "formal_receipts.jsonl",
                "liquid": RESIDENT / "liquid/formal_receipts.jsonl",
                "h2o": RESIDENT / "h2o/formal_receipts.jsonl",
            }.items()
        },
        "factors": {
            "criteria_only": "Change criteria description strings only; candidate IDs/order, state and instructions unchanged.",
            "rules_only": "Change state.rules and question.instructions only; Query, commandSet and criteria unchanged.",
            "combined": "Apply both factors without gating.",
            "two_stage": "Combined prompt; 30 apply/omit gates, followed by value selection for model-selected keys only. Full commandSet in both stages; stage two retains omit.",
        },
        "automatic_retries": 0, "online_output_repair": False,
        "supplementary_unit_completion": "Offline engineering result only, separate from raw model scores; fill unit only for exactly one temperature scale and no conflicting existing unit.",
        "candidate_count": "Original legal values retained, including every integer in each legal range.",
        "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source_dir.iterdir()},
    })
    print(f"Frozen {len(experiments)} observations/model; {sum(not r['reuse_baseline'] for r in experiments)} new/model")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    prepare(parser.parse_args().output)
