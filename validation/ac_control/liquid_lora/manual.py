"""Portable, local-only helpers for the EC2 LoRA handbook; no AWS mutations."""

import argparse
import hashlib
import json
import re
import shutil
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
REFERENCE = HERE.parent / "runs/2026-11-01-liquid-lora-v1"
REVISION = "cfe5760ff5d5998f91d9ac56bd4b2dbd96996d41"
RUNTIME_FILES = (
    "worker.py", "evaluate.py", "template.json", "train.json", "dev.json",
    "test-inputs.json", "historical-cases.json",
)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def checked_child(root, name):
    if not isinstance(name, str) or Path(name).name != name or name in ("", ".", ".."):
        raise ValueError("Checkpoint must be a filename inside training/")
    path = root / name
    if path.is_symlink():
        raise ValueError("Checkpoint symlinks are not accepted")
    return path


def prepare(root):
    """Use the frozen data; export no held-out or historical reference labels."""
    if root.exists():
        raise FileExistsError(f"Choose a new experiment directory: {root}")
    server = read(REFERENCE / "evaluation/server.json")
    for filename, key in (("worker.py", "worker_sha256"), ("evaluate.py", "server_sha256")):
        if digest(HERE / filename) != server[key]:
            raise ValueError(f"Frozen implementation changed: {filename}")
    root.mkdir(parents=True)
    for name in RUNTIME_FILES:
        shutil.copy2((HERE if name.endswith(".py") else REFERENCE) / name, root / name)
    for name in ("test.json", "historical-references.json", "split-limitations.json"):
        shutil.copy2(REFERENCE / name, root / name)
    save(root / "readme-before.json", {"README.md": digest(REPO / "README.md")})
    save(root / "experiment.json", {
        "model": "LiquidAI/d1-2B", "revision": REVISION,
        "dataset_source": str(REFERENCE.relative_to(REPO)),
        "files": {p.name: digest(p) for p in root.iterdir() if p.is_file()},
        "training": read(REFERENCE / "plan.json")["training"],
        "test_references_exported": False,
    })
    with tarfile.open(root / "runtime-input.tar.gz", "w:gz") as bundle:
        for name in RUNTIME_FILES:
            bundle.add(root / name, arcname=name)
    save(root / "runtime-input.json", {
        "sha256": digest(root / "runtime-input.tar.gz"),
        "files": {name: digest(root / name) for name in RUNTIME_FILES},
        "test_references_exported": False,
    })
    return {"directory": str(root), "runtime_files": list(RUNTIME_FILES),
            "runtime_sha256": digest(root / "runtime-input.tar.gz")}


def verify_model(model):
    """Check the weight and all custom Python sources against the tested revision."""
    expected = read(REFERENCE / "evaluation/server.json")
    hashes = {"model.safetensors": expected["weight_sha256"], **expected["model_source_sha256"]}
    for name, wanted in hashes.items():
        if digest(model / name) != wanted:
            raise ValueError(f"Model file differs from the tested revision: {name}")
    return {"revision": REVISION, "verified_files": len(hashes),
            "weight_sha256": hashes["model.safetensors"]}


def score(root):
    # Reuse the original accounting, but never regenerate its date-specific
    # report or overwrite docs/LIQUID_AC_LORA_RESULTS.md.
    import analyze as accounting

    accounting.ROOT = root
    accounting.report = lambda *args: None
    accounting.analyze()
    return {"summary": str(root / "summary.json"), "audit": str(root / "audit.json"),
            "adopted": read(root / "summary.json")["adopted"]}


def set_constant(source, name, value):
    text, count = re.subn(rf"^{name} = .+$", lambda _: f"{name} = {value}", source, flags=re.M)
    if count != 1:
        raise ValueError(f"Expected one constant: {name}")
    return text


def release(root, model, destination):
    """Create a new pinned service bundle; never modify the deployed service."""
    if destination.exists():
        raise FileExistsError(f"Release already exists: {destination}")
    selection = read(root / "training/selection.json")
    selected = selection["selected"]
    adapter = checked_child(root / "training", selected["path"])
    adapter_sha = digest(adapter)
    if adapter_sha != selected["sha256"]:
        raise ValueError("Selected checkpoint digest mismatch")
    audit, summary = read(root / "audit.json"), read(root / "summary.json")
    if (not audit["passed"] or audit["interface_errors"] != 0
            or audit["selected_adapter_sha256_verified"] != adapter_sha
            or not summary["adopted"] or not all(summary["conditions"].values())):
        raise ValueError("Evaluation gates did not pass; review the experiment")
    metadata = read(root / "evaluation/server.json")
    if metadata["selected"]["sha256"] != adapter_sha:
        raise ValueError("Evaluation used another adapter")
    for name, key in (("worker.py", "worker_sha256"), ("evaluate.py", "server_sha256")):
        if digest(root / name) != metadata[key]:
            raise ValueError(f"Evaluated source changed: {name}")
    model_check = verify_model(model)
    if model_check["weight_sha256"] != metadata["weight_sha256"]:
        raise ValueError("Evaluation used another base model")
    server = (REPO / "deployment/open_models/ac_lora_server.py").read_text()
    for name, value in {
        "ROOT": f"Path({str(destination)!r})", "MODEL": f"Path({str(model)!r})",
        "ADAPTER_SHA": repr(adapter_sha), "BASE_SHA": repr(model_check["weight_sha256"]),
        "WORKER_SHA": repr(digest(root / "worker.py")),
    }.items():
        server = set_constant(server, name, value)
    old_path = 'ROOT / "training/adapter-1024.pt"'
    if server.count(old_path) != 1:
        raise ValueError("Service template checkpoint path changed")
    server = server.replace(old_path, 'ROOT / "training/adapter.pt"')
    gateway = set_constant(
        (REPO / "deployment/open_models/ac_lora_gateway.py").read_text(),
        "ADAPTER", repr(adapter_sha),
    )
    compile(server, "server.py", "exec")
    compile(gateway, "gateway.py", "exec")
    (destination / "training").mkdir(parents=True)
    shutil.copy2(adapter, destination / "training/adapter.pt")
    shutil.copy2(root / "worker.py", destination / "worker.py")
    (destination / "server.py").write_text(server)
    (destination / "gateway.py").write_text(gateway)
    save(destination / "manifest.json", {
        "model": "LiquidAI/d1-2B", "revision": REVISION,
        "model_directory": str(model), "release_directory": str(destination),
        "adapter_sha256": adapter_sha,
        "base_sha256": model_check["weight_sha256"],
        "selected_checkpoint": selected["path"],
        "files": {name: digest(destination / name) for name in (
            "training/adapter.pt", "worker.py", "server.py", "gateway.py",
        )},
        "deployment_started": False,
    })
    return read(destination / "manifest.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "score"):
        commands.add_parser(name).add_argument("--run-dir", type=Path, required=True)
    commands.add_parser("verify-model").add_argument("--model-dir", type=Path, required=True)
    publish = commands.add_parser("release")
    for flag in ("run-dir", "model-dir", "release-dir"):
        publish.add_argument("--" + flag, type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.run_dir.resolve())
    elif args.command == "score":
        result = score(args.run_dir.resolve())
    elif args.command == "verify-model":
        result = verify_model(args.model_dir.resolve())
    else:
        result = release(args.run_dir.resolve(), args.model_dir.resolve(), args.release_dir.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
