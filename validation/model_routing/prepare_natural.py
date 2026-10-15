"""Second diagnostic: same 24 policy cases, natural-language candidate metadata."""

import argparse
import copy
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from prepare import sha


def describe(model):
    tiers = (
        "; ".join(
            f"at input length >= {tier['min_input_tokens']} tokens, input USD {tier['usd_per_million_input_tokens']}/million and output USD {tier['usd_per_million_output_tokens']}/million"
            for tier in model["input_price_tiers"]
        )
        or "none"
    )
    return (
        f"Route to {model['model']}. "
        f"Accepted input modalities: {', '.join(model['input_modalities'])}. "
        f"Produced output modalities: {', '.join(model['output_modalities'])}. "
        f"Supported request parameters: {', '.join(model['supports']) or 'none'}. "
        f"Context capacity: {model['context_tokens']} combined input+output tokens. "
        f"Maximum output: {model['max_output_tokens']} tokens. "
        f"Price: input USD {model['usd_per_million_input_tokens']} per million tokens; output USD {model['usd_per_million_output_tokens']} per million tokens. "
        f"Input-length price tiers: {tiers}. "
        f"Test endpoint status: {model['fixture_status']}. "
        f"Test endpoint p50 latency: {model['fixture_p50_latency_ms']} ms. "
        f"Test endpoint zero data retention: {'yes' if model['fixture_zero_data_retention'] else 'no'}."
    )


def convert(parent):
    plan = copy.deepcopy(parent)
    plan.pop("plan_sha256")
    plan["parent_plan_sha256"] = parent["plan_sha256"]
    plan["created_at"] = datetime.now(UTC).isoformat()
    plan["cases"] = [c for c in plan["cases"] if c["category"] != "semantic_task_routing"]
    for case in plan["cases"]:
        for key, description in case["criteria"].items():
            if key != "no_route":
                case["criteria"][key] = describe(json.loads(description))
                assert len(case["criteria"][key]) <= 1000
    plan["max_calls"] = len(plan["cases"]) * 2 * 2
    plan["method"] = (
        "Post-first-batch format diagnostic; same 24 non-semantic cases, state, policy, labels, IDs and metadata facts. Only JSON candidate metadata is expressed in natural language. Both orders tested. No eligibility filtering or model output substitution."
    )
    plan["formatter_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    plan["plan_sha256"] = sha(plan)
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite a plan")
    plan = convert(json.loads(args.parent.read_text()))
    args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {"cases": len(plan["cases"]), "calls": plan["max_calls"], "hash": plan["plan_sha256"]}
        )
    )


if __name__ == "__main__":
    main()
