import json
from pathlib import Path

import pytest
from h2o_ac_client import MODEL, decide, request
from prepare import payload
from prepare_h2o_official import VALIDATION

HERE = Path(__file__).resolve().parent
CATALOG = json.loads((HERE / "runs/2026-10-30-v1/command_set.json").read_text())


@pytest.mark.parametrize("profile", ["baseline", "rules_only"])
@pytest.mark.parametrize("reverse", [False, True])
def test_all_capabilities_candidates_and_order_preserved(profile, reverse):
    base = payload("Set the temperature to 21 degrees Celsius.", CATALOG, reverse)
    result = request(base, profile, "causal")
    assert json.loads(result["state"])["commandSet"] == CATALOG["commandSet"]
    assert len(result["questions"]) == 30
    for key, question in base["questions"].items():
        assert result["questions"][key]["criteria"] == question["criteria"]
        assert list(result["questions"][key]["criteria"]) == list(question["criteria"])
    assert len(result["questions"]["t_dr_mode"]["criteria"]) == 102
    assert set(result["questions"]["t_auto_defrost_clean"]["criteria"]) == {"omit", "0", "1"}


def test_does_not_fill_unit_or_remove_unrelated_model_action():
    task = request(payload("Set the temperature to 21 degrees Celsius.", CATALOG), "rules_only", "causal")

    def transport(url, sent, headers):
        selected = dict.fromkeys(sent["questions"], "omit") | {"t_temp": "21", "t_dr_mode": "42"}
        return {"status": "ok", "client_ms": 1, "response": {
            "model": MODEL, "attention_mode": "causal",
            "answers": {key: {"type": "choice", "choice": value} for key, value in selected.items()},
        }}

    result = decide(task, transport=transport)
    assert result["commands"] == [
        {"cmdKey": "t_temp", "cmdValue": "21"}, {"cmdKey": "t_dr_mode", "cmdValue": "42"}]


def test_wrong_mode_is_failure_not_silent_fallback():
    task = request(payload("Turn on power.", CATALOG), attention="causal")
    result = decide(task, transport=lambda *_: {
        "status": "ok", "client_ms": 1, "response": {"model": MODEL, "attention_mode": "bidirectional"}})
    assert result["status"] == "format_error" and result["commands"] == []


def test_validation_labels_are_legal():
    assert len(VALIDATION) == 24 and len({row[0] for row in VALIDATION}) == 24
    for _, query, expected in VALIDATION:
        task = payload(query, CATALOG)
        assert all(value in task["questions"][key]["criteria"] for key, value in expected.items())
