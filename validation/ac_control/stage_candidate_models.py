"""Stage pinned public candidate artifacts in a temporary private S3 prefix."""

import concurrent.futures
import hashlib
import json
from pathlib import Path

import boto3
import requests
from boto3.s3.transfer import TransferConfig

BUCKET = "strands-decider-vllm-632930644527"
PREFIX = "input/ac-candidates/2026-10-30-l4-v1/models"
ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / ".deployment/ac-model-candidates/model-manifests"
MODELS = {
    "pplx": ("perplexity-ai/pplx-decider-flash-v1.2", "9ff7cf9838e59df461c276b7699d56b244d2af58"),
    "knowline": ("PelaAI/KnowLine-4B-Gen5.5", "779944d2cc8ffa19cef386aee83c83bcb967ade2"),
    "torchcast": ("torchcast-ai/torchcast-decision-4b", "492bfb19662f3c6e601cc9c4bd2911ac95609ed4"),
    "clef": ("Cloudflare/clef-flash", "f0b7d3cd65296abfe459e6c228b618f5d8b26d2f"),
    "h2o": ("h2oai/h2o-lightning-4b", "2240c9eb666a45ac6c566808a0a9ca84dbe9809b"),
}


class Stream:
    def __init__(self, source):
        self.source, self.digest, self.size = source, hashlib.sha256(), 0

    def read(self, size=-1):
        data = self.source.read(size)
        self.digest.update(data)
        self.size += len(data)
        return data


def stage(name):
    repo, revision = MODELS[name]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / (name + ".json")
    if path.exists() and json.loads(path.read_text()).get("complete"):
        print(name, "already staged", flush=True)
        return
    previous_path = ROOT / ".deployment" / ("open-model-" + name + "-manifest.json")
    previous = json.loads(previous_path.read_text()) if previous_path.exists() else {}
    cached = {x["path"]: x for x in previous.get("files", [])} if previous.get("revision") == revision else {}
    response = requests.get(f"https://huggingface.co/api/models/{repo}/revision/{revision}", timeout=30)
    response.raise_for_status()
    files = [x["rfilename"] for x in response.json()["siblings"]
             if not x["rfilename"].startswith(("assets/", "docs/", ".git", ".eval_results/"))
             and (x["rfilename"].endswith((".py", ".json", ".safetensors", ".txt", ".sh", ".md",
                                          ".patch", ".jinja", ".lightning", ".toml", ".typed",
                                          "SHA256SUMS", "LICENSE", "NOTICE"))
                  or Path(x["rfilename"]).name.startswith("LICENSE"))]
    s3 = boto3.client("s3", region_name="us-east-1")

    def transfer(filename):
        key = PREFIX + "/" + name + "/" + filename
        if filename in cached:
            old = cached[filename]
            try:
                s3.head_object(Bucket=previous["bucket"], Key=old["key"])
            except s3.exceptions.ClientError as error:
                if error.response["Error"]["Code"] not in ("404", "NoSuchKey"):
                    raise
            else:
                s3.copy({"Bucket": previous["bucket"], "Key": old["key"]}, BUCKET, key,
                        ExtraArgs={"ServerSideEncryption": "AES256"},
                        Config=TransferConfig(max_concurrency=2))
                return {**old, "key": key, "source": "existing pinned artifact"}
        url = f"https://huggingface.co/{repo}/resolve/{revision}/{filename}"
        with requests.get(url, stream=True, timeout=(30, 300)) as result:
            result.raise_for_status()
            result.raw.decode_content = True
            source = Stream(result.raw)
            s3.upload_fileobj(source, BUCKET, key, ExtraArgs={"ServerSideEncryption": "AES256"},
                             Config=TransferConfig(multipart_chunksize=16 * 1024**2, max_concurrency=2))
        if filename in cached:
            assert source.size == cached[filename]["bytes"]
            assert source.digest.hexdigest() == cached[filename]["sha256"]
        return {"path": filename, "key": key, "bytes": source.size,
                "sha256": source.digest.hexdigest(), "source": url}

    manifest = {"model": repo, "revision": revision, "bucket": BUCKET, "files": []}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for record in pool.map(transfer, files):
            manifest["files"].append(record)
            path.write_text(json.dumps(manifest, indent=2) + "\n")
            print(name, record["path"], record["bytes"], flush=True)
    manifest["complete"] = True
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    s3.put_object(Bucket=BUCKET, Key=PREFIX + "/" + name + "/manifest.json",
                  Body=path.read_bytes(), ServerSideEncryption="AES256")
    print(name, "complete", len(files), flush=True)


if __name__ == "__main__":
    import sys
    for name in sys.argv[1:] or MODELS:
        stage(name)
