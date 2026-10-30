"""Verify cross-model identity, unchanged inputs, and baseline scoring parity."""

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from compare_resident import MODEL_IDS, decode_model, read_rows  # noqa: E402

BASELINE = Path(__file__).parent / "runs/2026-10-30-v1"


def evidence():
    requests = json.loads((BASELINE / "requests.json").read_text())
    references = json.loads((BASELINE / "references.json").read_text())
    capabilities = json.loads((BASELINE / "command_set.json").read_text())
    return (
        {(r["case_id"], r["variant"]): r for r in requests},
        {r["id"]: r for r in references},
        capabilities,
    )


def test_shared_grading_reproduces_existing_decider_results():
    requests, references, capabilities = evidence()
    rows = read_rows(BASELINE / "formal_receipts.jsonl", "decider",
                     requests, references, capabilities)
    prior = json.loads((BASELINE / "results.json").read_text())
    for row, original in zip(rows, prior, strict=True):
        for key in ["case_id", "variant", "correct", "keys_correct", "cmdList",
                    "expected_count", "predicted_count", "correct_pairs", "correct_keys"]:
            assert row[key] == original[key]


def test_model_identity_and_invalid_choices_are_not_silently_repaired():
    requests, _, capabilities = evidence()
    request = requests["S03", "original"]["payload"]
    catalog = {c["key"]: c for c in capabilities["commandSet"]}
    response = {
        "model": MODEL_IDS["liquid"],
        "answers": {key: {"type": "choice", "choice": "omit"} for key in request["questions"]},
    }
    response["answers"]["t_temp"]["choice"] = "24"
    commands = decode_model(response, request, catalog, MODEL_IDS["liquid"])
    assert [(c["cmdKey"], c["cmdValue"]) for c in commands] == [("t_temp", "24")]
    with pytest.raises(ValueError, match="identity"):
        decode_model(response, request, catalog, MODEL_IDS["h2o"])
    response["answers"]["t_temp"]["choice"] = "33"
    with pytest.raises(ValueError, match="invalid candidate"):
        decode_model(response, request, catalog, MODEL_IDS["liquid"])


def test_timing_and_input_integrity_for_h2o(tmp_path):
    requests, references, capabilities = evidence()
    request = requests["S01", "original"]
    receipt = {
        "case_id": "S01", "variant": "original", "input_sha256": request["input_sha256"],
        "status": "ok", "client_ms": 701,
        "response": {
            "model": MODEL_IDS["h2o"], "usage": {"latency_ms": 699},
            "answers": {key: {"type": "choice", "choice": "omit"}
                        for key in request["payload"]["questions"]},
        },
    }
    receipt["response"]["answers"]["t_power"]["choice"] = "1"
    receipt["response_text"] = json.dumps(receipt["response"])
    path = tmp_path / "receipts.jsonl"
    path.write_text(json.dumps(receipt) + "\n")
    row = read_rows(path, "h2o", requests, references, capabilities, required_count=1)[0]
    assert row["correct"] and row["server_ms"] == 699 and row["client_ms"] == 701
    changed = copy.deepcopy(receipt)
    changed["input_sha256"] = "changed"
    path.write_text(json.dumps(changed) + "\n")
    with pytest.raises(ValueError, match="Input differs"):
        read_rows(path, "h2o", requests, references, capabilities, required_count=1)
