"""Tests for evidence separation, complete inputs, and strict error accounting."""

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from analyze import decode, grade, summarize  # noqa: E402
from prepare import OMIT, payload, read_spec  # noqa: E402


def test_complete_capabilities_no_references_and_only_order_changes():
    capabilities, cases = read_spec()
    for case in cases:
        original = payload(case["query"], capabilities)
        reversed_ = payload(case["query"], capabilities, True)
        state = json.loads(original["state"])
        assert set(state) == {"query", "deviceTypeCode", "commandSet", "rules"}
        assert state["query"] == case["query"]
        assert state["commandSet"] == capabilities["commandSet"]
        assert len(original["questions"]) == 30
        assert original == reversed_  # dict equality ignores candidate order
        for key, question in original["questions"].items():
            assert list(question["criteria"]) == list(reversed(reversed_["questions"][key]["criteria"]))
        for command in capabilities["commandSet"]:
            criteria = original["questions"][command["key"]]["criteria"]
            if command["type"] == "range":
                assert set(criteria) - {OMIT} == {
                    str(n) for n in range(command["min"], command["max"] + 1)
                }
            else:
                assert set(criteria) - {OMIT} == set(
                    command.get("userControllableValues", command["options"])
                )


def test_order_and_number_representation_do_not_change_scoring():
    expected = [{"cmdKey": "t_temp", "cmdValue": "24"}, {"cmdKey": "t_temp_type", "cmdValue": "0"}]
    actual = [{"cmdKey": "t_temp_type", "cmdValue": 0}, {"cmdKey": "t_temp", "cmdValue": 24}]
    assert grade(expected, actual)["correct"]


def test_wrong_value_counts_as_missing_and_extra_without_hiding_key_correctness():
    expected = [{"cmdKey": "t_fan_speed", "cmdValue": "9"}]
    actual = [{"cmdKey": "t_fan_speed", "cmdValue": "7"}]
    scored = grade(expected, actual)
    assert not scored["correct"] and scored["keys_correct"]
    assert scored["correct_keys"] == 1 and scored["correct_pairs"] == 0
    assert scored["missing"] == [("t_fan_speed", "9")]
    assert scored["extra"] == [("t_fan_speed", "7")]


def test_decoder_does_not_complete_unit_or_remove_extra_power():
    capabilities, cases = read_spec()
    request = payload(cases[2]["query"], capabilities)
    response = {
        "model": "strands-decider-2B-hobson-v19-vllm",
        "answers": {k: {"type": "choice", "choice": OMIT} for k in request["questions"]},
    }
    response["answers"]["t_temp"]["choice"] = "24"
    response["answers"]["t_power"]["choice"] = "1"
    commands, _ = decode(response, request, capabilities)
    assert {c["cmdKey"] for c in commands} == {"t_temp", "t_power"}
    scored = grade(cases[2]["expected"], commands)
    assert not scored["correct"]
    assert scored["missing_keys"] == ["t_temp_type"]
    assert scored["extra_keys"] == ["t_power"]
    broken = copy.deepcopy(response)
    broken["answers"]["t_auto_defrost_clean"]["choice"] = "2"
    with pytest.raises(ValueError, match="outside supplied"):
        decode(broken, request, capabilities)
    del broken["answers"]["t_auto_defrost_clean"]
    with pytest.raises(ValueError, match="exactly"):
        decode(broken, request, capabilities)


def test_failures_stay_in_denominator():
    expected = [{"cmdKey": "t_power", "cmdValue": "1"}]
    row = {
        **grade(expected, [], "http_error"),
        "status": "http_error", "category": "single", "client_ms": 50,
    }
    summary = summarize([row])
    assert summary["exact_match"] == {"numerator": 0, "denominator": 1, "rate": 0}
    assert summary["missing_command_rate"]["rate"] == 1
    assert summary["errors"] == 1
