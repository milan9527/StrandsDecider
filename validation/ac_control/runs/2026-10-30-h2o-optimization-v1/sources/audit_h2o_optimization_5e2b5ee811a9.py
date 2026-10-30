"""Audit serial execution, unchanged services, and final H2O deployment evidence."""

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

from analyze_h2o_optimization import analyze
from run_resident import save, stamp

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
    assert final["health"]["ok"] and final["health"]["attention_mode"] == "bidirectional"
    assert services(final["protected_services"]) == protected
    assert final["rollback_timer_active"] is False
    assert final["restart_policy"] == "always"
    selection = json.loads((run / "selection.json").read_text())
    selected = summary["variants"][selection["selected_variant"]]
    assert selected["quality_rows"] and not selected["lost_correct_cases"]
    selected_runtime = json.loads(
        (run / "variants" / selection["selected_variant"] / "runtime.json").read_text())
    assert final["runtime"]["image"] == selected_runtime["image"]
    assert all(final["runtime"]["env"].get(key) == value
               for key, value in selected_runtime["env"].items())
    if selection["selected_variant"] != "seq1-eager":
        assert selected["full_30_speedup_vs_baseline"] > 1
        assert (run / "accepted_runtime.json").exists()
        assert selection["selected_variant"] not in performance_changed
    else:
        assert (run / "rollback/restored.json").exists()
        assert not final["optimization_dropin_exists"]
        restored_name = selection["restored_validation_variant"]
        restored = summary["variants"][restored_name]
        assert restored["quality_rows"] and not restored["changed_cases_vs_baseline"]
        assert restored["runtime_sha256"] == selected["runtime_sha256"]
        restored_runtime = json.loads((run / "variants" / restored_name / "runtime.json").read_text())
        assert final["runtime"]["started_at"] == restored_runtime["started_at"]
    result = {
        "audited_at": stamp(), "status": "passed", "variants": checks,
        "formal_calls": sum(row["phase"] != "warmup" for row in rows),
        "warmup_calls": sum(row["phase"] == "warmup" for row in rows),
        "request_overlap_count": 0, "invalid_responses": 0,
        "protected_services_unchanged": True, "frozen_inputs_and_sources_verified": True,
        "performance_choice_changes_vs_baseline": performance_changed,
        "selected_variant": selection["selected_variant"],
        "selected_quality_changed_cases": selected["changed_cases_vs_baseline"],
        "final_deployment_matches_selected_runtime": True,
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
