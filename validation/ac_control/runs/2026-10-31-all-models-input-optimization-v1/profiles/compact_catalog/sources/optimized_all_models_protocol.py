"""Freeze three complete nine-model comparisons with equivalent AC capabilities."""

import argparse
import copy
import json
from pathlib import Path

from all_models_protocol import PROVIDERS, SOURCE_NAMES, digest, save, sha, stamp
from compact_input_protocol import BASELINE, VARIANTS, audit_request, compact_request, single_field_request

HERE = Path(__file__).resolve().parent
ROOT = HERE / "runs/2026-10-31-all-models-input-optimization-v1"
SOURCES = tuple(dict.fromkeys((*SOURCE_NAMES, "prepare.py", "compact_input_protocol.py",
                              "optimized_all_models_protocol.py", "run_optimized_models.py")))


def portable_request(payload, variant):
    request = compact_request(payload, variant)
    for question in request["questions"].values():
        for key, description in question["criteria"].items():
            if description is None:
                question["criteria"][key] = key
    audit_request(payload, request)
    return request


def business_payload(case, key):
    request = case["payload"]
    return copy.deepcopy(request) if key is None else single_field_request(request, key)


def profile_order(provider):
    offset = PROVIDERS.index(provider) % len(VARIANTS)
    return VARIANTS[offset:] + VARIANTS[:offset]


def prepare(root):
    original_cases = json.loads((BASELINE / "cases.json").read_text())
    old_plan = json.loads((BASELINE / "plan.json").read_text())
    jobs = json.loads((BASELINE / "schedule.json").read_text())
    assert sum(len(job["keys"]) for job in jobs) == 2049
    root.mkdir(parents=True, exist_ok=False)
    save(root / "plan.json", {
        "prepared_at": stamp(), "providers": list(PROVIDERS), "profiles": list(VARIANTS),
        "calls_per_profile_provider": 2049, "total_calls": 2049 * 3 * 9,
        "formal_calls": 2016 * 3 * 9, "outer_concurrency": 1, "automatic_retries": 0,
        "profile_order": {provider: list(profile_order(provider)) for provider in PROVIDERS},
        "runtime_order": ["jev", "gpt", "decider", "liquid", "pplx", "knowline", "torchcast", "clef", "h2o"],
        "primary": "20 original specification queries, all 30 fields, entire command-set exact match.",
        "layouts": "Every primary query, three repetitions each of serial30 and full30; single-step reuses serial calls.",
        "quality": "156 requests per profile/model: spec, diagnostic, English variations, Chinese translations; both orders.",
        "portable_descriptions": "Numeric candidate descriptions are their string IDs for all nine models; no null descriptions.",
        "capability_policy": "Full mapping recoverable in every request, including single-field requests.",
        "profile_policy": "Frozen before inference; no answer-based tuning or best-case profile mixing.",
        "cache_policy": "Keep native caches and identical within-profile warmups; rotate profile order by provider.",
        "hardware_policy": "Reuse dedicated g6.xlarge/L4; same pinned model runtimes. Hosted models use prior US clients.",
        "answers_transferred": False, "historical_records_reused": False,
        "latency_policy": "Request-response; serial wall contains only the thirty calls and their in-memory handling.",
        "scope": "Input representation only; no output repair, query-based candidate filtering, or unit auto-completion.",
        "upstream_run": BASELINE.name, "spec_sha256": old_plan["input_sha256"]["spec.md"],
    })
    for variant in VARIANTS:
        target = root / "profiles" / variant
        target.mkdir(parents=True)
        cases = [{**case, "payload": portable_request(case["payload"], variant)} for case in original_cases]
        for original, candidate in zip(original_cases, cases):
            for key in candidate["payload"]["questions"]:
                single = business_payload(candidate, key)
                assert list(single["questions"]) == [key]
                from compact_input_protocol import catalog_from_request
                assert catalog_from_request(single) == catalog_from_request(original["payload"])
        for name in ("references.json", "command_set.json", "spec_references.json", "spec.md", "models.json"):
            (target / name).write_bytes((BASELINE / name).read_bytes())
        save(target / "cases.json", cases)
        save(target / "schedule.json", jobs)
        for name in SOURCES:
            path = target / "sources" / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes((HERE / name).read_bytes())
        plan = copy.deepcopy(old_plan)
        plan.update(
            prepared_at=stamp(), profile=variant, all_results_new_live_calls=True,
            prompt=f"Specification-preserving {variant}; portable numeric labels; no answer repair.",
            source_sha256={name: digest(target / "sources" / name) for name in SOURCES},
            input_sha256={name: digest(target / name) for name in old_plan["input_sha256"]},
        )
        save(target / "plan.json", plan)
    print(json.dumps({"run": str(root), "profiles": 3, "providers": 9, "planned_calls": 55323}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=ROOT)
    prepare(parser.parse_args().run)
