"""Verify factor isolation and prevent gold-guided routing/scoring."""

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from ablation_protocol import gate_payload, make_payload, selected_payload  # noqa: E402
from analyze import grade  # noqa: E402
from analyze_ablation import complete_unit, decode_receipt  # noqa: E402
from prepare import sha  # noqa: E402
from run_ablation import choices  # noqa: E402


def base():
    return json.loads((Path(__file__).parent / "runs/2026-10-30-v1/requests.json").read_text())[4]["payload"]


def test_factor_isolation_and_all_legal_candidates():
    original = base()
    conditional = make_payload(original, "criteria_only")
    assert conditional["state"] == original["state"]
    rules = make_payload(original, "rules_only")
    for field in ("query", "commandSet"):
        assert json.loads(rules["state"])[field] == json.loads(original["state"])[field]
    for key, question in original["questions"].items():
        assert conditional["questions"][key]["instructions"] == question["instructions"]
        assert list(conditional["questions"][key]["criteria"]) == list(question["criteria"])
        assert rules["questions"][key]["criteria"] == question["criteria"]
    assert len(conditional["questions"]["t_dr_mode"]["criteria"]) == 102
    assert set(conditional["questions"]["t_auto_defrost_clean"]["criteria"]) == {"omit", "0", "1"}


def test_gate_has_full_catalog_and_stage_two_is_selected_by_model():
    combined = make_payload(base(), "combined")
    gate = gate_payload(combined)
    assert len(gate["questions"]) == 30
    assert gate["state"] == combined["state"]
    selected = dict.fromkeys(gate["questions"], "omit")
    assert selected_payload(combined, selected) is None
    selected["t_dr_mode"] = "apply"  # Not requested in S03: no reference-based filtering.
    second = selected_payload(combined, selected)
    assert second["state"] == combined["state"]
    assert list(second["questions"]) == ["t_dr_mode"]
    assert second["questions"]["t_dr_mode"] == combined["questions"]["t_dr_mode"]
    assert list(gate_payload(combined, True)["questions"]["t_power"]["criteria"]) == ["apply", "omit"]


def test_missing_unit_stays_wrong_in_raw_metric_and_conflicts_are_not_repaired():
    catalog = {c["key"]: c for c in json.loads(base()["state"])["commandSet"]}
    actual = [{"cmdName": catalog["t_temp"]["name"], "cmdKey": "t_temp", "cmdValue": "24"}]
    expected = complete_unit(actual, catalog)
    assert not grade(expected, actual)["correct"]
    assert grade(expected, complete_unit(actual, catalog))["correct"]
    wrong = actual + [{"cmdName": catalog["t_temp_type"]["name"], "cmdKey": "t_temp_type", "cmdValue": "1"}]
    assert complete_unit(wrong, catalog) == wrong


def test_decode_rejects_wrong_model_or_choice_and_missing_second_stage():
    payload = gate_payload(make_payload(base(), "combined"))
    response = {"model": "test", "answers": {
        k: {"type": "choice", "choice": "omit"} for k in payload["questions"]
    }}
    with pytest.raises(ValueError, match="identity"):
        choices(response, payload, "other")
    response["answers"]["t_power"]["choice"] = "1"
    with pytest.raises(ValueError, match="candidate"):
        choices(response, payload, "test")
    response["model"] = "LiquidAI/d1-2B"
    response["answers"]["t_power"]["choice"] = "apply"
    stage = {
        "payload": payload, "input_sha256": sha(payload), "response": response,
        "response_text": json.dumps(response), "status": "ok",
        "choices": choices(response, payload, response["model"]),
    }
    experiment = {"first_payload": payload, "arm": "two_stage",
                  "value_payload": make_payload(base(), "combined")}
    with pytest.raises(ValueError, match="Missing required value stage"):
        decode_receipt({"stages": [stage]}, experiment, {}, {}, "liquid")
    changed = copy.deepcopy(stage)
    changed["payload"]["state"] = "{}"
    with pytest.raises(ValueError, match="payload differs"):
        decode_receipt({"stages": [changed]}, experiment, {}, {}, "liquid")
