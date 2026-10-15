"""Paired live router selection calls; never execute the selected downstream model."""

import argparse
import asyncio
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path

from prepare import payload, sha

HERE = Path(__file__).resolve().parent
sys.path.append(str(HERE.parent / "browser_finance"))
from common import Models, save, stamp, wire  # noqa: E402


def grade(case, receipt, variant):
    choice = receipt.get("choice")
    details = case["reference"].get("details", {}).get(choice, {})
    hard_eligible = case["reference"].get("hard_eligible")
    return {
        "case_id": case["id"],
        "category": case["category"],
        "provider": receipt["provider"],
        "variant": variant,
        "status": receipt["status"],
        "choice": choice,
        "expected": case["expected"],
        "correct": receipt["status"] == "ok" and choice == case["expected"],
        "violated_hard_constraints": details.get("ineligible_reasons", []),
        "false_no_route": choice == "no_route" and bool(hard_eligible),
        "eligible_but_not_preferred": hard_eligible is not None
        and choice in hard_eligible
        and choice != case["expected"],
        "elapsed_ms": receipt["elapsed_ms"],
        "input_sha256": receipt["input_sha256"],
    }


def summarize(rows, receipts):
    result = {}
    for provider in ("jev", "decider"):
        group = [r for r in rows if r["provider"] == provider]
        api = [r for r in receipts if r["provider"] == provider]
        times = sorted(r["elapsed_ms"] for r in api)
        pairs = {}
        for row in group:
            pairs.setdefault(row["case_id"], {})[row["variant"]] = row
        complete = [
            p
            for p in pairs.values()
            if len(p) == 2 and all(r["status"] == "ok" for r in p.values())
        ]
        result[provider] = {
            "models": sorted({r["model"] for r in api if "model" in r}),
            "calls": len(api),
            "api_errors": sum(r["status"] != "ok" for r in api),
            "correct": sum(r["correct"] for r in group),
            "total": len(group),
            "by_category": {
                category: {
                    variant: {
                        "correct": sum(
                            r["correct"]
                            for r in group
                            if r["category"] == category and r["variant"] == variant
                        ),
                        "total": sum(
                            r["category"] == category and r["variant"] == variant for r in group
                        ),
                    }
                    for variant in ("original_order", "reversed_order")
                }
                for category in sorted({r["category"] for r in group})
            },
            "order_changed_choice": sum(
                p["original_order"]["choice"] != p["reversed_order"]["choice"] for p in complete
            ),
            "order_pairs": len(complete),
            "hard_constraint_violations": sum(bool(r["violated_hard_constraints"]) for r in group),
            "false_no_route": sum(r["false_no_route"] for r in group),
            "eligible_but_not_preferred": sum(r["eligible_but_not_preferred"] for r in group),
            "median_rtt_ms": statistics.median(times) if times else None,
            "p95_rtt_ms": times[math.ceil(0.95 * len(times)) - 1] if times else None,
            "wrong": [r for r in group if not r["correct"]],
        }
    return result


async def run(args):
    plan = json.loads(args.plan.read_text())
    assert sha({k: v for k, v in plan.items() if k != "plan_sha256"}) == plan["plan_sha256"]
    for source in plan["sources"]:
        assert (
            hashlib.sha256((HERE / "sources" / source["file"]).read_bytes()).hexdigest()
            == source["sha256"]
        )
    args.output.mkdir(parents=True, exist_ok=False)
    metadata = {
        "started_at": stamp(),
        "status": "running",
        "plan_sha256": plan["plan_sha256"],
        "source_code_sha256": {
            str(p.relative_to(HERE.parent)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [
                HERE / "prepare.py",
                HERE / "run.py",
                HERE.parent / "browser_finance/common.py",
            ]
        },
        "downstream_calls": 0,
    }
    save(args.output / "plan.json", plan)
    save(args.output / "run.json", metadata)
    rows, receipts = [], []
    with (args.output / "receipts.jsonl").open("x") as stream:
        try:
            async with Models(
                args.gateway, args.credentials, args.jev_key, plan["max_calls"]
            ) as models:
                save(args.output / "decider-health.json", models.health)
                for index, case in enumerate(plan["cases"]):
                    for variant in plan["variants"]:
                        request = payload(case, variant)
                        order = ("jev", "decider") if index % 2 else ("decider", "jev")
                        paired = await asyncio.gather(*(models.decide(p, request) for p in order))
                        assert len({r["input_sha256"] for r in paired}) == 1
                        for receipt in paired:
                            receipt.update(
                                case_id=case["id"], category=case["category"], variant=variant
                            )
                            stream.write(wire(receipt) + "\n")
                            stream.flush()
                            receipts.append(receipt)
                            rows.append(grade(case, receipt, variant))
                    save(args.output / "results.json", rows)
                    print(
                        wire(
                            {
                                "case": case["id"],
                                "expected": case["expected"],
                                "answers": [
                                    {
                                        k: r[k]
                                        for k in (
                                            "provider",
                                            "variant",
                                            "status",
                                            "choice",
                                            "correct",
                                        )
                                    }
                                    for r in rows[-4:]
                                ],
                            }
                        ),
                        flush=True,
                    )
                metadata.update(status="complete", finished_at=stamp(), actual_calls=models.calls)
        finally:
            save(args.output / "results.json", rows)
            save(args.output / "summary.json", summarize(rows, receipts))
            save(args.output / "run.json", metadata)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gateway", default="https://d3i7ogfx5ml7dc.cloudfront.net")
    parser.add_argument(
        "--credentials",
        type=Path,
        default=HERE.parent.parent / ".deployment/admin-credentials.json",
    )
    parser.add_argument("--jev-key", type=Path, default=Path("/home/ec2-user/ai/jev/jevkey.txt"))
    parser.add_argument("--live", action="store_true", required=True)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
