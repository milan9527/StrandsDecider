"""Summarize the same warmed 32-request workload at each concurrency."""
import json
from pathlib import Path

from analyze import percentile

ROOT = Path(__file__).parent
references = json.loads((ROOT / "references.json").read_text())
summary = {}
for path in sorted((ROOT / "results").glob("*-performance-c*.jsonl")):
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    metrics = path.with_suffix(".metrics.json")
    if not metrics.exists():
        continue
    batch = json.loads(metrics.read_text())
    valid = [row for row in rows if row["status"] == "ok"]
    times = [row["client_ms"] for row in valid]
    correct = [row for row in valid if row["choices"] == references[row["case_id"]]["expected"]]
    batch.update(client_p50_ms=percentile(times, .5), client_p95_ms=percentile(times, .95),
                 client_p99_ms=percentile(times, .99), failures=len(rows) - len(valid),
                 reference_matching_requests=len(correct),
                 reference_matching_requests_per_second=len(correct) / batch["elapsed_s"],
                 valid_decisions_per_second=sum(len(row["choices"]) for row in valid) / batch["elapsed_s"],
                 unique_cases=len({row["case_id"] for row in rows}))
    summary.setdefault(rows[0]["provider"], {})[str(rows[0]["concurrency"])] = batch
(ROOT / "results/performance_summary.json").write_text(json.dumps(summary, indent=2))
for provider, groups in summary.items():
    print(provider, [(c, round(s["client_p50_ms"], 1),
                      round(s["successful_requests_per_second"], 2), s["failures"])
                     for c, s in groups.items()])
