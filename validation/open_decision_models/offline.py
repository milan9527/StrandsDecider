"""Download a presigned private manifest and verify every artifact on the GPU."""
import concurrent.futures
import hashlib
import json
import sys
import urllib.request
from pathlib import Path


def main():
    manifest = json.loads(Path(sys.argv[1]).read_text())
    root = Path(sys.argv[2]).resolve()
    root.mkdir(parents=True, exist_ok=True)

    def download(row):
        path = (root / row["path"]).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Artifact path escapes its destination")
        if path.exists():
            with path.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() == row["sha256"]:
                    return
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + ".partial")
        sha = hashlib.sha256()
        with urllib.request.urlopen(row["url"], timeout=180) as response, temp.open("wb") as output:
            while chunk := response.read(8 * 1024**2):
                sha.update(chunk)
                output.write(chunk)
        if sha.hexdigest() != row["sha256"]:
            temp.unlink(missing_ok=True)
            raise ValueError("Artifact hash mismatch: " + row["path"])
        temp.replace(path)
        print(json.dumps({"downloaded": row["path"], "bytes": path.stat().st_size}), flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(download, manifest["files"]))
    print(json.dumps({"verified_files": len(manifest["files"])}), flush=True)


if __name__ == "__main__":
    main()
