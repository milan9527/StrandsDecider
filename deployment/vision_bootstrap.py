"""Install offline dependencies in a dedicated environment and start the image service."""

import os
import subprocess
from pathlib import Path

ROOT = Path("/srv/vision")
python = ROOT / "venv/bin/python"
if not (ROOT / ".installed").exists():
    subprocess.run(["python", "-m", "venv", "--system-site-packages", str(ROOT / "venv")], check=True)
    subprocess.run([
        str(python), "-m", "pip", "install", "--disable-pip-version-check", "--no-index",
        "--find-links", str(ROOT / "wheels"), "transformers==5.18.0", "pillow==12.2.0",
    ], check=True)
    (ROOT / ".installed").touch()
for name in ("triton", "cuda"):
    directory = ROOT / name
    directory.mkdir(exist_ok=True)
    os.chown(directory, 10001, 10001)
os.environ.update({
    "PYTHONPATH": str(ROOT / "upstream"), "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
    "TOKENIZERS_PARALLELISM": "false", "OMP_NUM_THREADS": "2",
    "TRITON_CACHE_DIR": str(ROOT / "triton"), "CUDA_CACHE_PATH": str(ROOT / "cuda"),
})
os.setgid(10001)
os.setuid(10001)
os.execv(str(python), [str(python), "-u", str(ROOT / "vision_server.py")])
