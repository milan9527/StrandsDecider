"""Pin and stage public model artifacts through private S3 for an offline GPU."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path

import boto3
import requests
from boto3.s3.transfer import TransferConfig

ROOT = Path(__file__).resolve().parents[2]
BUCKET = "strands-decider-tetris-training-632930644527"
PREFIX = "open-decision-models-20261029"
MODELS = {
    "liquid": ("LiquidAI/d1-2B", "cfe5760ff5d5998f91d9ac56bd4b2dbd96996d41"),
    "pplx": ("perplexity-ai/pplx-decider-flash-v1.2", "9ff7cf9838e59df461c276b7699d56b244d2af58"),
    "knowline": ("PelaAI/KnowLine-4B-Gen5.5", "779944d2cc8ffa19cef386aee83c83bcb967ade2"),
    "h2o": ("h2oai/h2o-lightning-4b", "2240c9eb666a45ac6c566808a0a9ca84dbe9809b"),
}


class HashedStream:
    def __init__(self, stream):
        self.stream, self.sha, self.size = stream, hashlib.sha256(), 0

    def read(self, n=-1):
        data = self.stream.read(n)
        self.sha.update(data)
        self.size += len(data)
        return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=MODELS, required=True)
    args = parser.parse_args()
    repo, revision = MODELS[args.model]
    s3 = boto3.client("s3", region_name="us-east-1")
    manifest_path = ROOT / ".deployment" / f"open-model-{args.model}-manifest.json"
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    cached = {r["path"]: r for r in previous.get("files", [])} if previous.get("revision") == revision else {}
    meta = requests.get(f"https://huggingface.co/api/models/{repo}/revision/{revision}", timeout=30)
    meta.raise_for_status()
    selected = [
        row["rfilename"] for row in meta.json()["siblings"]
        if not row["rfilename"].startswith(("assets/", "docs/", ".git"))
        and row["rfilename"].endswith((".py", ".json", ".safetensors", ".txt", ".sh", ".md",
                                      ".patch", ".jinja", ".lightning", ".toml", ".typed",
                                      "SHA256SUMS", "LICENSE", "NOTICE"))
    ]

    def upload(name):
        key = f"{PREFIX}/models/{args.model}/{name}"
        url = f"https://huggingface.co/{repo}/resolve/{revision}/{name}"
        try:
            obj = s3.head_object(Bucket=BUCKET, Key=key)
            if name in cached and obj["ContentLength"] == cached[name]["bytes"]:
                return cached[name]
            if obj["Metadata"].get("revision") == revision and obj["Metadata"].get("sha256"):
                return {"path": name, "key": key, "bytes": obj["ContentLength"],
                        "sha256": obj["Metadata"]["sha256"]}
        except s3.exceptions.ClientError as exc:
            if exc.response["Error"]["Code"] not in ("404", "NoSuchKey"):
                raise
        with requests.get(url, stream=True, timeout=(20, 180)) as response:
            response.raise_for_status()
            response.raw.decode_content = True
            source = HashedStream(response.raw)
            s3.upload_fileobj(source, BUCKET, key,
                             ExtraArgs={"ServerSideEncryption": "AES256"},
                             Config=TransferConfig(multipart_chunksize=16 * 1024**2,
                                                   max_concurrency=2))
            sha = source.sha.hexdigest()
        # Metadata is informational; the receiving GPU independently hashes the bytes.
        record = {"path": name, "key": key, "bytes": source.size, "sha256": sha}
        print(json.dumps({"model": args.model, **record}), flush=True)
        return record

    manifest = {"model": repo, "revision": revision, "bucket": BUCKET,
                "decoded_http_content": True, "files": []}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(upload, name) for name in selected]
        for future in concurrent.futures.as_completed(futures):
            manifest["files"].append(future.result())
            manifest_path.write_text(json.dumps(manifest, indent=2))
    manifest["complete"] = True
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(json.dumps({"complete": True, "model": repo, "files": len(manifest["files"]),
                      "bytes": sum(x["bytes"] for x in manifest["files"])}))


if __name__ == "__main__":
    main()
