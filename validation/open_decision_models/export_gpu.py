"""Upload only results, software metadata, and logs; never private manifests or weights."""
import json
import tarfile
import urllib.request
from pathlib import Path

root = Path("/bench")
archive = root / "evidence.tar.gz"
with tarfile.open(archive, "w:gz") as output:
    for pattern in ["results/*", "environment-*.json", "*-server.log", "*-trial.log",
                    "initial_shared_gpu/**/*", "setup/*"]:
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                output.add(path, arcname=str(path.relative_to(root)))
settings = json.loads((root / "export-private.json").read_text())
response = urllib.request.urlopen(
    urllib.request.Request(settings["url"], data=archive.read_bytes(), method="PUT"), timeout=120)
print("Exported evidence:", response.status, archive.stat().st_size, flush=True)
