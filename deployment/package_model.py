"""Stage pinned upstream snapshots, dereferencing HF cache links for Docker COPY."""

import json
import shutil
from pathlib import Path

from huggingface_hub import snapshot_download

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / ".deployment" / "models"
SNAPSHOTS = {
    "decider": (
        "StrandsAgents/strands-decider-2B-hobson-v19",
        "bb282d786bc251fd4e3068de3ada9ddbb38127cd",
    ),
    "base": ("Qwen/Qwen3.5-2B-Base", "b1485b2fa6dfa1287294f269f5fb618e03d52d7c"),
}


def main():
    MODELS.mkdir(parents=True, exist_ok=True)
    for name, (repo, revision) in SNAPSHOTS.items():
        destination = MODELS / name
        marker = destination / ".packaged-revision"
        if marker.exists() and marker.read_text() == revision:
            print(f"{name}: already packaged at {revision}", flush=True)
            continue
        source = snapshot_download(
            repo,
            revision=revision,
            allow_patterns=["*.json", "*.safetensors", "*.jinja", "*.txt", "*.md", "lora/*"],
            ignore_patterns=["eval/*", "history.json", "train_config.json"],
        )
        shutil.copytree(source, destination, dirs_exist_ok=True, symlinks=False)
        if name == "decider":
            config_path = destination / "hobson_config.json"
            original = json.loads(config_path.read_text())
            config = {**original, "base_model": "/opt/models/base", "base_revision": None}
            config_path.write_text(json.dumps(config, indent=2) + "\n")
            (destination / "packaging.json").write_text(
                json.dumps(
                    {
                        "source": repo,
                        "revision": revision,
                        "original_config": original,
                        "change": "Only relocate base_model to the packaged directory for offline loading.",
                    },
                    indent=2,
                )
                + "\n"
            )
        marker.write_text(revision)
        print(f"{name}: packaged {repo}@{revision}", flush=True)


if __name__ == "__main__":
    main()
