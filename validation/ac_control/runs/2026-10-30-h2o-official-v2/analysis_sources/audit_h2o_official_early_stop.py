"""Audit the predeclared early stop without claiming heldback validation occurred."""

import hashlib
import json
import tarfile
from datetime import datetime
from pathlib import Path

import boto3
from analyze import grade
from analyze_h2o_official import analyze
from finish_h2o_official import service_blocks
from run_resident import save, stamp


def audit(root):
    summary = analyze(root)
    selection = json.loads((root / "selection.json").read_text())
    amendment = json.loads((root / "early_stop_amendment.json").read_text())
    screen = json.loads((root / "baseline_runtime_screen.json").read_text())
    assert not selection["development_eligible"] and not screen["screen_passed"]
    assert not screen["heldback_queried"]
    assert summary["formal_calls"] == 234 and summary["warmup_calls"] == 8
    assert all(s["status"] == "complete" and s["errors"] == 0 for s in summary["stages"].values())
    assert selection["development_receipts_sha256"] == summary["stages"]["development"]["receipts_sha256"]
    assert hashlib.sha256((root / "selection.json").read_bytes()).hexdigest() == amendment["selection_sha256"]
    assert hashlib.sha256((root / "plan.json").read_bytes()).hexdigest() == amendment["original_plan_sha256"]
    for name in ("restart_stability", "eager_baseline", "gdn_baseline_screen", "final_stability"):
        meta = json.loads((root / "stages" / name / "run.json").read_text())
        assert datetime.fromisoformat(amendment["prepared_at"]) < datetime.fromisoformat(meta["started_at"])
    inventory = json.loads((root / "final_inventory.json").read_text())
    assert all(inventory[key] for key in ("exact_original_unit_restored", "dropin_absent",
                                          "protected_services_unchanged"))
    initial = service_blocks(json.loads((root / "initial_inventory.json").read_text())["services"]["stdout"])
    for path in (root / "stages").glob("*/*_environment.json"):
        current = service_blocks(json.loads(path.read_text())["services"]["stdout"])
        for name in ("decider-vllm.service", "decider-liquid.service", "decider-comparison-gateway.service"):
            assert current[name] == initial[name]
    refs = {r["id"]: r for r in json.loads((root / "references.json").read_text())}
    original = {r["case_id"]: r for r in summary["stages"]["development"]["rows"]
                if r["profile"] == "baseline" and r["attention"] == "bidirectional"}
    stability = {}
    for stage in ("restart_stability", "final_stability"):
        calls = [json.loads(line) for line in (root / "stages" / stage / "receipts.jsonl").read_text().splitlines()]
        stability[stage] = {}
        for id in ("N03", "N09", "N10"):
            rows = [r for r in calls if r["kind"] == "repeatability" and r["case_id"] == id]
            assert len(rows) == 3
            stability[stage][id] = {
                "correct": sum(grade(refs[id]["expected"], r["commands"], r["status"])["correct"] for r in rows),
                "choice_variants": len({json.dumps(r["choices"], sort_keys=True) for r in rows}),
                "changed_vs_development": sum(r["choices"] != original[id]["choices"] for r in rows),
                "commands": [r["commands"] for r in rows],
            }
    transfer = json.loads((root / "transfer.json").read_text())
    statuses = {}
    ssm = boto3.client("ssm", region_name="us-east-1")
    for operation in transfer["commands"]:
        path = root / "transfer_inputs" / (operation["name"] + ".tar.gz")
        assert hashlib.sha256(path.read_bytes()).hexdigest() == operation["archive_sha256"]
        with tarfile.open(path) as archive:
            assert archive.getnames() == list(operation["files"])
            assert all("references" not in name for name in archive.getnames())
            for member in archive.getmembers():
                assert member.isfile()
                content = archive.extractfile(member).read()
                assert hashlib.sha256(content).hexdigest() == operation["files"][member.name]
                if member.name.startswith("jobs/"):
                    job = json.loads(content)
                    assert not any(r["case_id"].startswith("H") for r in job["requests"])
        invocation = ssm.get_command_invocation(CommandId=operation["id"], InstanceId=transfer["instance"])
        assert invocation["Status"] == "Success"
        statuses[operation["name"]] = invocation["Status"]
    serial = [json.loads(line) for line in (root / "stages/eager_baseline/receipts.jsonl").read_text().splitlines()]
    serial_sums = [sum(r["client_ms"] for r in serial if r["kind"] == "serial30" and r["repetition"] == rep)
                   for rep in range(3)]
    result = {
        "audited_at": stamp(), "passed": True, "accepted": False,
        "reason": "Causal profiles regressed known cases; GDN1024 speedup below 10% threshold.",
        "formal_calls": 234, "warmup_calls": 8, "errors": 0, "request_overlap_count": 0,
        "heldback_queried": False, "reference_answers_sent": False,
        "exact_original_unit_restored": True, "protected_services_unchanged": True,
        "early_stop_amendment": amendment, "screen": screen, "repeatability": stability,
        "ssm_statuses": statuses, "serial30_http_sum_ms": serial_sums,
        "serial30_wall_caveat": "Frozen runner publishes artifacts every 8 calls, including inside serial30. "
                               "Harness wall time includes uploads. Use summed HTTP times only, with this caveat; "
                               "the isolated candidate runner moves all artifact work outside serial30.",
    }
    save(root / "audit.json", result)
    for name in ("audit_h2o_official_early_stop.py", "analyze_h2o_official.py"):
        path = root / "analysis_sources" / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(Path(__file__).with_name(name).read_bytes())
    return result


if __name__ == "__main__":
    print(json.dumps(audit(Path(__file__).parent / "runs/2026-10-30-h2o-official-v2"), indent=2))
