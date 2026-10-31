"""Frozen nine-model baseline and complete specification request-layout schedule."""

import argparse
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE / "runs/2026-10-30-all-models-full-v1"
PROVIDERS = ("jev", "gpt", "decider", "liquid", "pplx", "knowline", "torchcast", "clef", "h2o")
SOURCE_NAMES = (
    "all_models_protocol.py", "run_all_models.py", "run_candidate_benchmark.py",
    "api_ablation_protocol.py", "run_api_ablation.py", "resume_api_capture.py",
    "run_resident.py", "run_ablation.py", "ablation_protocol.py",
)


def stamp():
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017 - also used by GPU-host Python


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wire(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def sha(value):
    return hashlib.sha256(wire(value).encode()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False, default=str) + "\n")


def schedule(cases):
    """No references or prior responses are used to construct requests."""
    s03 = next(c for c in cases if c["case_id"] == "S03" and c["order"] == "original")
    primary = [c for c in cases if c["dataset"] == "spec" and c["order"] == "original"]
    assert len(primary) == 20 and len(cases) == 156
    jobs = []

    def add(case, kind, repetition=0, keys=None):
        keys = keys or [None]
        jobs.append({
            "case_id": case["case_id"], "dataset": case["dataset"], "order": case["order"],
            "language": case["language"], "kind": kind, "repetition": repetition,
            "keys": keys,
        })

    for repetition in range(3):
        add(s03, "warmup_full30", repetition)
    for case in cases:
        add(case, "quality")
    for key in s03["payload"]["questions"]:
        add(s03, "warmup_single", keys=[key])
    for repetition in range(3):
        for index, case in enumerate(primary):
            # Counterbalance layout order across both cases and repetitions.
            kinds = ("serial30", "full30") if (index + repetition) % 2 == 0 else ("full30", "serial30")
            for kind in kinds:
                add(case, kind, repetition,
                    list(case["payload"]["questions"]) if kind == "serial30" else None)
    assert sum(len(j["keys"]) for j in jobs) == 2049
    return jobs


def business_payload(case, key):
    result = copy.deepcopy(case["payload"])
    if key is not None:
        result["questions"] = {key: result["questions"][key]}
    return result


def prepare(root):
    from api_ablation_protocol import GPT_MODEL, GPT_SYSTEM
    from prepare import SPEC, payload, read_spec

    parent = HERE / "runs/2026-10-30-spec-unified-v1"
    assert not (root / "plan.json").exists(), "Never overwrite a frozen plan"
    caps, refs = read_spec()
    cases = json.loads((parent / "cases.json").read_text())
    for ref in refs:
        for order in ("original", "reversed"):
            actual = next(c for c in cases if c["case_id"] == ref["id"] and c["order"] == order)
            assert actual["payload"] == payload(ref["query"], caps, order == "reversed")
    models = json.loads((parent / "models.json").read_text())
    liquid = json.loads((HERE.parents[1] / ".deployment/open-model-liquid-manifest.json").read_text())
    models.update({
        "liquid": {"repository": "LiquidAI/d1-2B", "revision": liquid["revision"],
                   "runtime": "Official BF16 Transformers system_one"},
        "decider": {"repository": "strands-decider-2B-hobson-v19-vllm",
                    "runtime": "Existing v19 vLLM service reproduced on isolated L4; identity and artifacts recorded before inference"},
        "jev": {"repository": "jev-latest", "version_policy": "Pin first successful warmup response"},
        "gpt": {"repository": GPT_MODEL, "reasoning_effort": "low", "max_output_tokens": 8192},
    })
    root.mkdir(parents=True, exist_ok=True)
    for name in ("cases.json", "references.json", "command_set.json", "spec_references.json", "spec.md"):
        (root / name).write_bytes((parent / name).read_bytes())
    assert digest(root / "spec.md") == digest(SPEC)
    save(root / "models.json", models)
    save(root / "schedule.json", schedule(cases))
    for name in SOURCE_NAMES:
        target = root / "sources" / name
        target.parent.mkdir(exist_ok=True)
        target.write_bytes((HERE / name).read_bytes())
    old = json.loads((parent / "plan.json").read_text())
    save(root / "plan.json", {
        "prepared_at": stamp(), "providers": list(PROVIDERS), "all_results_new_live_calls": True,
        "prompt": "Unmodified full30 baseline from AC_Control_Test_Spec.md; no answer repair.",
        "quality": "156 full30 calls: 20 spec, 10 diagnostics, 24 English new cases, 24 Chinese translations; both option orders.",
        "primary_acceptance": "Original-order 20 specification queries; 40 expected command pairs. Entire command-set exact match.",
        "request_layouts": "All 20 original-order specification cases, three repetitions of serial30 and full30; same state and options.",
        "single_step_definition": "Each of 1800 actual single-field calls within 60 serial30 tasks; shared records, not extra trials.",
        "calls_per_provider": 2049, "formal_per_provider": 2016, "warmups_per_provider": 33,
        "repetitions": 3, "layout_cases": 20, "layout_tasks_per_mode": 60,
        "quality_calls_per_provider": 156, "serial30_calls_per_provider": 1800,
        "full30_layout_calls_per_provider": 60,
        "layout_order": "Alternate serial30/full30 order by case index plus repetition parity; all providers identical.",
        "warmups": "Three complete S03 calls, then quality; one S03 call for each of 30 field shapes before layout trials.",
        "outer_concurrency": 1, "automatic_retries": 0,
        "references_sent_to_models": False, "output_repair": False,
        "serial30_artifact_operations_inside_block": 0,
        "failure_policy": "Preserve every attempt and error in its denominator; stop after three consecutive failed calls. No automatic replay.",
        "cache_policy": "Native caches retained, identical warmup and request schedule; no cache-equality claim.",
        "runtime_policy": "Pinned native runtimes; one local model at a time on isolated g6.xlarge/L4; hosted API hardware differs.",
        "resource_policy": "Reuse the prior isolated L4. No changes to original resident services. Stop test compute after evidence verification.",
        "region": old["region"], "jev_secret_arn": old["jev_secret_arn"],
        "gpt_model": GPT_MODEL, "gpt_effort": "low", "gpt_system": GPT_SYSTEM,
        "latency_scope": "Client request/response including local loopback or hosted network/SDK; serial wall includes only its 30 sequential calls.",
        "input_sha256": {name: digest(root / name) for name in (
            "cases.json", "references.json", "command_set.json", "models.json",
            "spec_references.json", "spec.md", "schedule.json")},
        "source_sha256": {name: digest(root / "sources" / name) for name in SOURCE_NAMES},
    })
    print(wire({"run": str(root), "providers": 9, "calls": 9 * 2049, "formal": 9 * 2016, "warmups": 9 * 33}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=ROOT)
    prepare(parser.parse_args().run)
