"""Audit serial execution, unchanged services, and final H2O deployment evidence."""

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

from analyze_h2o_optimization import analyze
from run_ablation import choices
from run_resident import save, sha, stamp

PROTECTED = {"decider-vllm.service", "decider-liquid.service",
             "decider-comparison-gateway.service"}


def services(text):
    records = [dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
               for block in text.strip().split("\n\n")]
    return {row["Id"]: row for row in records if row.get("Id") in PROTECTED}


def audit(run):
    summary = analyze(run)
    original = json.loads((run / "rollback/original.json").read_text())
    protected = services(original["protected_services"])
    assert set(protected) == PROTECTED
    rows = []
    checks = []
    for directory in sorted((run / "variants").iterdir()):
        metadata = json.loads((directory / "run.json").read_text())
        assert metadata["status"] == "complete", f"Incomplete observations: {directory.name}"
        for phase in ("before", "after"):
            snapshot = json.loads((directory / f"{phase}_environment.json").read_text())
            assert services(snapshot["services"]["stdout"]) == protected
        captured = [json.loads(line) for line in (directory / "receipts.jsonl").read_text().splitlines()]
        rows.extend(captured)
        checks.append(directory.name)
        quality_name = summary["variants"][directory.name].get("quality_evidence_variant")
        if quality_name and quality_name != directory.name:
            runtime = json.loads((directory / "runtime.json").read_text())
            quality_runtime = json.loads((run / "variants" / quality_name / "runtime.json").read_text())
            assert runtime["started_at"] == quality_runtime["started_at"]
    rows.sort(key=lambda row: row["started_at"])
    for previous, current in zip(rows[:-1], rows[1:], strict=True):
        assert datetime.fromisoformat(previous["finished_at"]) <= datetime.fromisoformat(current["started_at"])
    baseline = [row for row in rows if row["variant"] == "seq1-eager"
                and row["phase"] == "performance" and row["mode"] == "full_30"][0]["choices"]
    performance_changed = sorted({row["variant"] for row in rows
                                  if row["phase"] == "performance"
                                  and any(value != baseline[key] for key, value in row["choices"].items())})
    final = json.loads((run / "final_runtime.json").read_text())
    initial = json.loads((run / "initial_inventory.json").read_text())
    for name, digest in final["model_source_sha256"].items():
        assert digest == initial[name]["sha256"]
    assert final["health"]["ok"] and final["health"]["attention_mode"] == "bidirectional"
    assert services(final["protected_services"]) == protected
    assert final["rollback_timer_active"] is False
    assert final["restart_policy"] == "always"
    selection = json.loads((run / "selection.json").read_text())
    selected = summary["variants"][selection["selected_variant"]]
    assert selected["quality_rows"]
    selected_runtime = json.loads(
        (run / "variants" / selection["selected_variant"] / "runtime.json").read_text())
    assert final["runtime"]["image"] == selected_runtime["image"]
    assert all(final["runtime"]["env"].get(key) == value
               for key, value in selected_runtime["env"].items())
    if selection["action"] != "rollback":
        assert not selected["lost_correct_cases"]
        assert selected["full_30_speedup_vs_baseline"] > 1
        assert (run / "accepted_runtime.json").exists()
        assert selection["selected_variant"] not in performance_changed
    else:
        assert (run / "rollback/restored.json").exists()
        assert not final["optimization_dropin_exists"]
        assert final["effective_h2o_unit"] == original["effective_unit"]
        restored_name = selection["restored_validation_variant"]
        restored = summary["variants"][restored_name]
        assert restored["quality_rows"]
        # Record observed quality differences; a successful configuration rollback
        # must not be mislabeled as historical answer reproducibility.
        assert restored["changed_cases_vs_baseline"] == selection["observed_restoration_changes"]
        assert restored["runtime_sha256"] == summary["variants"][selection["baseline_variant"]]["runtime_sha256"]
        restored_runtime = json.loads((run / "variants" / restored_name / "runtime.json").read_text())
        assert final["runtime"]["started_at"] == restored_runtime["started_at"]
    repeatability = run / "repeatability"
    repeat_rows = [json.loads(line) for line in (repeatability / "receipts.jsonl").read_text().splitlines()]
    repeat_plan = json.loads((repeatability / "plan.json").read_text())
    repeat_meta = json.loads((repeatability / "run.json").read_text())
    assert repeat_meta["status"] == "complete" and repeat_meta["actual_calls"] == len(repeat_rows)
    assert [{key: row[key] for key in ("case_id", "mode", "repetition")}
            for row in repeat_rows] == repeat_plan["schedule"]
    cases = {row["case_id"]: row["payload"] for row in json.loads((run / "cases.json").read_text())
             if row["order"] == "original"}
    for row in repeat_rows:
        payload = cases[row["case_id"]]
        if row["mode"] == "single_key":
            payload = {"state": payload["state"],
                       "questions": {"t_swing_angle": payload["questions"]["t_swing_angle"]}}
        assert row["request"] == payload
        assert row["status"] == "ok" and row["http_status"] == 200
        assert row["response"] == json.loads(row["response_text"])
        assert row["response"]["attention_mode"] == "bidirectional"
        assert sha(payload) == row["input_sha256"]
        assert choices(row["response"], payload, "h2oai/h2o-lightning-4b") == row["choices"]
    for phase in ("before", "after"):
        snapshot = json.loads((repeatability / f"{phase}_environment.json").read_text())
        assert services(snapshot["services"]["stdout"]) == protected
        restored_snapshot = json.loads(
            (run / "variants" / selection["restored_validation_variant"] / "after_environment.json").read_text())
        assert snapshot["services"]["stdout"] == restored_snapshot["services"]["stdout"]
    n09_answers = [row["response"]["answers"]["t_swing_angle"] for row in repeat_rows if row["case_id"] == "N09"]
    assert len(n09_answers) == 6 and all(answer == n09_answers[0] for answer in n09_answers)
    combined = sorted(rows + repeat_rows, key=lambda row: row["started_at"])
    for previous, current in zip(combined[:-1], combined[1:], strict=True):
        assert datetime.fromisoformat(previous["finished_at"]) <= datetime.fromisoformat(current["started_at"])
    result = {
        "audited_at": stamp(), "status": "passed", "variants": checks,
        "formal_calls": sum(row["phase"] != "warmup" for row in rows) + len(repeat_rows),
        "main_formal_calls": sum(row["phase"] != "warmup" for row in rows),
        "supplemental_repeatability_calls": len(repeat_rows),
        "warmup_calls": sum(row["phase"] == "warmup" for row in rows),
        "request_overlap_count": 0, "invalid_responses": 0,
        "protected_services_unchanged": True, "frozen_inputs_and_sources_verified": True,
        "performance_choice_changes_vs_baseline": performance_changed,
        "selected_variant": selection["selected_variant"],
        "selected_quality_changed_cases": selected["changed_cases_vs_baseline"],
        "historical_choices_reproduced_after_rollback": not selected["changed_cases_vs_baseline"],
        "quality_status": selection["quality_status"],
        "final_deployment_matches_selected_runtime": True,
        "model_source_files_unchanged": True,
        "n09_six_repeat_answers_identical": True,
        "automatic_rollback_timer_disarmed": True,
        "restored_validation_variant": selection.get("restored_validation_variant"),
        "auditor_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    save(run / "audit.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    audit(parser.parse_args().run)
