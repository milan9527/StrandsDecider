from decimal import Decimal

from prepare import build_cases, catalogue, estimate_cost, payload, reference, sha
from run import grade


def test_frozen_case_count_payload_separation_and_order():
    cases = build_cases()
    assert len(cases) == 32
    assert len({c["id"] for c in cases}) == 32
    for case in cases:
        first = payload(case, "original_order")
        reverse = payload(case, "reversed_order")
        assert first["state"] == reverse["state"]
        assert sha(first) != sha(reverse)
        assert case["expected"] in first["questions"]["decision"]["criteria"]
        assert '"reference":' not in first["state"]
        assert '"expected":' not in first["state"]
        assert '"hard_eligible":' not in first["state"]
        assert (
            first["questions"]["decision"]["criteria"]
            == reverse["questions"]["decision"]["criteria"]
        )
        assert len(first["state"]) <= 12000
        assert all(len(v) <= 1000 for v in first["questions"]["decision"]["criteria"].values())


def test_independent_price_arithmetic_and_tier_boundary():
    models = catalogue()
    assert estimate_cost(
        models["m2"], {"input_tokens": 10000, "reserved_output_tokens": 1000}
    ) == Decimal("0.00098")
    assert estimate_cost(
        models["m4"], {"input_tokens": 1000, "reserved_output_tokens": 10000}
    ) == Decimal("0.00259375")
    assert estimate_cost(
        models["m6"], {"input_tokens": 300000, "reserved_output_tokens": 1000}
    ) == Decimal("0.765")


def test_soft_latency_does_not_turn_into_hard_rejection():
    case = next(c for c in build_cases() if c["id"] == "latency-soft-unmet")
    assert case["reference"]["hard_eligible"] == list(catalogue())
    assert case["expected"] == "m1"


def test_fallback_disabled_rejects_healthy_alternatives():
    case = next(c for c in build_cases() if c["id"] == "fallback-disabled")
    assert case["expected"] == "no_route"
    assert case["reference"]["hard_eligible"] == []
    request = dict(case["state"]["request"], fallback_allowed=True)
    models = catalogue()
    models["m5"]["fixture_status"] = "down"
    assert reference(models, request)["expected"] == "m1"


def test_wrong_choices_are_graded_without_repair():
    case = next(c for c in build_cases() if c["id"] == "cost-one-fits")
    response = {
        "provider": "jev",
        "status": "ok",
        "choice": "m4",
        "elapsed_ms": 10,
        "input_sha256": "test",
    }
    scored = grade(case, response, "original_order")
    assert not scored["correct"] and scored["choice"] == "m4"
    assert scored["violated_hard_constraints"] == ["over_budget"]
