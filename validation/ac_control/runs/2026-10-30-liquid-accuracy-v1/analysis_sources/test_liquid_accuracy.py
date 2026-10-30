"""Check candidate coverage, protocol mapping, and model-driven selection."""

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from liquid_ac_client import MODEL, decide  # noqa: E402
from liquid_ac_protocol import decode_commands, prepare_strategy, second_stage  # noqa: E402


def base():
    return json.loads((Path(__file__).parent / "runs/2026-10-30-v1/requests.json").read_text())[4]["payload"]


@pytest.mark.parametrize("strategy", ["baseline", "two_stage", "semantic_gate", "temperature_bundle", "bundle_examples"])
def test_all_capabilities_and_unrelated_values_survive(strategy):
    original = base()
    prepared = prepare_strategy(original, strategy)
    for part in ("first", "values"):
        if prepared[part]:
            state = json.loads(prepared[part]["state"])
            assert state["commandSet"] == json.loads(original["state"])["commandSet"]
            assert state["query"] == json.loads(original["state"])["query"]
    values = prepared["values"] or prepared["first"]
    assert set(values["questions"]["t_dr_mode"]["criteria"]) == set(original["questions"]["t_dr_mode"]["criteria"])
    assert set(values["questions"]["t_auto_defrost_clean"]["criteria"]) == {"omit", "0", "1"}


def test_temperature_candidates_cover_all_values_and_map_units_without_reading_query():
    original = base()
    prepared = prepare_strategy(original, "temperature_bundle")
    for key, unit in (("t_temp", "0"), ("t_temp_f", "1")):
        for value in original["questions"][key]["criteria"]:
            if value == "omit":
                continue
            commands = decode_commands(original, prepared, {"temperature_action": key + ":" + value})
            assert {row["cmdKey"]: row["cmdValue"] for row in commands} == {key: value, "t_temp_type": unit}
    # The wrong model choice is retained; no extraction of the true request or answer.
    assert decode_commands(original, prepared, {"t_dr_mode": "42"}) == [{"cmdKey": "t_dr_mode", "cmdValue": "42"}]
    assert decode_commands(original, prepared, {"temperature_action": "unit:1"}) == [{"cmdKey": "t_temp_type", "cmdValue": "1"}]


def test_review_is_forwarded_but_stage_two_can_omit():
    original = base()
    prepared = prepare_strategy(original, "semantic_gate")
    selected = dict.fromkeys(prepared["first"]["questions"], "omit")
    selected.update(t_temp="apply", t_power="review")
    second = second_stage(prepared, selected)
    assert set(second["questions"]) == {"t_temp", "t_power"}
    assert "omit" in second["questions"]["t_power"]["criteria"]
    assert decode_commands(original, prepared, {"t_temp": "24", "t_power": "omit"}) == [
        {"cmdKey": "t_temp", "cmdValue": "24"}
    ]  # Original-key strategy does not silently fill a missing unit.


def test_reverse_order_does_not_change_action_meaning():
    original = base()
    reversed_base = copy.deepcopy(original)
    for question in reversed_base["questions"].values():
        question["criteria"] = dict(reversed(list(question["criteria"].items())))
    normal = prepare_strategy(original, "temperature_bundle")
    reversed_ = prepare_strategy(reversed_base, "temperature_bundle")
    assert normal["mapping"] == reversed_["mapping"]
    for stage in ("first", "values"):
        for key in normal[stage]["questions"]:
            assert list(normal[stage]["questions"][key]["criteria"]) == list(
                reversed(list(reversed_[stage]["questions"][key]["criteria"])))


def test_empty_gate_skips_value_call_and_invalid_answer_is_visible():
    calls = []

    def transport(url, payload, headers):
        calls.append(payload)
        response = {"model": MODEL, "answers": {
            key: {"type": "choice", "choice": "omit"} for key in payload["questions"]
        }}
        return {"status": "ok", "http_status": 200, "response": response,
                "response_text": json.dumps(response), "client_ms": 1}

    result = decide(base(), "temperature_bundle", transport=transport)
    assert result["status"] == "ok" and result["commands"] == [] and len(calls) == 1

    def invalid(url, payload, headers):
        result = transport(url, payload, headers)
        result["response"]["model"] = "wrong-model"
        return result

    result = decide(base(), "temperature_bundle", transport=invalid)
    assert result["status"] == "error" and result["commands"] == []
    assert result["stages"][0]["response"]["model"] == "wrong-model"


def test_no_query_dependent_candidate_pruning():
    original = base()
    changed = copy.deepcopy(original)
    state = json.loads(changed["state"])
    state["query"] = "Set the target temperature to 35 degrees Celsius."
    changed["state"] = json.dumps(state)
    first = prepare_strategy(original, "bundle_examples")
    second = prepare_strategy(changed, "bundle_examples")
    assert first["first"]["questions"] == second["first"]["questions"]
    assert first["values"]["questions"] == second["values"]["questions"]
    assert first["mapping"] == second["mapping"]
