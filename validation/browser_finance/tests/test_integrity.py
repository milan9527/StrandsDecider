import json

import pytest

from browser import candidates, domain_allowed, payload_for
from common import digest, validate
from evaluate import correct_cfpb
from prepare import browser_tasks, finance_cases
from runner import finance_payload


def test_finance_reference_never_enters_model_payload_and_order_changes_hash():
    cases = finance_cases()
    assert len(cases) == 30
    for case in cases:
        first = finance_payload(case, "original_order")
        reverse = finance_payload(case, "reversed_order")
        assert json.loads(first["state"]) == case["state"]
        assert first["state"] == reverse["state"]
        assert (
            first["questions"]["decision"]["criteria"]
            == reverse["questions"]["decision"]["criteria"]
        )
        assert digest(first) != digest(reverse)
        assert "reference_basis" not in first["state"]
        assert "expected" not in json.loads(first["state"])
        assert case["expected"] in case["criteria"]


def test_candidates_only_allow_observed_controls_and_safe_domains():
    task = browser_tasks()[0]
    observation = {
        "controls": [
            {
                "index": i,
                "tag": "a",
                "label": f"link{i}",
                "href": f"https://en.wikipedia.org/wiki/Item{i}",
                "dismiss": False,
            }
            for i in range(40)
        ]
        + [
            {
                "index": 50,
                "tag": "a",
                "label": "evil",
                "href": "https://wikipedia.org.evil.example/",
                "dismiss": False,
            }
        ]
    }
    options, actions, offset, count = candidates(observation, task, 7)
    assert len(options) == 12
    assert count == 40 and offset == 7
    assert all(a["index"] in range(7, 14) for a in actions.values() if "index" in a)
    assert not domain_allowed("https://wikipedia.org.evil.example/", ["wikipedia.org"])
    assert not domain_allowed("javascript:alert(1)", ["wikipedia.org"])
    assert domain_allowed("https://en.wikipedia.org/wiki/Basel_III", ["wikipedia.org"])


def test_browser_verification_labels_not_given_to_model():
    task = browser_tasks()[-1]
    observation = {
        "url": task["start_url"],
        "title": "BankFind",
        "headings": [],
        "text": "Search form",
    }
    payload = payload_for(task, observation, {"wait": "Wait", "finish": "Finish"}, 0, 0, [])
    assert "628" not in payload["state"]
    assert "bank_detail_link" not in payload["state"]


def test_mock_or_wrong_model_cannot_count_as_live_decider():
    payload = {"questions": {"decision": {"criteria": {"a": "A", "b": "B"}}}}
    reply = {
        "source": "mock",
        "model": "strands-decider-2B",
        "answers": {
            "decision": {
                "type": "choice",
                "choice": "a",
                "confidence": 0.8,
                "probabilities": {"a": 0.8, "b": 0.2},
            }
        },
    }
    with pytest.raises(AssertionError):
        validate(reply, payload, "decider")
    reply["source"] = "live"
    assert validate(reply, payload, "decider") == "a"
    reply["answers"]["decision"]["choice"] = "c"
    with pytest.raises(AssertionError):
        validate(reply, payload, "decider")


def test_corrected_deadline_still_requires_real_destination_and_model_finish():
    expected = {
        "url_contains": "/dispute",
        "heading": "Dispute",
        "body_terms": ["60 calendar days", "written"],
    }
    run = {
        "steps": [{"action": {"kind": "finish"}, "status": "executed"}],
        "status": "premature_finish",
        "success": False,
        "goal_reached": False,
    }
    observation = {
        "url": "https://example.test/dispute",
        "headings": ["Dispute"],
        "text": "Send written notice within 60 calendar days.",
    }
    assert correct_cfpb(run, observation, expected)["success"]
    assert not run["success"]
    observation["url"] = "https://example.test/"
    assert not correct_cfpb(run, observation, expected)["success"]
    observation["url"] = "https://example.test/dispute"
    run["steps"] = []
    corrected = correct_cfpb(run, observation, expected)
    assert corrected["goal_reached"] and not corrected["success"]
