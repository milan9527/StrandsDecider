"""Offline audit and development-only candidate selection for H2O official trials."""

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

from analyze import grade, timing
from h2o_ac_client import MODEL, request
from run_ablation import choices
from run_resident import save, sha, stamp


def aggregate(rows):
    return {
        "count": len(rows), "correct": sum(row["correct"] for row in rows),
        "errors": sum(row["status"] != "ok" for row in rows),
        "extra_pairs": sum(len(row["extra"]) for row in rows),
        "missing_pairs": sum(len(row["missing"]) for row in rows),
        "client_ms": timing(row["client_ms"] for row in rows),
        "server_ms": timing(row["server_ms"] for row in rows),
        "processed_input_tokens": timing(row["processed_input_tokens"] for row in rows),
    }


def analyze(root):
    plan = json.loads((root / "plan.json").read_text())
    refs = json.loads((root / "references.json").read_text())
    assert sha(refs) == plan["references_sha256"]
    refs = {ref["id"]: ref for ref in refs}
    capabilities = json.loads((root / "command_set.json").read_text())
    assert sha(capabilities) == plan["capabilities_sha256"]
    cases = {}
    for split in ("development", "validation"):
        data = json.loads((root / (split + "_cases.json")).read_text())
        assert sha(data) == plan[split + "_sha256"]
        for case in data:
            assert json.loads(case["payload"]["state"])["commandSet"] == capabilities["commandSet"]
            cases[case["case_id"], case["order"]] = case
    for name, digest in plan["sources"].items():
        assert hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() == digest
        assert hashlib.sha256((root / "sources" / name).read_bytes()).hexdigest() == digest
    stages = {}
    all_calls = []
    for directory in sorted((root / "stages").glob("*")):
        if not (directory / "run.json").exists():
            continue
        meta = json.loads((directory / "run.json").read_text())
        path = root / "jobs" / (directory.name + ".json")
        assert hashlib.sha256(path.read_bytes()).hexdigest() == meta["job_sha256"]
        job = json.loads(path.read_text())
        calls = [json.loads(line) for line in (directory / "receipts.jsonl").read_text().splitlines()]
        assert len(calls) <= len(job["requests"])
        if meta["status"] == "complete":
            assert len(calls) == len(job["requests"]) == meta["actual_calls"]
        scored = []
        for index, row in enumerate(calls):
            item = job["requests"][index]
            task = item["payload"]
            assert row["transport_request"] == task and row["input_sha256"] == sha(task)
            for key, value in item.items():
                if key != "payload":
                    assert row[key] == value
            case = cases[row["case_id"], row["order"]]
            expected_task = request(case["payload"], row["profile"], row["attention"])
            if row["kind"] in ("single_key", "serial30"):
                assert len(task["questions"]) == 1
                expected_task["questions"] = {key: expected_task["questions"][key] for key in task["questions"]}
            assert task == expected_task, "Prompt differs from frozen profile/input"
            if row["status"] == "ok":
                assert row["response"] == json.loads(row["response_text"])
                assert row["response"]["attention_mode"] == row["attention"]
                assert not row["response"].get("effort_used", {}).get("state_selection"), "Model-side input truncation"
                selected = choices(row["response"], task, MODEL)
                assert selected == row["choices"]
                commands = [{"cmdKey": key, "cmdValue": value}
                            for key, value in selected.items() if value != "omit"]
                assert row["commands"] == commands
            if row["kind"] == "quality":
                usage = row.get("response", {}).get("usage", {})
                scored.append({
                    key: row.get(key) for key in ("case_id", "dataset", "order", "profile", "attention",
                                             "status", "client_ms", "commands", "choices")
                } | {"server_ms": usage.get("latency_ms"),
                     "processed_input_tokens": usage.get("processed_input_tokens"),
                     **grade(refs[row["case_id"]]["expected"], row["commands"], row["status"])})
        scores = {}
        for profile, mode in sorted({(r["profile"], r["attention"]) for r in scored}):
            group = [r for r in scored if r["profile"] == profile and r["attention"] == mode]
            scores[profile + ":" + mode] = {
                dataset + ":" + order: aggregate([r for r in group
                                                   if r["dataset"] == dataset and r["order"] == order])
                for dataset in sorted({r["dataset"] for r in group})
                for order in ("original", "reversed")
            }
            scores[profile + ":" + mode]["all"] = aggregate(group)
        before = json.loads((directory / "before_environment.json").read_text())["services"]["stdout"]
        if meta["status"] == "complete":
            after = json.loads((directory / "after_environment.json").read_text())["services"]["stdout"]
            assert before == after, "Service changed during a job"
        latency = {}
        for profile, mode, kind in sorted({(r["profile"], r["attention"], r["kind"]) for r in calls
                                           if r["kind"] in ("full30", "single_key", "serial30")}):
            group = [r for r in calls if (r["profile"], r["attention"], r["kind"]) == (profile, mode, kind)]
            result = {"client_ms": timing(r["client_ms"] for r in group)}
            if kind == "serial30":
                repetitions = {}
                for repetition in sorted({r["repetition"] for r in group}):
                    part = [r for r in group if r["repetition"] == repetition]
                    if len(part) == 30:
                        repetitions[repetition] = (
                            datetime.fromisoformat(part[-1]["finished_at"])
                            - datetime.fromisoformat(part[0]["started_at"])).total_seconds() * 1000
                result["serial30_wall_ms"] = timing(repetitions.values())
            latency[profile + ":" + mode + ":" + kind] = result
        stages[directory.name] = {
            "status": meta["status"], "calls": len(calls),
            "warmups": sum(r["kind"] == "warmup" for r in calls),
            "errors": sum(r["status"] != "ok" for r in calls),
            "scores": scores, "latency": latency, "rows": scored,
            "receipts_sha256": hashlib.sha256((directory / "receipts.jsonl").read_bytes()).hexdigest(),
        }
        all_calls.extend(calls)
    all_calls.sort(key=lambda row: row["started_at"])
    assert all(datetime.fromisoformat(a["finished_at"]) <= datetime.fromisoformat(b["started_at"])
               for a, b in zip(all_calls[:-1], all_calls[1:], strict=True))
    result = {"analyzed_at": stamp(), "stages": stages, "request_overlap_count": 0,
              "model_side_input_truncation_count": 0,
              "formal_calls": sum(r["kind"] != "warmup" for r in all_calls),
              "warmup_calls": sum(r["kind"] == "warmup" for r in all_calls)}
    save(root / "summary.json", result)
    return result


def select(root, summary):
    assert not (root / "selection.json").exists()
    assert "validation" not in summary["stages"]
    stage = summary["stages"]["development"]
    assert stage["status"] == "complete"
    control = [r for r in stage["rows"] if r["profile"] == "baseline" and r["attention"] == "bidirectional"]
    controls = {r["case_id"]: r for r in control}
    candidates = {}
    for profile in ("baseline", "rules_only"):
        rows = [r for r in stage["rows"] if r["profile"] == profile and r["attention"] == "causal"]
        metrics = aggregate(rows)
        regressions = [r["case_id"] for r in rows if controls[r["case_id"]]["correct"] and not r["correct"]]
        candidates[profile] = {"metrics": metrics, "regressions": regressions,
                               "eligible": not regressions and metrics["errors"] == 0
                               and metrics["client_ms"]["mean"] <= aggregate(control)["client_ms"]["mean"] * .8}

    def rank(profile):
        data = candidates[profile]["metrics"]
        return data["correct"], -data["extra_pairs"], -data["missing_pairs"], -data["client_ms"]["mean"]

    eligible = [profile for profile, data in candidates.items() if data["eligible"]]
    selected = max(eligible or list(candidates), key=rank)
    selection = {
        "selected_at": stamp(), "profile": selected, "attention": "causal",
        "development_eligible": selected in eligible, "candidates": candidates,
        "development_receipts_sha256": stage["receipts_sha256"],
        "validation_outputs_seen": False,
    }
    save(root / "selection.json", selection)
    return selection


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--select", action="store_true")
    args = parser.parse_args()
    result = analyze(args.run)
    print(json.dumps({name: {key: value for key, value in stage.items() if key != "rows"}
                      for name, stage in result["stages"].items()}, indent=2))
    if args.select:
        print(json.dumps(select(args.run, result), indent=2))
