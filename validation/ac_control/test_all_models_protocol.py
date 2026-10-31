"""Check the expanded coverage and preserved inputs before paid/live inference."""

import json
from collections import Counter
from pathlib import Path

from all_models_protocol import PROVIDERS, business_payload, schedule

PARENT = Path(__file__).parent / "runs/2026-10-30-spec-unified-v1"


def cases():
    return json.loads((PARENT / "cases.json").read_text())


def test_complete_coverage_and_denominators():
    jobs = schedule(cases())
    assert set(PROVIDERS) == {"jev", "gpt", "decider", "liquid", "pplx", "knowline", "torchcast", "clef", "h2o"}
    counts = Counter()
    for job in jobs:
        counts[job["kind"]] += len(job["keys"])
    assert counts == {
        "warmup_full30": 3, "warmup_single": 30, "quality": 156, "serial30": 1800, "full30": 60,
    }
    layouts = Counter((j["case_id"], j["kind"]) for j in jobs if j["kind"] in ("serial30", "full30"))
    assert len(layouts) == 40
    assert set(layouts.values()) == {3}


def test_serial_preserves_full_state_and_all_field_candidates():
    frozen = cases()
    originals = json.loads(json.dumps(frozen))
    primary = [c for c in frozen if c["dataset"] == "spec" and c["order"] == "original"]
    for case in primary:
        keys = list(case["payload"]["questions"])
        jobs = [j for j in schedule(frozen) if j["case_id"] == case["case_id"] and j["kind"] == "serial30"]
        assert len(jobs) == 3
        for job in jobs:
            assert job["keys"] == keys and len(keys) == 30
        combined = {}
        for key in keys:
            one = business_payload(case, key)
            assert one["state"] == case["payload"]["state"]
            assert one["questions"] == {key: case["payload"]["questions"][key]}
            combined.update(one["questions"])
        assert combined == case["payload"]["questions"]
    assert frozen == originals


def test_schedule_contains_no_answers_and_preserves_quality_sequence():
    frozen = cases()
    jobs = schedule(frozen)
    assert [(j["case_id"], j["order"]) for j in jobs if j["kind"] == "quality"] == [
        (c["case_id"], c["order"]) for c in frozen]
    for job in jobs:
        assert set(job) == {"case_id", "dataset", "order", "language", "kind", "repetition", "keys"}
    assert not any("expected" in key or "answer" in key for job in jobs for key in job)


def test_layout_order_is_counterbalanced_for_every_case():
    frozen = cases()
    jobs = schedule(frozen)
    ids = [c["case_id"] for c in frozen if c["dataset"] == "spec" and c["order"] == "original"]
    for index, case_id in enumerate(ids):
        for repetition in range(3):
            actual = [j["kind"] for j in jobs if j["case_id"] == case_id
                      and j["repetition"] == repetition and j["kind"] in ("serial30", "full30")]
            expected = ["serial30", "full30"] if (index + repetition) % 2 == 0 else ["full30", "serial30"]
            assert actual == expected
