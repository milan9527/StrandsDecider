"""Score fixed decisions separately from transport/format errors and latency."""
import collections
import hashlib
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).parent


def percentile(values, q):
    values = sorted(values)
    if not values:
        return None
    index = (len(values) - 1) * q
    lo = int(index)
    hi = min(lo + 1, len(values) - 1)
    return round(values[lo] + (values[hi] - values[lo]) * (index - lo), 2)


def score(rows, references):
    total_questions = sum(len(references[r["case_id"]]["expected"]) for r in rows)
    success = [r for r in rows if r["status"] == "ok"]
    correct = sum(sum(r["choices"].get(k) == v for k, v in references[r["case_id"]]["expected"].items())
                  for r in success)
    exact = sum(r["choices"] == references[r["case_id"]]["expected"] for r in success)
    by_case = collections.defaultdict(dict)
    for row in success:
        by_case[row["case_id"]][row["variant"]] = row["choices"]
    pairs = [r for r in by_case.values() if "original" in r and "reversed" in r]
    flip_questions = sum(sum(a != pair["reversed"].get(k) for k, a in pair["original"].items())
                         for pair in pairs)
    pair_questions = sum(len(pair["original"]) for pair in pairs)
    latency = [r["client_ms"] for r in success]
    inference = [r["response"]["benchmark_timing"]["inference_ms"] for r in success
                 if r.get("response", {}).get("benchmark_timing")]
    return {
        "requests": len(rows), "valid_responses": len(success),
        "call_or_format_failures": len(rows) - len(success),
        "correct_decisions": correct, "total_decisions": total_questions,
        "decision_accuracy_including_failures": round(correct / total_questions, 4) if total_questions else None,
        "exact_cases": exact, "case_accuracy_including_failures": round(exact / len(rows), 4),
        "valid_case_accuracy": round(exact / len(success), 4) if success else None,
        "candidate_order_flip_cases": sum(p["original"] != p["reversed"] for p in pairs),
        "valid_order_pairs": len(pairs), "candidate_order_flip_decisions": flip_questions,
        "paired_decisions": pair_questions,
        "client_p50_ms": percentile(latency, .5), "client_p95_ms": percentile(latency, .95),
        "inference_p50_ms": percentile(inference, .5), "inference_p95_ms": percentile(inference, .95),
    }


def main():
    refs = json.loads((ROOT / "references.json").read_text())
    requests = json.loads((ROOT / "requests.json").read_text())
    ordered = [{"case_id": r["case_id"], "variant": r["variant"],
                "ordered_request_sha256": hashlib.sha256(
                    json.dumps(r["request"], ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()}
               for r in requests]
    (ROOT / "ordered_request_hashes.json").write_text(json.dumps(ordered, indent=2))
    summary = {}
    mistakes = []
    for path in sorted((ROOT / "results").glob("*-quality.jsonl")):
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        if not rows:
            continue
        provider = rows[0]["provider"]
        groups = collections.defaultdict(list)
        for r in rows:
            groups[r["group"]].append(r)
            if r["status"] != "ok" or r["choices"] != refs[r["case_id"]]["expected"]:
                mistakes.append({k: r.get(k) for k in ["provider", "case_id", "variant", "status",
                                                     "choices", "error_type", "error"]} |
                                {"expected": refs[r["case_id"]]["expected"]})
        summary[provider] = {"complete": len(rows) == len(requests), "overall": score(rows, refs),
                             "groups": {g: score(rs, refs) for g, rs in groups.items()}}
        categories = collections.defaultdict(list)
        for row in rows:
            if row["group"] == "routing":
                categories[refs[row["case_id"]]["category"]].append(row)
        summary[provider]["routing_categories"] = {k: score(v, refs) for k, v in categories.items()}
    (ROOT / "results/summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    (ROOT / "results/mismatches.json").write_text(json.dumps(mistakes, indent=2, ensure_ascii=False))
    for provider, result in summary.items():
        print(provider, json.dumps(result["overall"]))
        for group, result in result["groups"].items():
            print(" ", group, result["exact_cases"], "/", result["requests"],
                  result["client_p50_ms"], "ms", result["call_or_format_failures"], "failures")


if __name__ == "__main__":
    main()
