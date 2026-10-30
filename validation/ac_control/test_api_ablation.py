"""Check transport effort, lossless inputs, and strict rejection of malformed choices."""

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from api_ablation_protocol import (  # noqa: E402
    GPT_MODEL,
    decode_gpt,
    decode_jev,
    gpt_request,
    jev_request,
)


def payload():
    return json.loads((Path(__file__).parent / "runs/2026-10-30-v1/requests.json").read_text())[0]["payload"]


def test_provider_transports_preserve_complete_task_and_low_effort():
    task = payload()
    gpt = gpt_request(task)
    assert json.loads(gpt["messages"][0]["content"][0]["text"]) == task
    assert gpt["modelId"] == GPT_MODEL
    assert gpt["additionalModelRequestFields"] == {"reasoning": {"effort": "low"}}
    assert len(task["questions"]) == 30
    assert len(task["questions"]["t_dr_mode"]["criteria"]) == 102
    jev = jev_request(task)
    assert {k: v for k, v in jev.items() if k != "model"} == task


def test_gpt_requires_complete_string_choices_and_does_not_repair_answers():
    task = payload()
    answer = {"answers": dict.fromkeys(task["questions"], "omit")}
    response = {"stopReason": "end_turn", "output": {"message": {"content": [
        {"text": json.dumps(answer)},
    ]}}}
    assert set(decode_gpt(response, task).values()) == {"omit"}
    wrong = copy.deepcopy(response)
    wrong["stopReason"] = "max_tokens"
    with pytest.raises(ValueError, match="end_turn"):
        decode_gpt(wrong, task)
    answer["answers"]["t_temp"] = 24  # Candidate IDs are strings: no coercion.
    response["output"]["message"]["content"][0]["text"] = json.dumps(answer)
    with pytest.raises(ValueError, match="candidate"):
        decode_gpt(response, task)
    del answer["answers"]["t_temp"]
    response["output"]["message"]["content"][0]["text"] = json.dumps(answer)
    with pytest.raises(ValueError, match="question IDs"):
        decode_gpt(response, task)


def test_jev_version_pin_and_native_choice_membership():
    task = payload()
    response = {"model": "jev-1.14.0", "answers": {
        k: {"type": "choice", "choice": "omit"} for k in task["questions"]
    }}
    assert len(decode_jev(response, task, "jev-1.14.0")) == 30
    with pytest.raises(ValueError, match="version"):
        decode_jev(response, task, "jev-1.15.0")
    response["answers"]["t_temp"]["choice"] = "33"
    with pytest.raises(ValueError, match="candidate"):
        decode_jev(response, task, "jev-1.14.0")
