"""Freeze routing policies, real catalogue metadata and synthetic request cases."""

import argparse
import copy
import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
IDS = {
    "m1": "meta-llama/llama-3.1-8b-instruct",
    "m2": "qwen/qwen3-coder-30b-a3b-instruct",
    "m3": "deepseek/deepseek-r1-0528",
    "m4": "mistralai/mistral-small-3.2-24b-instruct",
    "m5": "google/gemini-2.5-flash",
    "m6": "google/gemini-2.5-pro",
}


def wire(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def sha(value):
    return hashlib.sha256(wire(value).encode()).hexdigest()


def catalogue():
    source = json.loads((HERE / "sources/models.json").read_text())["data"]
    result = {}
    for key, model_id in IDS.items():
        row = next(m for m in source if m["id"] == model_id)
        prices = row["pricing"]
        result[key] = {
            "model": model_id,
            "context_tokens": row["context_length"],
            "max_output_tokens": row["top_provider"]["max_completion_tokens"],
            "input_modalities": row["architecture"]["input_modalities"],
            "output_modalities": row["architecture"]["output_modalities"],
            "supports": [
                p
                for p in row["supported_parameters"]
                if p in ("reasoning", "tools", "structured_outputs", "logprobs")
            ],
            "usd_per_million_input_tokens": str(Decimal(prices["prompt"]) * 1000000),
            "usd_per_million_output_tokens": str(Decimal(prices["completion"]) * 1000000),
            "input_price_tiers": [
                {
                    "min_input_tokens": o["min_prompt_tokens"],
                    "usd_per_million_input_tokens": str(Decimal(o["prompt"]) * 1000000),
                    "usd_per_million_output_tokens": str(Decimal(o["completion"]) * 1000000),
                }
                for o in prices.get("overrides", [])
                if "min_prompt_tokens" in o
            ],
            # These fields describe test fixtures, not measured vendor endpoints.
            "fixture_status": "healthy",
            "fixture_p50_latency_ms": 1000,
            "fixture_zero_data_retention": True,
        }
    return result


POLICY = """Apply every hard constraint: candidate must be healthy, allowed, not excluded, support all required input/output modalities and parameters, fit input_tokens + reserved_output_tokens within context, and reserved_output_tokens within max_output_tokens. If zero data retention is required, fixture_zero_data_retention must be true. If fallback_allowed is false, only primary_model may be chosen. A budget ceiling is inclusive.
For cost use (input_tokens * input_rate + reserved_output_tokens * output_rate) / 1000000 USD; apply a listed input price tier when input_tokens >= min_input_tokens. This is the benchmark's text-token estimate only, not an actual bill. For prefer_order choose the first eligible ID in preference_order. For lowest_cost choose the eligible model with the smallest cost. For latency_then_cost, first prefer eligible models at or below preferred_latency_ms; if none meet this SOFT preference, keep all eligible models, then choose the cheapest. Break cost ties by model ID. Select no_route if no candidate satisfies hard constraints. Never infer capability from brand names."""


def estimate_cost(model, request):
    input_rate = Decimal(model["usd_per_million_input_tokens"])
    output_rate = Decimal(model["usd_per_million_output_tokens"])
    for tier in sorted(model["input_price_tiers"], key=lambda t: t["min_input_tokens"]):
        if request["input_tokens"] >= tier["min_input_tokens"]:
            input_rate = Decimal(tier["usd_per_million_input_tokens"])
            output_rate = Decimal(tier["usd_per_million_output_tokens"])
    return (
        request["input_tokens"] * input_rate + request["reserved_output_tokens"] * output_rate
    ) / 1000000


def reference(models, request):
    """Reference is evaluated before inference and never sent to either model."""
    eligible, details = [], {}
    for key, model in models.items():
        reasons = []
        if model["fixture_status"] != "healthy":
            reasons.append("unavailable")
        if key not in request["allowed_models"] or key in request["excluded_models"]:
            reasons.append("account_model_restriction")
        if not set(request["required_input_modalities"]) <= set(model["input_modalities"]):
            reasons.append("input_modality")
        if not set(request["required_output_modalities"]) <= set(model["output_modalities"]):
            reasons.append("output_modality")
        if not set(request["required_parameters"]) <= set(model["supports"]):
            reasons.append("required_parameter")
        if request["input_tokens"] + request["reserved_output_tokens"] > model["context_tokens"]:
            reasons.append("context_limit")
        if request["reserved_output_tokens"] > model["max_output_tokens"]:
            reasons.append("output_limit")
        if request["require_zdr"] and not model["fixture_zero_data_retention"]:
            reasons.append("data_retention")
        if not request["fallback_allowed"] and key != request["primary_model"]:
            reasons.append("fallback_disabled")
        cost = estimate_cost(model, request)
        if request["budget_usd"] is not None and cost > Decimal(request["budget_usd"]):
            reasons.append("over_budget")
        details[key] = {"ineligible_reasons": reasons, "estimated_text_cost_usd": str(cost)}
        if not reasons:
            eligible.append(key)
    ranked = eligible[:]
    if request["objective"] == "latency_then_cost":
        fast = [
            k
            for k in ranked
            if models[k]["fixture_p50_latency_ms"] <= request["preferred_latency_ms"]
        ]
        ranked = fast or ranked
    if request["objective"] == "prefer_order":
        ranked.sort(key=request["preference_order"].index)
    else:
        ranked.sort(key=lambda k: (Decimal(details[k]["estimated_text_cost_usd"]), k))
    return {
        "expected": ranked[0] if ranked else "no_route",
        "hard_eligible": eligible,
        "ranked": ranked,
        "details": details,
    }


def payload(case, order):
    candidates = case["criteria"]
    if order == "reversed_order":
        candidates = dict(reversed(list(candidates.items())))
    return {
        "state": wire(case["state"]),
        "questions": {
            "decision": {
                "type": "choice",
                "instructions": "Choose exactly one route using the supplied policy and current evidence. Respect hard constraints and distinguish soft preferences. Read numbers, capability limits and availability carefully. Do not add assumptions about model quality or ignore a constraint because a model sounds suitable.",
                "criteria": candidates,
            }
        },
    }


def build_cases():
    cases = []
    profiles = {
        "economy_text": "Approved route for inexpensive short text transformation or simple label classification; no complex code/math analysis, image reading or large-document comparison.",
        "code_analysis": "Approved route for diagnosing code failures, concurrency bugs and implementation reasoning; can inspect provided source and traces.",
        "reasoning": "Approved route for multi-step mathematical or logical proofs that require deriving and checking an argument.",
        "vision": "Approved route for understanding information only present in supplied images, such as chart labels or invoice fields.",
        "long_document": "Approved route for comparing and synthesizing supplied documents totaling more than 100000 tokens.",
        "clarify": "Request missing essential material when the user's task cannot be done from supplied inputs; do not guess absent content.",
    }
    prompts = [
        (
            "rewrite",
            "Rewrite this 80-word shipping notification in a friendly tone, preserving its dates and amounts. The text is supplied.",
            "economy_text",
        ),
        (
            "ticket-label",
            "Label this short customer message as billing, bug or how-to: 'Where do I change the CSV separator?' Return one label.",
            "economy_text",
        ),
        (
            "concurrency",
            "Two supplied implementations disagree under concurrent writes. Inspect both source listings and identify the unsafe thread interleaving.",
            "code_analysis",
        ),
        (
            "debug",
            "Given the supplied stack trace and source file, determine why this SQL connection pool deadlocks and propose the minimal fix.",
            "code_analysis",
        ),
        (
            "proof",
            "Prove the supplied mathematical claim by induction, checking both the base case and inductive step rather than restating the conclusion.",
            "reasoning",
        ),
        (
            "invoice-image",
            "Read the invoice number and total amount from the attached scan. These fields occur only in the image; no OCR text is provided.",
            "vision",
        ),
        (
            "long-contracts",
            "Compare obligations across the three supplied contracts and identify conflicts. The supplied contract text totals 180000 tokens.",
            "long_document",
        ),
        (
            "missing-attachment",
            "Summarize the attached contract, but no attachment or contract text was received. Do not fabricate its contents.",
            "clarify",
        ),
    ]
    for key, prompt, expected in prompts:
        cases.append(
            {
                "id": "intent-" + key,
                "category": "semantic_task_routing",
                "state": {
                    "task": "Select the application's approved route profile for the request. Route profiles are controlled test definitions, not measured vendor quality.",
                    "request": prompt,
                },
                "criteria": profiles.copy(),
                "expected": expected,
                "reference": {"kind": "authored_task_to_profile", "expected": expected},
            }
        )

    base = catalogue()

    def add(key, category, description, changes=None, endpoints=None, expected=None):
        request = {
            "description": description,
            "input_tokens": 1000,
            "reserved_output_tokens": 500,
            "required_input_modalities": ["text"],
            "required_output_modalities": ["text"],
            "required_parameters": [],
            "allowed_models": list(base),
            "excluded_models": [],
            "objective": "prefer_order",
            "preference_order": list(base),
            "budget_usd": None,
            "primary_model": None,
            "fallback_allowed": True,
            "require_zdr": False,
            "preferred_latency_ms": None,
        }
        request.update(changes or {})
        models = copy.deepcopy(base)
        for name, values in (endpoints or {}).items():
            models[name].update(values)
        oracle = reference(models, request)
        assert oracle["expected"] == expected, (key, oracle)
        criteria = {key: wire(model) for key, model in models.items()}
        criteria["no_route"] = (
            "No model satisfies every HARD constraint. Do not route this request until requirements or availability change. A soft latency preference alone is not grounds to reject."
        )
        cases.append(
            {
                "id": key,
                "category": category,
                "state": {
                    "task": "Select an eligible model route under this application's explicitly stated policy.",
                    "provenance": "Model capabilities/prices are a frozen OpenRouter public catalogue snapshot. Availability, latency, retention flags and request requirements are SYNTHETIC TEST FIXTURES, not live endpoint measurements. No downstream model will be called.",
                    "routing_policy": POLICY,
                    "request": request,
                },
                "criteria": criteria,
                "expected": oracle["expected"],
                "reference": oracle,
            }
        )

    cap = "capability_constraints"
    add(
        "cap-image",
        cap,
        "Extract fields from an attached image.",
        {"required_input_modalities": ["text", "image"]},
        expected="m4",
    )
    add(
        "cap-audio",
        cap,
        "Process native audio input.",
        {"required_input_modalities": ["text", "audio"]},
        expected="m5",
    )
    add(
        "cap-video",
        cap,
        "Inspect video input.",
        {"required_input_modalities": ["text", "video"]},
        expected="m5",
    )
    add(
        "cap-context",
        cap,
        "Process 300000 input tokens in one request without truncation.",
        {"input_tokens": 300000},
        expected="m5",
    )
    add(
        "cap-output",
        cap,
        "Reserve 70000 output tokens; enforce the output cap.",
        {"reserved_output_tokens": 70000, "preference_order": ["m4", "m3", "m5", "m6", "m2", "m1"]},
        expected="m2",
    )
    add(
        "cap-image-logprobs",
        cap,
        "Image input with token logprobs required.",
        {"required_input_modalities": ["text", "image"], "required_parameters": ["logprobs"]},
        expected="m4",
    )
    add(
        "cap-json-tools",
        cap,
        "Tool calls and strict structured output are required.",
        {"required_parameters": ["tools", "structured_outputs"]},
        expected="m1",
    )
    add(
        "cap-image-output",
        cap,
        "The model must generate an image as output.",
        {"required_output_modalities": ["image"]},
        expected="no_route",
    )

    cost = "cost_and_budget"
    add(
        "cost-basic",
        cost,
        "Choose cheapest eligible text model.",
        {"objective": "lowest_cost"},
        expected="m1",
    )
    add(
        "cost-input-heavy",
        cost,
        "Approved coder/small-model pool; input-heavy workload.",
        {
            "objective": "lowest_cost",
            "allowed_models": ["m2", "m4"],
            "input_tokens": 10000,
            "reserved_output_tokens": 1000,
        },
        expected="m2",
    )
    add(
        "cost-output-heavy",
        cost,
        "Approved coder/small-model pool; output-heavy workload.",
        {
            "objective": "lowest_cost",
            "allowed_models": ["m2", "m4"],
            "input_tokens": 1000,
            "reserved_output_tokens": 10000,
        },
        expected="m4",
    )
    add(
        "cost-no-budget",
        cost,
        "Budget too small for the approved pool.",
        {
            "objective": "lowest_cost",
            "allowed_models": ["m2", "m4"],
            "input_tokens": 10000,
            "reserved_output_tokens": 1000,
            "budget_usd": "0.0005",
        },
        expected="no_route",
    )
    add(
        "cost-exact-budget",
        cost,
        "Inclusive budget equals one candidate's computed estimate.",
        {
            "objective": "lowest_cost",
            "allowed_models": ["m2", "m4"],
            "input_tokens": 1000,
            "reserved_output_tokens": 10000,
            "budget_usd": "0.00259375",
        },
        expected="m4",
    )
    add(
        "cost-one-fits",
        cost,
        "Only one approved model fits the budget.",
        {
            "objective": "lowest_cost",
            "allowed_models": ["m2", "m4"],
            "input_tokens": 10000,
            "reserved_output_tokens": 1000,
            "budget_usd": "0.001",
        },
        expected="m2",
    )
    add(
        "cost-long-context",
        cost,
        "Long context; apply the listed long-input price tier where relevant.",
        {"objective": "lowest_cost", "input_tokens": 300000, "reserved_output_tokens": 1000},
        expected="m5",
    )
    add(
        "cost-reasoning-output",
        cost,
        "Explicit reasoning parameter required; minimize total price for long output.",
        {
            "objective": "lowest_cost",
            "required_parameters": ["reasoning"],
            "input_tokens": 1000,
            "reserved_output_tokens": 10000,
        },
        expected="m3",
    )

    fail = "availability_fallback_and_preferences"
    add(
        "fallback-primary-down",
        fail,
        "Primary route is down; use the approved fallback.",
        {"allowed_models": ["m5", "m6"], "primary_model": "m5"},
        {"m5": {"fixture_status": "down"}},
        expected="m6",
    )
    add(
        "fallback-rate-limit",
        fail,
        "The cheapest endpoint is rate-limited; select cheapest healthy alternative.",
        {"objective": "lowest_cost", "primary_model": "m1"},
        {"m1": {"fixture_status": "rate_limited"}},
        expected="m2",
    )
    add(
        "fallback-disabled",
        fail,
        "Fallbacks disabled; primary route is down.",
        {"primary_model": "m5", "fallback_allowed": False},
        {"m5": {"fixture_status": "down"}},
        expected="no_route",
    )
    add(
        "fallback-all-down",
        fail,
        "No healthy endpoint exists.",
        endpoints={k: {"fixture_status": "down"} for k in base},
        expected="no_route",
    )
    add(
        "fallback-excluded",
        fail,
        "Account restricts allowed models and excludes one of them.",
        {"allowed_models": ["m2", "m3"], "excluded_models": ["m2"]},
        expected="m3",
    )
    add(
        "fallback-retention",
        fail,
        "Only approved ZDR endpoint fixtures may process this request.",
        {"allowed_models": ["m5", "m6"], "require_zdr": True},
        {"m5": {"fixture_zero_data_retention": False}},
        expected="m6",
    )
    add(
        "latency-soft-unmet",
        fail,
        "Latency preference is soft; all models exceed it. Do not reject solely for this.",
        {"objective": "latency_then_cost", "preferred_latency_ms": 2000},
        {k: {"fixture_p50_latency_ms": 3000 + i * 1000} for i, k in enumerate(base)},
        expected="m1",
    )
    add(
        "latency-preferred-pool",
        fail,
        "Choose cheapest model meeting the soft latency preference when such candidates exist.",
        {"objective": "latency_then_cost", "preferred_latency_ms": 1000},
        {
            k: {"fixture_p50_latency_ms": ms}
            for k, ms in zip(base, [3000, 2000, 6000, 800, 500, 700], strict=True)
        },
        expected="m4",
    )
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite a frozen plan")
    cases = build_cases()
    for case in cases:
        request = payload(case, "original_order")
        assert len(request["state"]) <= 12000
        assert all(len(text) <= 1000 for text in case["criteria"].values())
    plan = {
        "created_at": datetime.now(UTC).isoformat(),
        "inference_started": False,
        "cases": cases,
        "variants": ["original_order", "reversed_order"],
        "max_calls": len(cases) * 2 * 2,
        "providers": ["jev", "decider"],
        "method": "32 unique requests, 8 per category; every request/order is identical for both models. Reverse only candidate insertion order. No candidate filtering, retries, answer replacement or downstream generation.",
        "limitations": [
            "Task-profile labels are authored; model metadata is public; runtime endpoint state and request requirements are synthetic.",
            "This tests routing policy adherence, not OpenRouter Auto performance or routed-model answer quality.",
            "Published model-level supported parameters are not a guarantee about every provider endpoint.",
            "Cost is a defined text-token estimate using catalogue rates and tiers; no caching, media charges, tool costs, actual billing or hidden reasoning-token usage measured.",
            "Small English-language diagnostic set; order variants are repeated cases, not independent samples.",
        ],
        "sources": json.loads((HERE / "sources/manifest.json").read_text()),
    }
    plan["plan_sha256"] = sha(plan)
    args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
    print(
        wire(
            {
                "cases": len(cases),
                "max_calls": plan["max_calls"],
                "plan_sha256": plan["plan_sha256"],
            }
        )
    )


if __name__ == "__main__":
    main()
