"""Verify trial isolation and rollback without touching systemd or Docker."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "deployment/open_models/tune_h2o_runtime.py"
spec = importlib.util.spec_from_file_location("h2o_runtime_controller", SOURCE)
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


@pytest.fixture
def environment(tmp_path, monkeypatch):
    dropin = tmp_path / "systemd/90-ac-optimization.conf"
    calls = []
    original = (
        "[Service]\nExecStart=/usr/bin/docker run "
        '-e "VLLM_ARGS=--max-num-seqs 1 --enforce-eager --quantization fp8" '
        "-e VLLM_GDN_PREFILL_GRAPH_MAX_TOKENS=0 -e VLLM_GDN_PREFILL_GRAPH_PRECAPTURE=0 "
        "-e VLLM_CACHE_ROOT=/bench/h2o-cache image serve.sh\n"
    )
    healthy = {"ok": True, "model": "h2oai/h2o-lightning-4b", "attention_mode": "bidirectional"}

    def command(args, **kwargs):
        calls.append(args)
        stdout = original if args[:2] == ["systemctl", "cat"] else "protected unchanged"
        return {"returncode": 0, "stdout": stdout, "stderr": ""}

    monkeypatch.setattr(controller, "DROPIN", dropin)
    monkeypatch.setattr(controller, "command", command)
    monkeypatch.setattr(controller, "health", lambda: healthy)
    monkeypatch.setattr(controller, "wait_ready", lambda timeout: healthy)
    args = SimpleNamespace(root=tmp_path / "run", variant="seq2", sequences=2,
                           graphs="off", gdn_tokens=0, timeout=30)
    return args, dropin, calls, healthy


def test_trial_changes_only_h2o_and_keeps_fp8_and_bidirectional(environment):
    args, dropin, calls, _ = environment
    controller.configure(args)
    text = dropin.read_text()
    assert "--max-num-seqs 2 " in text
    assert "--enforce-eager" in text and "--quantization fp8" in text
    assert "ac-optimization-seq2" in text and "Restart=no" in text
    assert [c for c in calls if c[:2] == ["systemctl", "restart"]] == [
        ["systemctl", "restart", "decider-h2o"]
    ]
    assert any(c[0] == "systemd-run" for c in calls)


def test_failed_start_restores_original_configuration(environment, monkeypatch):
    args, dropin, calls, healthy = environment
    attempts = iter([TimeoutError("startup timeout"), healthy])

    def ready(timeout):
        result = next(attempts)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(controller, "wait_ready", ready)
    with pytest.raises(TimeoutError):
        controller.configure(args)
    assert not dropin.exists()
    assert (args.root / "rollback/restored.json").exists()
    result = json.loads((args.root / "runtime_trials/seq2/result.json").read_text())
    assert result["status"] == "failed" and result["rolled_back"]
    assert len([c for c in calls if c[:2] == ["systemctl", "restart"]]) == 2


def test_accept_restores_restart_policy_without_restarting(environment):
    args, dropin, calls, _ = environment
    controller.configure(args)
    calls.clear()
    controller.accept(args.root)
    assert "Restart=always" in dropin.read_text()
    assert not any(c[:2] == ["systemctl", "restart"] for c in calls)
    assert (args.root / "accepted_runtime.json").exists()


def test_gdn_graphs_can_be_enabled_without_changing_attention_or_general_eager_mode(environment):
    args, dropin, _, _ = environment
    args.gdn_tokens = 4096
    controller.configure(args)
    text = dropin.read_text()
    assert "VLLM_GDN_PREFILL_GRAPH_MAX_TOKENS=4096" in text
    assert "VLLM_GDN_PREFILL_GRAPH_MAX_SEQS=2" in text
    assert "VLLM_GDN_PREFILL_GRAPH_PRECAPTURE=1" in text
    assert "--enforce-eager" in text
    assert "SHIM_ATTENTION_MODE=causal" not in text


def test_general_graph_trial_limits_compilation_workers_and_keeps_gdn_disabled(environment):
    args, dropin, _, _ = environment
    args.graphs = "on"
    controller.configure(args)
    text = dropin.read_text()
    assert "--enforce-eager" not in text
    assert "TORCHINDUCTOR_COMPILE_THREADS=1" in text
    assert "VLLM_GDN_PREFILL_GRAPH_MAX_TOKENS=0" in text
    assert "--quantization fp8" in text
