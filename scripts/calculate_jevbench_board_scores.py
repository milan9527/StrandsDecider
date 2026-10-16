#!/usr/bin/env python3
"""Reproduce published axes and calculate explicitly unofficial local projections.

This is not a replacement for the sealed JevBench v1.6 scorer. In particular,
public accuracy and ECE cannot supply its Intelligence and Calibration axes.
Uses only saved aggregate data; never calls a model or changes AWS resources.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "validation/jevbench/runs/2026-10-16-original"
AXES = ("intelligence", "calibration", "speed", "cost")


def clipped(value):
    return max(0.0, min(100.0, value))


def logarithmic_score(value, reference, penalty):
    if not math.isfinite(value) or value < 0:
        raise ValueError("Expected a finite nonnegative measurement")
    return 100.0 if value == 0 else clipped(
        100 - penalty * math.log10(value / reference)
    )


def speed_score(p50, p95):
    return sum(logarithmic_score(x, 0.1, 20) for x in (p50, p95)) / 2


def cost_score(usd_per_1000):
    return logarithmic_score(usd_per_1000, 0.001, 30)


def composite(axes):
    """Official Option A aggregate formula; missing axes stay missing."""
    if any(axes.get(key) is None for key in AXES):
        return None
    values = [axes[key] for key in AXES]
    if any(not math.isfinite(x) or not 0 <= x <= 100 for x in values):
        raise ValueError("Axes must be finite values from 0 to 100")
    if 0 in values:
        return 0.0
    harmonic = 4 / sum(1 / x for x in values)
    gates = math.prod(
        min(1, axes[key] / 50) ** 2 for key in ("intelligence", "speed", "cost")
    )
    return harmonic * gates


def verify_reference(reference):
    errors = {"composite": [], "speed": [], "cost": [], "capability": []}

    def check(axis, computed, published):
        if published is not None:
            if computed is None:
                raise AssertionError(f"Missing computed {axis}")
            delta = abs(computed - published)
            if delta > 1e-9:
                raise AssertionError(f"{axis} differs by {delta}")
            errors[axis].append(delta)

    for row in reference["systems"]:
        axes = row["axes"]
        check("composite", composite(axes), row.get("jevbench_score"))
        check(
            "speed",
            speed_score(row["speed"]["p50_s_adjusted"], row["speed"]["p95_s_adjusted"]),
            axes.get("speed"),
        )
        usd = row.get("usd_per_1000")
        if usd is not None:
            check("cost", cost_score(usd), axes.get("cost"))
        if all(axes.get(k) is not None for k in ("intelligence", "calibration")):
            check(
                "capability",
                (axes["intelligence"] + axes["calibration"]) / 2,
                row.get("capability"),
            )
    return {
        name: {"checked": len(values), "max_absolute_error": max(values, default=0)}
        for name, values in errors.items()
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=RUN)
    parser.add_argument("--reference", type=Path, default=RUN / "leaderboard-reference.json")
    parser.add_argument("--hourly-usd", type=float, default=0.8048)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not math.isfinite(args.hourly_usd) or args.hourly_usd <= 0:
        parser.error("--hourly-usd must be finite and positive")
    summary = json.loads((args.run / "summary.json").read_text())
    analysis = json.loads((args.run / "analysis.json").read_text())
    reference = json.loads(args.reference.read_text())
    verification = verify_reference(reference)
    p50, p95 = (summary["latency"][f"p{q}_s"] for q in (50, 95))
    adjusted50, adjusted95 = 2 * p50 + 0.15, 2 * p95 + 0.15
    mean = analysis["client_mean_ms"] / 1000
    cost_cases = {}
    for name, seconds in (
        ("website_p50_what_if", p50),
        ("mean_call_time_allocation", mean),
    ):
        cost_cases[name] = [
            {
                "utilisation": utilisation,
                "usd_per_1000": (usd := args.hourly_usd * seconds / 3.6 / utilisation),
                "cost_axis": cost_score(usd),
            }
            for utilisation in (1.0, 0.5, 0.1)
        ]
    partial_axes = {
        "intelligence": None,
        "calibration": None,
        "speed": speed_score(adjusted50, adjusted95),
        "cost": cost_cases["mean_call_time_allocation"][0]["cost_axis"],
    }
    output = {
        "status": "unofficial_partial_projection_only",
        "official_capability": None,
        "official_composite": composite(partial_axes),
        "rank": None,
        "missing": [
            "Current-release 300 public and 1200 sealed decisions",
            "Versioned per-type/tier Intelligence and Calibration scoring",
            "Official evaluation latency and common cost basis",
        ],
        "input_sha256": {
            str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path):
            hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                args.run / "summary.json", args.run / "analysis.json", args.reference
            )
        },
        "observed_public_v1": {
            "n": summary["n_attempted"],
            "correct": summary["n_correct"],
            "accuracy_percent": summary["accuracy"] * 100,
            "brier": summary["brier_mean"],
            "ece": summary["ece"]["ece"],
            "p50_s": p50,
            "p95_s": p95,
            "mean_s": mean,
        },
        "speed_projections": {
            "private_http_direct_axis": speed_score(p50, p95),
            "self_hosted_rule_p50_s": adjusted50,
            "self_hosted_rule_p95_s": adjusted95,
            "self_hosted_rule_axis": partial_axes["speed"],
            "limitation": (
                "Private HTTP measurement is not evaluator loopback or public API timing. "
                "Applying 2x+150ms is a sensitivity calculation, not an official score."
            ),
        },
        "cost_projections": {
            "hourly_usd": args.hourly_usd,
            "monthly_730h_compute_usd": args.hourly_usd * 730,
            "basis": "g6.xlarge Linux On Demand us-east-1; compute only; one serial stream",
            "cases": cost_cases,
            "limitation": (
                "Website p50 capacity is modeled, not measured throughput. "
                "Mean-call allocation excludes idle time at utilisation=1, "
                "EBS, network, application and benchmark-client costs. "
                "Neither case supplies the official common-cost axis."
            ),
        },
        "reference_formula_verification": verification,
        "published_examples": [
            row for row in reference["systems"]
            if row["key"] in ("jev-1.13.0", "sage-1.3.0", "h2o-lightning-4b")
        ],
    }
    text = json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
