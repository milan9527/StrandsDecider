"""Freeze H2O official-guidance trials and previously untested validation queries."""

import argparse
import hashlib
import json
from pathlib import Path

from h2o_ac_client import request
from prepare import payload
from run_resident import save, sha, stamp

HERE = Path(__file__).resolve().parent
SOURCES = ("h2o_ac_client.py", "run_h2o_official.py", "ablation_protocol.py",
           "run_ablation.py", "run_resident.py")
VALIDATION = [
    ("H01", "Power the air conditioner on; keep the operating mode unchanged.", {"t_power": "1"}),
    ("H02", "Power the air conditioner off without changing its quiet settings.", {"t_power": "0"}),
    ("H03", "Set a target of 21 degrees Celsius and turn energy saving on.", {"t_temp": "21", "t_temp_type": "0", "t_eco": "1"}),
    ("H04", "Set the target to 73 degrees Fahrenheit with high fan speed.", {"t_temp_f": "73", "t_temp_type": "1", "t_fan_speed": "9"}),
    ("H05", "Enable continuous vertical oscillation; keep horizontal airflow unchanged.", {"t_up_down": "1"}),
    ("H06", "Disable continuous vertical oscillation and point horizontal airflow straight ahead.", {"t_up_down": "0", "t_swing_direction": "0"}),
    ("H07", "Set vertical airflow to Position 2 and horizontal airflow to all right.", {"t_swing_angle": "3", "t_swing_direction": "1"}),
    ("H08", "Turn fresh air off while keeping healthy wind unchanged.", {"t_fresh_air": "0"}),
    ("H09", "Turn healthy wind on without changing fresh-air ventilation.", {"t_health_fan": "1"}),
    ("H10", "Enable 8-degree frost-protection heating, preserving the DR temperature offset.", {"t_8heat": "1"}),
    ("H11", "Disable 8-degree frost protection and turn the display light off.", {"t_8heat": "0", "t_dimmer": "0"}),
    ("H12", "Enable outdoor quiet and disable indoor quiet.", {"t_outdoor_mute": "1", "t_fan_mute": "0"}),
    ("H13", "Switch to heating mode and choose low fan speed; leave the target temperature unchanged.", {"t_work_mode": "1", "t_fan_speed": "5"}),
    ("H14", "Select Comfort Auto without changing the operating mode.", {"t_indoortemp_detection": "1"}),
    ("H15", "Select Auto operating mode while leaving Comfort Auto unchanged.", {"t_work_mode": "4"}),
    ("H16", "Turn AI Smart off and set AI Wind to blow towards people.", {"t_tms": "0", "t_swing_follow": "1"}),
    ("H17", "Start outdoor self-cleaning; keep indoor self-cleaning unchanged.", {"t_outdoor_selfclean": "1"}),
    ("H18", "Activate one-key self-cleaning without changing the separate indoor and outdoor self-clean switches.", {"t_onekey_selfclean": "1"}),
    ("H19", "Choose the youth sleep profile and enable air purification.", {"t_sleep": "3", "t_purify": "1"}),
    ("H20", "Enable demand response with a temperature offset of 6 degrees and load capacity of 52 percent.", {"t_dr_onoff": "1", "t_dr_offset": "6", "t_dr_mode": "52"}),
    ("H21", "Disable demand response while preserving its offset and load capacity.", {"t_dr_onoff": "0"}),
    ("H22", "Disable automatic defrost cleaning and Super Mode.", {"t_auto_defrost_clean": "0", "t_super": "0"}),
    ("H23", "Change only the temperature unit to Fahrenheit; preserve the target value.", {"t_temp_type": "1"}),
    ("H24", "Leave all air-conditioner settings unchanged.", {}),
]


def item(case, profile, attention, kind="quality", repetition=0):
    return {key: case[key] for key in ("case_id", "order", "dataset")} | {
        "profile": profile, "attention": attention, "kind": kind, "repetition": repetition,
        "payload": request(case["payload"], profile, attention),
    }


def job(root, name, items):
    path = root / "jobs" / (name + ".json")
    if path.exists():
        raise FileExistsError("Frozen job already exists")
    save(path, {"prepared_at": stamp(), "requests": items})


def prepare(root):
    root.mkdir(parents=True, exist_ok=False)
    (root / "jobs").mkdir()
    (root / "sources").mkdir()
    capabilities = json.loads((HERE / "runs/2026-10-30-v1/command_set.json").read_text())
    refs = json.loads((HERE / "runs/2026-10-30-api-ablation-v1/references.json").read_text())
    refs += [{"id": key, "query": query, "dataset": "validation",
              "category": "single" if len(expected) <= 1 else "multi",
              "expected": [{"cmdKey": k, "cmdValue": v} for k, v in expected.items()]}
             for key, query, expected in VALIDATION]
    datasets = {}
    for split in ("development", "validation"):
        cases = []
        for ref in refs:
            if (ref["dataset"] == "validation") != (split == "validation"):
                continue
            for order in ("original", "reversed"):
                base = payload(ref["query"], capabilities, order == "reversed")
                for expected in ref["expected"]:
                    assert expected["cmdValue"] in base["questions"][expected["cmdKey"]]["criteria"]
                cases.append({"case_id": ref["id"], "dataset": ref["dataset"],
                              "order": order, "payload": base})
        datasets[split] = cases
        save(root / (split + "_cases.json"), cases)
    save(root / "references.json", refs)
    save(root / "command_set.json", capabilities)
    for name in SOURCES:
        (root / "sources" / name).write_bytes((HERE / name).read_bytes())
    save(root / "plan.json", {
        "prepared_at": stamp(), "model": "h2oai/h2o-lightning-4b",
        "development_sha256": sha(datasets["development"]),
        "validation_sha256": sha(datasets["validation"]),
        "references_sha256": sha(refs), "capabilities_sha256": sha(capabilities),
        "sources": {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in SOURCES},
        "profiles": ["baseline", "rules_only"], "modes": ["bidirectional", "causal"],
        "selection_policy": (
            "Select a causal prompt using only development original results before validation inference. "
            "Require zero transport errors, no loss of any originally correct development case versus "
            "same-process baseline bidirectional, and mean complete-request latency <= 80% of that control. "
            "Rank by exact correct count, fewer extra pairs, fewer missing pairs, then lower mean latency. "
            "If none qualifies, freeze the strongest causal prompt only as a diagnostic candidate, not adopted. "
            "GDN1024 can be recommended only with >=10% lower paired S03 full-request mean than the "
            "same candidate without GDN and no changed development choices or transport failures. "
            "Final adoption additionally requires no regression on any correct control case in both orders "
            "of the 30 development and 24 validation queries and mean validation latency <=80% of control. "
            "No tuning or replacement candidate after validation."
        ),
        "validation_policy": "24 new queries authored using known error categories and frozen before trials; same-domain held-back validation, not an external blind benchmark.",
        "runtime_policy": "Preserve other three resident services; only H2O restarts. Unique compile-cache directory per trial. Automatic rollback for runtime mutations. BF16 only if memory allows without evicting other models.",
        "timing_policy": "External requests strictly serial; rotate profile/mode order per case; separate warmups, full30, single-Key and serial30 totals. SHIM_CACHE_WRITE remains all for multi-question workloads.",
        "automatic_retries": 0, "external_concurrency": 1,
    })
    cases = [c for c in datasets["development"] if c["order"] == "original"]
    arms = [("baseline", "bidirectional"), ("baseline", "causal"),
            ("rules_only", "bidirectional"), ("rules_only", "causal")]
    warm = next(c for c in cases if c["case_id"] == "S03")
    items = [item(warm, *arm, kind="warmup") for arm in arms]
    for index, case in enumerate(cases):
        for arm in arms[index % 4:] + arms[:index % 4]:
            items.append(item(case, *arm))
    job(root, "development", items)
    print(json.dumps({"run": str(root), "development_calls": len(items), "validation_cases": 24}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    prepare(parser.parse_args().run)
