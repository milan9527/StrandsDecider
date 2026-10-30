"""Audit H2O trials offline; compare latency and every saved choice to baseline."""

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

from analyze import grade, timing
from run_ablation import choices
from run_resident import save, sha


def analyze(run):
    plan = json.loads((run / "plan.json").read_text())
    cases = json.loads((run / "cases.json").read_text())
    payload = json.loads((run / "payload.json").read_text())
    references = json.loads((run / "references.json").read_text())
    for name, data in (("cases", cases), ("payload", payload), ("references", references)):
        assert sha(data) == plan[name + "_sha256"]
    for name, expected in plan["runner_source_sha256"].items():
        assert hashlib.sha256((run / "sources" / name).read_bytes()).hexdigest() == expected
        assert hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() == expected
    refs = {row["id"]: row for row in references}
    lookup = {(row["case_id"], row["order"]): row for row in cases}
    variants = {}
    for meta_path in sorted((run / "variants").glob("*/run.json")):
        directory = meta_path.parent
        meta = json.loads(meta_path.read_text())
        runtime = json.loads((directory / "runtime.json").read_text())
        rows = [json.loads(line) for line in (directory / "receipts.jsonl").read_text().splitlines()]
        if meta["status"] != "complete":
            continue
        assert len(rows) == meta["actual_calls"]
        assert meta["plan_sha256"] == hashlib.sha256((run / "plan.json").read_bytes()).hexdigest()
        for previous, current in zip(rows[:-1], rows[1:], strict=True):
            assert datetime.fromisoformat(previous["finished_at"]) <= datetime.fromisoformat(current["started_at"])
        for row in rows:
            business = (lookup[row["case_id"], row["order"]]["payload"] if row["phase"] == "quality"
                        else payload if row["mode"] == "full_30" else {
                            "state": payload["state"],
                            "questions": {key: payload["questions"][key] for key in row["question_ids"]},
                        })
            transport = business if meta["attention_mode"] == "bidirectional" else {
                **business, "attention_mode": meta["attention_mode"],
            }
            assert row["input_sha256"] == sha(business)
            assert row["transport_request"] == transport and row["transport_sha256"] == sha(transport)
            assert row["question_ids"] == list(business["questions"])
            assert row["status"] == "ok" and row["http_status"] == 200
            assert row["response"] == json.loads(row["response_text"])
            assert row["response"]["attention_mode"] == meta["attention_mode"]
            assert row["choices"] == choices(row["response"], business, plan["model"])
        measurements = []
        perf = [r for r in rows if r["phase"] == "performance"]
        if meta["phase"] in ("all", "performance"):
            assert len(perf) == 93
            for repetition in range(plan["repetitions"]):
                full = [r for r in perf if r["repetition"] == repetition and r["mode"] == "full_30"]
                single = [r for r in perf if r["repetition"] == repetition and r["mode"] == "serial_1"]
                assert len(full) == 1 and len(single) == 30
                assert [r["question_ids"][0] for r in single] == list(payload["questions"])
                selected = {key: value for row in single for key, value in row["choices"].items()}
                measurements.append({
                    "repetition": repetition, "full_30_ms": full[0]["client_ms"],
                    "serial_30_wall_ms": (
                        datetime.fromisoformat(single[-1]["finished_at"])
                        - datetime.fromisoformat(single[0]["started_at"])).total_seconds() * 1000,
                    "changed_keys_when_split": [key for key in selected if selected[key] != full[0]["choices"][key]],
                    "full_usage": full[0]["response"].get("usage"),
                })
        quality = []
        quality_rows = [r for r in rows if r["phase"] == "quality"]
        if meta["phase"] in ("all", "quality"):
            assert [(r["case_id"], r["order"]) for r in quality_rows] == list(lookup)
            for row in quality_rows:
                commands = [{"cmdKey": key, "cmdValue": value} for key, value in row["choices"].items()
                            if value != "omit"]
                quality.append({
                    "case_id": row["case_id"], "order": row["order"], "dataset": row["dataset"],
                    "choices": row["choices"], "client_ms": row["client_ms"],
                    **grade(refs[row["case_id"]]["expected"], commands),
                })
        groups = {}
        for dataset, order in (("spec", "original"), ("spec", "reversed"), ("extension", "original")):
            subset = [r for r in quality if r["dataset"] == dataset and r["order"] == order]
            groups[dataset + "_" + order] = {
                "correct": sum(r["correct"] for r in subset), "count": len(subset),
                "client_ms": timing(r["client_ms"] for r in subset),
            }
        variants[directory.name] = {
            "mode": meta["attention_mode"], "formal_calls": len(rows) - 1,
            "runtime_sha256": sha({"env": runtime["env"], "image": runtime["image"],
                                   "attention_mode": meta["attention_mode"]}),
            "request_overlap_count": 0,
            "full_30_ms": timing(m["full_30_ms"] for m in measurements),
            "single_key_ms": timing(r["client_ms"] for r in perf if r["mode"] == "serial_1"),
            "serial_30_wall_ms": timing(m["serial_30_wall_ms"] for m in measurements),
            "quality": groups, "quality_rows": quality, "measurements": measurements,
            "receipts_sha256": hashlib.sha256((directory / "receipts.jsonl").read_bytes()).hexdigest(),
        }
    for name, data in variants.items():
        if data["quality_rows"]:
            data["quality_evidence_variant"] = name
            continue
        for other_name, other in variants.items():
            if other["runtime_sha256"] == data["runtime_sha256"] and other["quality_rows"]:
                data["quality"] = other["quality"]
                data["quality_rows"] = other["quality_rows"]
                data["quality_evidence_variant"] = other_name
                break
    baseline = variants.get("seq1-eager")
    if baseline:
        originals = {(r["case_id"], r["order"]): r for r in baseline["quality_rows"]}
        for data in variants.values():
            data["changed_cases_vs_baseline"] = [
                [r["case_id"], r["order"]] for r in data["quality_rows"]
                if r["choices"] != originals[r["case_id"], r["order"]]["choices"]
            ]
            data["lost_correct_cases"] = [
                [r["case_id"], r["order"]] for r in data["quality_rows"]
                if originals[r["case_id"], r["order"]]["correct"] and not r["correct"]
            ]
            data["gained_correct_cases"] = [
                [r["case_id"], r["order"]] for r in data["quality_rows"]
                if not originals[r["case_id"], r["order"]]["correct"] and r["correct"]
            ]
            if data["full_30_ms"].get("count"):
                data["full_30_speedup_vs_baseline"] = baseline["full_30_ms"]["mean"] / data["full_30_ms"]["mean"]
    summary = {"analyzed_at": datetime.now().astimezone().isoformat(), "variants": variants,
               "analyzer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    save(run / "optimization_summary.json", summary)
    print(json.dumps({name: {k: v for k, v in data.items() if k not in (
        "quality_rows", "measurements", "receipts_sha256",
    )} for name, data in variants.items()}, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    analyze(parser.parse_args().run)
