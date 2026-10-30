"""Freeze graph/final recommendations and audit serial H2O optimization evidence."""

import argparse
import hashlib
import io
import json
import tarfile
from datetime import datetime
from pathlib import Path

from analyze_h2o_official import analyze
from run_resident import save, stamp


def immutable(path, value):
    if path.exists():
        assert json.loads(path.read_text()) == value
    else:
        save(path, value)


def select_runtime(root, summary):
    assert not (root / "runtime_selection.json").exists()
    assert "validation" not in summary["stages"]
    selection = json.loads((root / "selection.json").read_text())
    arm = selection["profile"] + ":" + selection["attention"]
    before = summary["stages"]["eager_latency"]
    after = summary["stages"].get("gdn_screen")
    quality = summary["stages"].get("gdn_quality")
    accepted = False
    evidence = {"eager_full30_ms": before["latency"][arm + ":full30"]["client_ms"]["mean"]}
    if after and after["status"] == "complete":
        evidence["gdn_full30_ms"] = after["latency"][arm + ":full30"]["client_ms"]["mean"]
        evidence["speedup"] = evidence["eager_full30_ms"] / evidence["gdn_full30_ms"]
        if quality and quality["status"] == "complete":
            old = {(r["case_id"], r["order"]): r["choices"]
                   for r in summary["stages"]["restart_check"]["rows"]
                   if r["profile"] == selection["profile"] and r["attention"] == selection["attention"]}
            evidence["changed_cases"] = [
                r["case_id"] for r in quality["rows"]
                if r["choices"] != old[r["case_id"], r["order"]]
            ]
            accepted = (evidence["gdn_full30_ms"] <= evidence["eager_full30_ms"] * .9
                        and not evidence["changed_cases"] and quality["errors"] == 0)
    result = {"selected_at": stamp(), "runtime": "gdn1024" if accepted else "original_eager",
              "gdn_accepted_for_validation": accepted, "evidence": evidence,
              "validation_outputs_seen": False}
    save(root / "runtime_selection.json", result)
    return result


def service_blocks(value):
    blocks = {}
    for block in value.strip().split("\n\n"):
        fields = dict(line.split("=", 1) for line in block.splitlines())
        blocks[fields["Id"]] = fields
    return blocks


def finish(root, summary):
    selection = json.loads((root / "selection.json").read_text())
    runtime_selection = json.loads((root / "runtime_selection.json").read_text())
    validation = summary["stages"]["validation"]
    assert validation["status"] == "complete" and validation["calls"] == 218
    metadata = json.loads((root / "stages/validation/run.json").read_text())
    assert datetime.fromisoformat(selection["selected_at"]) < datetime.fromisoformat(metadata["started_at"])
    assert datetime.fromisoformat(runtime_selection["selected_at"]) < datetime.fromisoformat(metadata["started_at"])
    assert selection["development_receipts_sha256"] == summary["stages"]["development"]["receipts_sha256"]
    rows = validation["rows"]
    control = {(r["case_id"], r["order"]): r for r in rows
               if r["profile"] == "baseline" and r["attention"] == "bidirectional"}
    candidate = [r for r in rows if r["profile"] == selection["profile"] and r["attention"] == "causal"]
    assert len(control) == len(candidate) == 108
    regressions = [{"case_id": r["case_id"], "order": r["order"], "dataset": r["dataset"],
                    "control": control[r["case_id"], r["order"]]["commands"], "candidate": r["commands"]}
                   for r in candidate if control[r["case_id"], r["order"]]["correct"] and not r["correct"]]
    original_control = {r["case_id"]: r for r in summary["stages"]["development"]["rows"]
                        if r["profile"] == "baseline" and r["attention"] == "bidirectional"}
    initial_regressions = [r["case_id"] for r in candidate
                           if r["order"] == "original" and r["case_id"] in original_control
                           and original_control[r["case_id"]]["correct"] and not r["correct"]]
    new_control = [r for r in control.values() if r["dataset"] == "validation"]
    new_candidate = [r for r in candidate if r["dataset"] == "validation"]
    speedup = (sum(r["client_ms"] for r in new_control)
               / sum(r["client_ms"] for r in new_candidate))
    accepted = (selection["development_eligible"] and not regressions and not initial_regressions
                and speedup >= 1.25 and validation["errors"] == 0)
    recommendation = {
        "accepted": accepted, "profile": selection["profile"] if accepted else "baseline",
        "attention": "causal" if accepted else "bidirectional",
        "runtime": runtime_selection["runtime"] if accepted else "original_eager",
        "scope": "AC client using full30 original-key choices; no answer repair or generic default-mode switch.",
        "regressions": regressions, "validation_speedup": speedup,
        "regressions_vs_initial_original_control": initial_regressions,
        "candidate_profile": selection["profile"],
        "development_eligible": selection["development_eligible"],
        "validation_receipts_sha256": validation["receipts_sha256"],
    }
    immutable(root / "recommendation.json", recommendation)
    # Other services must remain unchanged across all H2O restarts.
    initial = service_blocks(json.loads((root / "initial_inventory.json").read_text())["services"]["stdout"])
    for path in (root / "stages").glob("*/*_environment.json"):
        current = service_blocks(json.loads(path.read_text())["services"]["stdout"])
        for name in ("decider-vllm.service", "decider-liquid.service", "decider-comparison-gateway.service"):
            assert current[name] == initial[name], f"Protected service changed: {name}"
    transfer = json.loads((root / "transfer.json").read_text())
    archives = {}
    for command in transfer["commands"]:
        path = root / "transfer_inputs" / (command["name"] + ".tar.gz")
        assert hashlib.sha256(path.read_bytes()).hexdigest() == command["archive_sha256"]
        with tarfile.open(fileobj=io.BytesIO(path.read_bytes()), mode="r:gz") as archive:
            assert archive.getnames() == list(command["files"])
            assert all("references" not in name for name in archive.getnames())
            for member in archive.getmembers():
                assert member.isfile()
                assert hashlib.sha256(archive.extractfile(member).read()).hexdigest() == command["files"][member.name]
        archives[command["name"]] = command["archive_sha256"]
    originals = {(r["case_id"], r["order"]): r for r in summary["stages"]["development"]["rows"]
                 if r["profile"] == "baseline" and r["attention"] == "bidirectional"}
    restart = summary["stages"].get("restart_check", {})
    restart_changed = [
        r["case_id"] for r in restart.get("rows", [])
        if r["profile"] == "baseline" and r["attention"] == "bidirectional"
        if r["choices"] != originals[r["case_id"], r["order"]]["choices"]
    ]
    result = {
        "audited_at": stamp(), "passed": True,
        "formal_calls": summary["formal_calls"], "warmup_calls": summary["warmup_calls"],
        "request_overlap_count": summary["request_overlap_count"],
        "model_side_input_truncation_count": summary["model_side_input_truncation_count"],
        "errors": sum(stage["errors"] for stage in summary["stages"].values()),
        "protected_services_unchanged": True, "reference_file_absent_from_archives": True,
        "restart_changed_original_cases": restart_changed,
        "final_control_changed_original_cases": [
            key[0] for key, r in originals.items() if r["choices"] != control[key]["choices"]],
        "recommendation": recommendation, "transfer_archives": archives,
        "analysis_sources": {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                             for name in ("analyze_h2o_official.py", "finish_h2o_official.py",
                                          "prepare_h2o_official.py", "plan_h2o_official_jobs.py",
                                          "remote_h2o_official.py", "test_h2o_official.py")},
    }
    for name in result["analysis_sources"]:
        path = root / "analysis_sources" / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(Path(__file__).with_name(name).read_bytes())
    save(root / "audit.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--select-runtime", action="store_true")
    args = parser.parse_args()
    summary = analyze(args.run)
    result = select_runtime(args.run, summary) if args.select_runtime else finish(args.run, summary)
    print(json.dumps(result, indent=2))
