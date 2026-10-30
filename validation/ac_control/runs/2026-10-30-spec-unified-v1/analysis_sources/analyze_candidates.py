"""Audit frozen requests and score native choices offline, without answer repair."""

import argparse
import copy
import hashlib
import json
from datetime import datetime
from pathlib import Path

from analyze import grade, timing
from run_candidate_benchmark import selected, sha


def metrics(rows):
    return {"requests": len(rows), "correct": sum(row["correct"] for row in rows),
            "errors": sum(row["status"] != "ok" for row in rows),
            "extra_pairs": sum(len(row["extra"]) for row in rows),
            "missing_pairs": sum(len(row["missing"]) for row in rows),
            "client_ms": timing(row["client_ms"] for row in rows)}


def analyze(root, results_root=None, output_path=None):
    results_root = results_root or root / "results"
    output_path = output_path or root / "summary.json"
    plan = json.loads((root / "plan.json").read_text())
    data = {}
    for filename, field in (("cases", "cases"), ("references", "references"),
                            ("models", "models"), ("command_set", "capabilities")):
        data[filename] = json.loads((root / (filename + ".json")).read_text())
        assert sha(data[filename]) == plan[field + "_sha256"]
    transfer = json.loads((root / "source-transfer.json").read_text())
    for name, digest in transfer["files"].items():
        path = root / ("sources/" if name.endswith(".py") else "") / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    cases = {(r["case_id"], r["order"]): r for r in data["cases"]}
    refs = {r["id"]: r for r in data["references"]}
    for case in cases.values():
        assert json.loads(case["payload"]["state"])["commandSet"] == data["command_set"]["commandSet"]
    results, all_calls = {}, []
    for provider in plan["model_order"]:
        folder = results_root / provider
        if not (folder / "run.json").exists():
            results[provider] = {"status": "no_inference_receipts"}
            continue
        meta = json.loads((folder / "run.json").read_text())
        assert meta["runner_sha256"] == transfer["files"]["run_candidate_benchmark.py"]
        calls = [json.loads(line) for line in (folder / "receipts.jsonl").read_text().splitlines()]
        assert len(calls) == meta["calls"]
        scored = []
        for row in calls:
            case = cases[row["case_id"], row["order"]]
            expected = copy.deepcopy(case["payload"])
            expected["model"] = data["models"][provider]["repository"]
            if provider == "h2o":
                expected["attention_mode"] = "bidirectional"
            if row["kind"] in ("warmup_single", "single_key", "serial30"):
                assert len(row["transport_request"]["questions"]) == 1
                key = next(iter(row["transport_request"]["questions"]))
                assert row["kind"] != "single_key" or key == "t_temp"
                expected["questions"] = {key: expected["questions"][key]}
            assert row["transport_request"] == expected
            assert row["input_sha256"] == sha(expected)
            assert all(row[key] == case[key] for key in ("dataset", "language", "order"))
            if row["status"] == "ok":
                assert row["response"] == json.loads(row["response_text"])
                assert row["response"]["model"] == expected["model"]
                if provider == "h2o":
                    assert row["response"]["attention_mode"] == "bidirectional"
                assert not row["response"].get("effort_used", {}).get("state_selection")
                choices = selected(row["response"], expected)
                assert choices == row["choices"]
                assert row["commands"] == [{"cmdKey": key, "cmdValue": value}
                                            for key, value in choices.items() if value != "omit"]
            if row["kind"] == "quality":
                scored.append({key: row.get(key) for key in (
                    "case_id", "dataset", "language", "order", "status", "commands", "choices", "client_ms")}
                    | grade(refs[row["case_id"]]["expected"], row["commands"], row["status"]))
        quality_cases = [(r["case_id"], r["order"]) for r in calls if r["kind"] == "quality"]
        assert quality_cases == list(cases)[:len(quality_cases)], "Quality order changed"
        if meta["status"] == "complete":
            assert len(calls) == 285 and len(scored) == 156
            assert sum(r["kind"].startswith("warmup") for r in calls) == 33
            assert len(meta["serial30_blocks"]) == 3
        blocks = meta["serial30_blocks"]
        for block in blocks:
            rows = [r for r in calls if r["kind"] == "serial30" and r["repetition"] == block["repetition"]]
            assert len(rows) == 30
            assert [next(iter(r["transport_request"]["questions"])) for r in rows] == list(
                cases["S03", "original"]["payload"]["questions"])
            assert abs(sum(r["client_ms"] for r in rows) - block["http_sum_ms"]) < .01
            assert block["wall_ms"] >= block["http_sum_ms"]
            assert block["artifact_operations_inside_block"] == 0
        by_case = {(r["case_id"], r["order"]): r for r in scored}
        changes = [id for id, order in by_case if order == "original" and (id, "reversed") in by_case
                   and by_case[id, order]["choices"] != by_case[id, "reversed"]["choices"]]
        layout_comparison = []
        for repetition in range(3):
            full = [r for r in calls if r["kind"] == "full30" and r["repetition"] == repetition]
            serial = [r for r in calls if r["kind"] == "serial30" and r["repetition"] == repetition]
            if len(full) == 1 and len(serial) == 30 and all(r["status"] == "ok" for r in full + serial):
                combined = {key: value for row in serial for key, value in row["choices"].items()}
                commands = [{"cmdKey": key, "cmdValue": value} for key, value in combined.items() if value != "omit"]
                layout_comparison.append({
                    "repetition": repetition,
                    "changed_fields": [key for key, value in combined.items() if full[0]["choices"][key] != value],
                    "serial_commands": commands, "full_commands": full[0]["commands"],
                    "serial_correct": grade(refs["S03"]["expected"], commands)["correct"],
                    "full_correct": grade(refs["S03"]["expected"], full[0]["commands"])["correct"],
                })
        results[provider] = {
            "status": meta["status"], "calls": len(calls),
            "formal_calls": sum(not r["kind"].startswith("warmup") for r in calls),
            "warmup_calls": sum(r["kind"].startswith("warmup") for r in calls),
            "errors": sum(r["status"] != "ok" for r in calls),
            "scores": {"all": metrics(scored)} | {
                language: metrics([r for r in scored if r["language"] == language])
                for language in ("en", "zh")
            } | {dataset + ":" + order: metrics([r for r in scored if r["dataset"] == dataset and r["order"] == order])
                 for dataset in sorted({r["dataset"] for r in scored}) for order in ("original", "reversed")},
            "latency": {
                "single_key_ms": timing(r["client_ms"] for r in calls if r["kind"] == "single_key"),
                "serial30_step_ms": timing(r["client_ms"] for r in calls if r["kind"] == "serial30"),
                "serial30_total_ms": timing(b["wall_ms"] for b in blocks),
                "serial30_http_sum_ms": timing(b["http_sum_ms"] for b in blocks),
                "full30_ms": timing(r["client_ms"] for r in calls if r["kind"] == "full30"),
            },
            "option_order_changed_cases": changes, "s03_layout_comparison": layout_comparison, "rows": scored,
            "receipts_sha256": hashlib.sha256((folder / "receipts.jsonl").read_bytes()).hexdigest(),
        }
        all_calls.extend(calls)
    all_calls.sort(key=lambda row: row["started_at"])
    for previous, current in zip(all_calls[:-1], all_calls[1:], strict=True):
        assert datetime.fromisoformat(previous["finished_at"]) <= datetime.fromisoformat(current["started_at"])
    result = {"models": results, "request_overlap_count": 0, "reference_answers_sent": False,
              "input_audit_passed": True, "total_observed_calls": len(all_calls)}
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    args = parser.parse_args()
    result = analyze(args.run)
    print(json.dumps({name: {key: value for key, value in model.items() if key != "rows"}
                      for name, model in result["models"].items()}, indent=2))
