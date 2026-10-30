"""Collect a running benchmark and show compact, explicitly partial scores."""

import argparse
import contextlib
import io
import json
from pathlib import Path

from analyze_ablation import analyze
from remote_ablation import collect

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--provider", choices=["decider", "liquid", "h2o"])
    args = parser.parse_args()
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        collect(args.run, json.loads((args.run / "transfer.json").read_text()))
    collected = json.loads(output.getvalue())
    print("SSM:", collected["ssm"]["Status"])
    if collected["ssm"]["Status"] == "Failed":
        print(collected["ssm"]["StandardErrorContent"])
    for provider, meta in (collected["progress"] or {}).get("models", {}).items():
        print(provider, meta["status"], f"{meta['actual_observations']}/{meta['planned_observations']}",
              "calls", meta["actual_calls"], "latest", meta["last_case"], meta["last_arm"])
    with contextlib.redirect_stdout(io.StringIO()):
        result, rows = analyze(args.run, partial=True)
    print("Observed errors:", sum(r["status"] != "ok" for r in rows))
    for provider, model in result["models"].items():
        if args.provider and provider != args.provider:
            continue
        if not any(r["provider"] == provider and not r["baseline_reused"] for r in rows):
            continue
        print(provider, {
            arm: {
                label: f"{s['exact_match']['numerator']}/{s['cases']}"
                for label, s in stats.items() if label in ("spec_original", "extension_original")
            }
            for arm, stats in model.items()
        })
