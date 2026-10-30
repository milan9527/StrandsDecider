"""Offline audit, development-only selection, and held-back validation scoring."""

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

from analyze import grade, timing
from liquid_ac_protocol import decode_commands, prepare_strategy, second_stage
from run_ablation import choices
from run_resident import save, sha, stamp

MODEL = "LiquidAI/d1-2B"


def aggregate(rows):
    return {
        "correct": sum(row["correct"] for row in rows), "count": len(rows),
        "extra_pairs": sum(len(row["extra"]) for row in rows),
        "missing_pairs": sum(len(row["missing"]) for row in rows),
        "correct_keys": sum(row["correct_keys"] for row in rows),
        "expected_keys": sum(row["expected_count"] for row in rows),
        "errors": sum(row["status"] != "ok" for row in rows),
        "client_ms": timing(row["client_ms"] for row in rows),
        "gate_ms": timing(row["gate_ms"] for row in rows),
        "value_ms": timing(row["value_ms"] for row in rows),
    }


def audit_row(row, base):
    prepared = prepare_strategy(base, row["strategy"])
    expected_payload = prepared["first"]
    decoded = {}
    for index, stage in enumerate(row["stages"]):
        assert expected_payload is not None and stage["payload"] == expected_payload
        assert stage["input_sha256"] == sha(expected_payload)
        phase = "gate" if index == 0 and prepared["values"] is not None else "value"
        assert stage["phase"] == phase
        if stage["status"] != "ok":
            assert row["status"] != "ok"
            break
        assert stage["response"] == json.loads(stage["response_text"])
        selected = choices(stage["response"], expected_payload, MODEL)
        assert selected == stage["choices"]
        if phase == "gate":
            assert row["gate_choices"] == selected
            expected_payload = second_stage(prepared, selected)
        else:
            decoded = selected
            expected_payload = None
    if row["status"] == "ok":
        assert expected_payload is None
        assert row["model_selections"] == decoded
        assert row["action_mapping"] == prepared["mapping"]
        assert row["commands"] == decode_commands(base, prepared, decoded)
    return row["commands"]


def analyze(root):
    plan = json.loads((root / "plan.json").read_text())
    references = json.loads((root / "references.json").read_text())
    assert sha(references) == plan["references_sha256"]
    refs = {ref["id"]: ref for ref in references}
    for name, digest in plan["source_sha256"].items():
        assert hashlib.sha256((root / "sources" / name).read_bytes()).hexdigest() == digest
        assert hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() == digest
    phases = {}
    all_calls = []
    service_state = None
    runtime_state = None
    for phase in ("development", "validation"):
        directory = root / phase
        if not (directory / "receipts.jsonl").exists():
            continue
        metadata = json.loads((directory / "run.json").read_text())
        cases = json.loads((root / (phase + "_cases.json")).read_text())
        assert sha(cases) == plan[phase + "_sha256"]
        lookup = {(case["case_id"], case["order"]): case for case in cases}
        receipts = [json.loads(line) for line in (directory / "receipts.jsonl").read_text().splitlines()]
        expected_schedule = []
        strategies = metadata["strategies"]
        for index, case in enumerate(cases):
            rotated = strategies[index % len(strategies):] + strategies[:index % len(strategies)]
            expected_schedule.extend((case["case_id"], case["order"], strategy) for strategy in rotated)
        actual_schedule = [(row["case_id"], row["order"], row["strategy"]) for row in receipts]
        assert actual_schedule == expected_schedule[:len(receipts)]
        if metadata["status"] == "complete":
            assert actual_schedule == expected_schedule
            assert metadata["observations"] == len(receipts)
            assert metadata["actual_calls"] == sum(len(row["stages"]) for row in receipts)
        rows = []
        for row in receipts:
            case = lookup[row["case_id"], row["order"]]
            assert row["input_sha256"] == sha(case["payload"])
            commands = audit_row(row, case["payload"])
            stage_time = {
                phase + "_ms": next((stage["client_ms"] for stage in row["stages"] if stage["phase"] == phase), None)
                for phase in ("gate", "value")
            }
            rows.append({key: row[key] for key in ("case_id", "dataset", "order", "strategy", "status", "client_ms")}
                        | {"commands": commands, **stage_time,
                           **grade(refs[row["case_id"]]["expected"], commands, row["status"])})
            all_calls.extend(row["stages"])
        warmup = [json.loads(line) for line in (directory / "warmup.jsonl").read_text().splitlines()]
        for row in warmup:
            audit_row(row, next(case for case in cases if case["order"] == "original")["payload"])
            all_calls.extend(row["stages"])
        before = json.loads((directory / "before_environment.json").read_text())["services"]["stdout"]
        runtime = json.loads((directory / "runtime.json").read_text())
        if service_state is None:
            service_state, runtime_state = before, runtime
        assert before == service_state and runtime == runtime_state
        if metadata["status"] == "complete":
            assert json.loads((directory / "after_environment.json").read_text())["services"]["stdout"] == service_state
        scores = {}
        for strategy in strategies:
            selected = [row for row in rows if row["strategy"] == strategy]
            groups = {
                dataset + "_" + order: aggregate([row for row in selected
                                                  if row["dataset"] == dataset and row["order"] == order])
                for dataset in sorted({row["dataset"] for row in selected})
                for order in ("original", "reversed")
            }
            by_case = {(row["case_id"], row["order"]): row for row in selected}
            groups["order_changed_cases"] = [
                case for case, order in by_case if order == "original"
                and (case, "reversed") in by_case
                and by_case[case, "original"]["commands"] != by_case[case, "reversed"]["commands"]
            ]
            groups["original_total"] = aggregate([row for row in selected if row["order"] == "original"])
            groups["reversed_total"] = aggregate([row for row in selected if row["order"] == "reversed"])
            scores[strategy] = groups
        phases[phase] = {
            "status": metadata["status"], "observations": len(rows),
            "actual_calls": sum(len(row["stages"]) for row in receipts),
            "warmup_calls": sum(len(row["stages"]) for row in warmup),
            "scores": scores, "rows": rows,
            "receipts_sha256": hashlib.sha256((directory / "receipts.jsonl").read_bytes()).hexdigest(),
        }
    all_calls.sort(key=lambda call: call["started_at"])
    for previous, current in zip(all_calls[:-1], all_calls[1:], strict=True):
        assert datetime.fromisoformat(previous["finished_at"]) <= datetime.fromisoformat(current["started_at"])
    result = {"analyzed_at": stamp(), "phases": phases, "request_overlap_count": 0,
              "services_unchanged": True, "analyzer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    save(root / "accuracy_summary.json", result)
    print(json.dumps({phase: {key: value for key, value in data.items() if key not in ("rows", "receipts_sha256")}
                      for phase, data in phases.items()}, ensure_ascii=False, indent=2))
    return result


def select(root, result):
    assert not (root / "selection.json").exists(), "Selection is immutable"
    assert "validation" not in result["phases"], "Cannot select after seeing validation"
    development = result["phases"]["development"]
    assert development["status"] == "complete"
    scores = development["scores"]
    control = scores["two_stage"]
    eligible = []
    for strategy, score in scores.items():
        if strategy in ("baseline", "two_stage"):
            continue
        if (score["original_total"]["correct"] > control["original_total"]["correct"]
                and all(score[group]["correct"] >= control[group]["correct"]
                        for group in ("spec_original", "extension_original", "reversed_total"))):
            eligible.append(strategy)
    def rank(strategy):
        score = scores[strategy]
        original = score["original_total"]
        return (original["correct"], score["reversed_total"]["correct"],
                -original["missing_pairs"], -original["extra_pairs"], -original["client_ms"]["mean"])
    candidate = max(eligible, key=rank) if eligible else "two_stage"
    save(root / "selection.json", {
        "selected_at": stamp(), "candidate": candidate, "eligible": eligible,
        "development_receipts_sha256": development["receipts_sha256"],
        "validation_outputs_seen": False,
        "reason": "Apply the frozen development selection rule; two_stage retained if no new strategy qualifies.",
    })
    print("Selected before validation:", candidate)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--select", action="store_true")
    args = parser.parse_args()
    result = analyze(args.run)
    if args.select:
        select(args.run, result)
