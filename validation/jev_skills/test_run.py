import copy
import json

import httpx
import pytest

from validation.jev_skills.run import (
    assess,
    collect,
    digest,
    load_cases,
    run_pairs,
    summarize,
    validate_raw,
)


def case():
    return next(c for c in load_cases()[2] if c["id"] == "jev-documents--example")


def response(item):
    return {
        "model": "test-model",
        "source": "live",
        "answers": {
            name: {
                "type": "choice", "choice": expected, "confidence": 0.9,
                "probabilities": {
                    label: float(label == expected)
                    for label in item["payload"]["questions"][name]["criteria"]
                },
            }
            for name, expected in item["expected"].items()
        },
    }


def test_frozen_catalog_and_three_types():
    source, _, cases = load_cases()
    assert len(source["scenarios"]) == 108
    assert len(cases) == 32
    assert len({c["skill"] for c in cases}) == 5
    assert {q["type"] for c in cases for q in c["payload"]["questions"].values()} == {
        "choice", "noul", "score",
    }
    for c in cases:
        assert set(c["payload"]) == {"state", "questions"}
        assert c["input_sha256"] == digest(c["payload"])


@pytest.mark.parametrize("fault", ["missing", "invalid_label", "nan", "bool", "sum", "extra"])
def test_invalid_model_answers_are_not_decisions(fault):
    item = case()
    raw = response(item)
    answer = raw["answers"]["source"]
    if fault == "missing":
        del raw["answers"]["claim_support"]
    elif fault == "invalid_label":
        answer["choice"] = "invented"
    elif fault == "nan":
        answer["confidence"] = float("nan")
    elif fault == "bool":
        answer["probabilities"]["s2"] = True
    elif fault == "sum":
        answer["probabilities"]["s2"] = 0.2
    elif fault == "extra":
        answer["probabilities"]["invented"] = 0
    with pytest.raises(ValueError):
        validate_raw(raw, item["payload"])


def test_failed_call_is_retained_without_retry_or_rule_fallback():
    calls = []

    def timeout(payload):
        calls.append(payload)
        raise httpx.ReadTimeout("do not log this token-like error")

    result = collect("jev", case(), timeout)
    assert len(calls) == 1
    assert result["status"] == "error"
    assert result["error_type"] == "ReadTimeout"
    assert "judgments" not in result
    assert "token-like" not in json.dumps(result)


def test_paired_payloads_are_identical_and_expectations_are_not_sent():
    item = case()
    seen = {"jev": [], "decider": []}

    def invoke(provider):
        def call(payload):
            seen[provider].append(copy.deepcopy(payload))
            payload["state"] = "Mutating one worker must not affect the other."
            return response(item)
        return call

    receipts = []
    rows = run_pairs([item], {p: invoke(p) for p in seen}, 2, receipts.append)
    assert rows == receipts
    assert seen["jev"] == seen["decider"] == [item["payload"], item["payload"]]
    assert all(set(p) == {"state", "questions"} for p in seen["jev"])
    assert all(row["input_sha256"] == item["input_sha256"] for row in rows)
    assert summarize([item], rows, 2)["pairing"]["valid_identical_input_pairs"] == 2


def test_partial_failure_keeps_other_model_and_planned_denominators():
    item = case()

    def invalid(_):
        return {"model": "test-model", "answers": {}}

    rows = run_pairs([item], {"jev": invalid, "decider": lambda _: response(item)}, 1, lambda _: None)
    summary = summarize([item], rows, 1)
    assert summary["jev"]["all"]["reference_questions"] == 2
    assert summary["jev"]["all"]["matches_reference"] == 0
    assert summary["jev"]["all"]["failed_calls"] == 1
    assert summary["decider"]["all"]["matches_reference"] == 2
    assert summary["pairing"]["valid_identical_input_pairs"] == 0
    assert rows[0]["providers"]["jev"]["invalid_response"]["answers"] == {}


def test_noul_false_is_not_a_failed_request_and_half_is_unresolved():
    item = next(c for c in load_cases()[2] if c["id"] == "jev--completion")
    raw = {"answers": {
        "claim_supported": {"type": "noul", "noul": 0.1},
        "next_step": {"type": "choice", "choice": "check_job"},
    }}
    assert assess(item, raw)["claim_supported"]["matches_reference"] is True
    raw["answers"]["claim_supported"]["noul"] = 0.5
    assert assess(item, raw)["claim_supported"]["matches_reference"] is False


def test_score_uses_continuous_rubric_value_not_a_probability():
    item = next(c for c in load_cases()[2] if c["id"] == "jev-triage--example")
    raw = {"answers": {
        "queue": {"type": "choice", "choice": "bug"},
        "urgency": {"type": "score", "score": 1.49},
    }}
    assert assess(item, raw)["urgency"]["matches_reference"] is True
    raw["answers"]["urgency"]["score"] = 1.51
    assert assess(item, raw)["urgency"]["matches_reference"] is False


def test_example_replay_is_rejected_as_live_decider():
    item = case()
    raw = response(item)
    raw["source"] = "example"
    assert collect("decider", item, lambda _: raw)["status"] == "error"


def test_summary_is_identical_after_receipt_json_round_trip():
    item = case()
    raw = response(item)
    raw["answers"]["source"]["choice"] = "s1"
    raw["answers"]["claim_support"]["choice"] = "supported"
    rows = run_pairs([item], {"jev": lambda _: raw, "decider": lambda _: raw}, 1, lambda _: None)
    restored = json.loads(json.dumps(rows, sort_keys=True))
    assert summarize([item], rows, 1) == summarize([item], restored, 1)
