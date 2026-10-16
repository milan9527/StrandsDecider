"""Summarize paired observations; do not treat policy agreement as model accuracy."""

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path

PROVIDERS = ("decider", "jev", "bedrock")
EXPECTED_WORKFLOWS = {
    "support": "customer_support",
    "code": "coding",
    "analysis": "reasoning",
    "retrieval": "embedding",
}


def side_time(side):
    if side["error"] or len(side["steps"]) != 2 or not side["steps"][-1]["selected_model"]:
        return None
    return sum(s["timings"]["backend_total_ms"] for s in side["steps"])


def stats(values):
    values = [v for v in values if v is not None]
    return {
        "n": len(values),
        "mean_ms": statistics.mean(values) if values else None,
        "min_ms": min(values) if values else None,
        "max_ms": max(values) if values else None,
    }


def chosen(side):
    return side["steps"][-1].get("selected_model") if len(side["steps"]) == 2 else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    args = parser.parse_args()
    data = json.loads(args.result.read_text())
    if not data["live"]:
        parser.error("Replay is not performance evidence")
    out = {
        "started_at": data["started_at"],
        "finished_at": data["finished_at"],
        "rounds": len(data["runs"]),
        "providers": {},
        "cases": {},
        "method": data["method"],
        "evidence_version": data["runs"][0].get("evidence_optimization", {}).get("version"),
        "legacy_program_policy_version": data["runs"][0]
        .get("task_ranking_policy", {})
        .get("version"),
        "catalog_version": data["runs"][0]["catalog_version"],
        "ranking_version": data["runs"][0]["ranking_version"],
        "warmup_attempts": len(data["warmups"]),
        "formal_route_calls": sum(c["path"] == "routing/decision" for c in data["calls"]),
        "program_rank_calls": sum(c["path"] == "routing/rank" for c in data["calls"]),
        "target_calls": sum(c["path"] == "routing/execute" for c in data["calls"]),
    }
    for p in PROVIDERS:
        before, after, flow_results = [], [], []
        for case, expected in EXPECTED_WORKFLOWS.items():
            ws = [r["cases"][case] for r in data["runs"]]
            sides = [w["sides"][p] for w in ws]
            opts = [w["optimizedSides"][p] for w in ws]
            flows = [s["steps"][0]["choice"] if s["steps"] else None for s in sides]
            flow_results.extend(f == expected for f in flows)
            b, a = [side_time(s) for s in sides], [side_time(s) for s in opts]
            before.extend(b)
            after.extend(a)
            row = {
                "original_route": stats(b),
                "optimized_route": stats(a),
                "attempts": len(ws),
                "workflow_correct": sum(f == expected for f in flows),
                "original_choices": dict(
                    Counter(chosen(s)["id"] if chosen(s) else "FAILED" for s in sides)
                ),
                "optimized_choices": dict(
                    Counter(chosen(s)["id"] if chosen(s) else "FAILED" for s in opts)
                ),
            }
            if "execution_export" in data:
                executed = data["execution_export"]["cases"][case]
                for key, source in (("original", "sides"), ("optimized", "optimizedSides")):
                    side = executed[source][p]
                    row[key + "_execution"] = {
                        "selected_model": chosen(side),
                        "result": side["execution"],
                        "route_error": side["error"],
                    }
            out["cases"].setdefault(case, {})[p] = row
        out["providers"][p] = {
            "attempts": len(before),
            "workflow_correct": sum(flow_results),
            "original": stats(before),
            "optimized": stats(after),
            "original_route_failures": sum(v is None for v in before),
            "optimized_route_failures": sum(v is None for v in after),
        }
    destination = args.result.with_name("summary.json")
    destination.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: out[k]
                for k in (
                    "rounds",
                    "warmup_attempts",
                    "formal_route_calls",
                    "program_rank_calls",
                    "target_calls",
                    "providers",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
