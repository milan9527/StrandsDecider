import hashlib
import json
import tarfile

import pytest

from validation.ac_control.liquid_lora import manual


def test_prepare_exports_training_labels_but_not_test_references(tmp_path):
    root = tmp_path / "new-run"
    result = manual.prepare(root)
    assert result["runtime_sha256"] == manual.digest(root / "runtime-input.tar.gz")
    with tarfile.open(root / "runtime-input.tar.gz") as archive:
        assert set(archive.getnames()) == set(manual.RUNTIME_FILES)
        assert len(json.load(archive.extractfile("train.json"))) == 1024
        assert len(json.load(archive.extractfile("dev.json"))) == 96
        heldout = json.load(archive.extractfile("test-inputs.json"))
        assert len(heldout) == 192
        assert all(set(row) == {"id", "query", "language"} for row in heldout)
    assert len(manual.read(root / "test.json")) == 192
    with pytest.raises(FileExistsError):
        manual.prepare(root)


def release_fixture(tmp_path, monkeypatch):
    root = tmp_path / "run"
    (root / "training").mkdir(parents=True)
    (root / "evaluation").mkdir()
    adapter = root / "training/adapter-512.pt"
    adapter.write_bytes(b"test checkpoint")
    for name in ("worker.py", "evaluate.py"):
        (root / name).write_text("# fixture source\n")
    selected = {"path": adapter.name, "sha256": manual.digest(adapter)}
    manual.save(root / "training/selection.json", {"selected": selected})
    manual.save(root / "audit.json", {
        "passed": True, "interface_errors": 0,
        "selected_adapter_sha256_verified": selected["sha256"],
    })
    manual.save(root / "summary.json", {"adopted": True, "conditions": {"quality": True}})
    manual.save(root / "evaluation/server.json", {
        "selected": selected, "weight_sha256": "base-fixture-sha",
        "worker_sha256": manual.digest(root / "worker.py"),
        "server_sha256": manual.digest(root / "evaluate.py"),
    })
    monkeypatch.setattr(manual, "verify_model", lambda _: {"weight_sha256": "base-fixture-sha"})
    return root, adapter


def test_release_uses_the_selected_checkpoint_and_pins_both_services(tmp_path, monkeypatch):
    root, adapter = release_fixture(tmp_path, monkeypatch)
    target = tmp_path / "release"
    result = manual.release(root, tmp_path / "model", target)
    expected = hashlib.sha256(adapter.read_bytes()).hexdigest()
    assert result["adapter_sha256"] == expected
    assert result["selected_checkpoint"] == "adapter-512.pt"
    assert (target / "training/adapter.pt").read_bytes() == adapter.read_bytes()
    for name in ("server.py", "gateway.py"):
        text = (target / name).read_text()
        assert expected in text
        assert "2a87384a624545021fc6ca91cf5406ed42e518a8607f048ca264048f57a0d171" not in text
        compile(text, name, "exec")
    with pytest.raises(FileExistsError):
        manual.release(root, tmp_path / "model", target)


def test_failed_gate_or_tampered_adapter_cannot_create_release(tmp_path, monkeypatch):
    root, adapter = release_fixture(tmp_path, monkeypatch)
    target = tmp_path / "release"
    manual.save(root / "summary.json", {"adopted": False, "conditions": {"quality": False}})
    with pytest.raises(ValueError, match="gates"):
        manual.release(root, tmp_path / "model", target)
    assert not target.exists()
    adapter.write_bytes(b"changed")
    with pytest.raises(ValueError, match="digest mismatch"):
        manual.release(root, tmp_path / "model", target)
    assert not target.exists()


def test_checkpoint_cannot_escape_training_directory(tmp_path):
    with pytest.raises(ValueError):
        manual.checked_child(tmp_path, "../adapter.pt")
    path = tmp_path / "adapter.pt"
    path.symlink_to(tmp_path / "elsewhere.pt")
    with pytest.raises(ValueError):
        manual.checked_child(tmp_path, path.name)
