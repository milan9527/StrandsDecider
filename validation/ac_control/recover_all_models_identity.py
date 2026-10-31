"""Continue after KnowLine's zero-call health alias mismatch, without replaying results."""

import json

from all_models_infra import collect, status
from all_models_protocol import PROVIDERS, ROOT, digest, save, stamp
from continue_all_models import note, wait_operation
from prepare_all_models_runtime import benchmark, launch


def recover():
    controller = ROOT / "gpu-controller-tokyo.json"
    previous = json.loads(controller.read_text())
    assert previous["status"] == "failed" and previous["provider"] == "knowline"
    assert previous["phase"] == "benchmark"
    assert status("archive-knowline-zero-call-identity-failure")["Status"] == "Success"
    archived = json.loads((ROOT / "attempts/knowline-health-alias/attempt.json").read_text())
    assert archived["decision_calls"] == archived["formal_calls"] == archived["warmup_calls"] == 0
    amendment = ROOT / "infrastructure/knowline-identity-amendment.json"
    assert not amendment.exists(), "Recovery is explicit and must not replay itself"
    for provider in PROVIDERS[:5]:
        meta = json.loads((ROOT / "results" / provider / "run.json").read_text())
        assert meta["status"] in ("complete", "complete_with_errors") and meta["calls"] == 2049
    save(ROOT / "gpu-controller-tokyo-health-alias-failure.json", previous)
    save(amendment, {
        "recorded_at": stamp(), "previous_controller": previous,
        "reason": "Official /health reports configured alias m; the uniform runner requires repository identity.",
        "change": "Both KnowLine --served-model-name arguments now use PelaAI/KnowLine-4B-Gen5.5.",
        "routing_and_health_identity_only": True, "business_inputs_unchanged": True,
        "model_weights_and_code_unchanged": True, "inference_parameters_unchanged": True,
        "prior_decision_calls": 0, "prior_attempt": "attempts/knowline-health-alias/",
        "inference_runner_sha256": digest(ROOT / "sources/run_all_models.py"),
        "deployment_helper_sha256": digest(ROOT.parents[1] / "prepare_all_models_runtime.py"),
    })
    state = dict(previous, status="running", phase="launch", resumed_at=stamp(),
                 recovery="knowline-routing-identity")
    state.pop("error", None)
    state.pop("error_type", None)
    save(controller, state)
    try:
        for provider in PROVIDERS[5:]:
            attempt = "nine-models-identity" if provider == "knowline" else "nine-models"
            state.update(phase="launch", provider=provider)
            save(controller, state)
            note(launch=launch(provider, attempt))
            wait_operation("start-" + provider + "-" + attempt)
            state["phase"] = "benchmark"
            save(controller, state)
            note(benchmark=benchmark(provider, attempt))
            wait_operation("benchmark-" + provider + "-" + attempt)
            collect()
            meta = json.loads((ROOT / "results" / provider / "run.json").read_text())
            assert meta["status"] in ("complete", "complete_with_errors") and meta["calls"] == 2049
            note(provider=provider, calls=meta["calls"], errors=meta["errors"], status=meta["status"])
        state.update(status="complete", phase="finished")
    except BaseException as error:
        state.update(status="failed", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        state["updated_at"] = stamp()
        save(controller, state)
    from finish_all_models import finish
    finish()


if __name__ == "__main__":
    recover()
