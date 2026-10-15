import json
from pathlib import Path

from prepare_natural import convert, describe


def test_natural_diagnostic_preserves_problem_and_reference():
    parent = json.loads(Path("plan-2026-10-13.json").read_text())
    converted = convert(parent)
    assert len(converted["cases"]) == 24 and converted["max_calls"] == 96
    original = {c["id"]: c for c in parent["cases"]}
    for case in converted["cases"]:
        source = original[case["id"]]
        assert case["state"] == source["state"]
        assert case["reference"] == source["reference"]
        assert case["expected"] == source["expected"]
        assert list(case["criteria"]) == list(source["criteria"])
        assert case["criteria"]["no_route"] == source["criteria"]["no_route"]
        for key in case["criteria"]:
            if key == "no_route":
                continue
            model = json.loads(source["criteria"][key])
            text = describe(model)
            assert model["model"] in text
            assert str(model["context_tokens"]) in text
            assert str(model["max_output_tokens"]) in text
            assert str(model["fixture_p50_latency_ms"]) in text
            assert model["fixture_status"] in text
            assert model["usd_per_million_input_tokens"] in text
            assert model["usd_per_million_output_tokens"] in text
            for value in model["input_modalities"] + model["output_modalities"] + model["supports"]:
                assert value in text
            assert "eligible" not in text
