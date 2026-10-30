"""Verify retained evidence, then remove only this run's temporary S3 transfers."""

import hashlib
import json
from datetime import UTC, datetime

import boto3
from remote_candidates import BUCKET, PREFIX, ROOT


def cleanup():
    root = ROOT
    assert json.loads((root / "audit.json").read_text())["passed"]
    assert not (root / "transfer_cleanup.json").exists()
    s3 = boto3.client("s3", region_name="us-east-1")
    assert s3.get_bucket_versioning(Bucket=BUCKET).get("Status") is None
    prefix_out = "output/" + PREFIX + "/"
    objects = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=prefix_out):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            local = root / key.removeprefix(prefix_out)
            data = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
            assert local.read_bytes() == data, "Evidence differs: " + key
            objects.append({"key": key, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                            "verification": "byte-identical local evidence"})
    expected = {}
    inventory = json.loads((root / "logs/final-inventory.json").read_text())
    for path in (root / "model-manifests").glob("*.json"):
        manifest = json.loads(path.read_text())
        assert inventory["models"][path.stem]["manifest_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        for item in manifest["files"]:
            expected[item["key"]] = {"bytes": item["bytes"], "sha256": item["sha256"],
                                     "verification": "Public pinned artifact: streamed SHA-256 at upload, "
                                                     "independent full SHA-256 on GPU before inference; GPU copy retained."}
        expected["input/" + PREFIX + "/models/" + path.stem + "/manifest.json"] = {
            "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "local": path, "verification": "byte-identical local manifest"}
    transfer = json.loads((root / "source-transfer.json").read_text())
    archive = root.parents[3] / ".deployment/ac-model-candidates/test-input.tar.gz"
    expected[transfer["key"]] = {
        "bytes": archive.stat().st_size, "sha256": transfer["archive_sha256"], "local": archive,
        "verification": "byte-identical frozen input archive"}
    # Optional read-only final inventory helper, staged separately after model testing.
    source = root / "analysis_sources/candidate_final_inventory.py"
    expected["input/" + PREFIX + "/final-inventory.py"] = {
        "bytes": source.stat().st_size, "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "local": source, "verification": "byte-identical inventory helper"}
    seen = set()
    prefix_in = "input/" + PREFIX + "/"
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=prefix_in):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            item = expected[key]
            assert obj["Size"] == item["bytes"]
            if "local" in item:
                data = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
                assert data == item["local"].read_bytes()
                assert hashlib.sha256(data).hexdigest() == item["sha256"]
            objects.append({"key": key, **{k: v for k, v in item.items() if k != "local"}})
            seen.add(key)
    assert seen == set(expected), "Unexpected or missing input transfer objects"
    verification = {"verified_at": datetime.now(UTC).isoformat(), "bucket": BUCKET,
                    "prefixes": [prefix_in, prefix_out], "objects": objects}
    (root / "transfer_verification.json").write_text(json.dumps(verification, indent=2) + "\n")
    for index in range(0, len(objects), 1000):
        response = s3.delete_objects(Bucket=BUCKET, Delete={
            "Objects": [{"Key": item["key"]} for item in objects[index:index + 1000]], "Quiet": True})
        assert not response.get("Errors"), response
    assert all(s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix)["KeyCount"] == 0
               for prefix in (prefix_in, prefix_out))
    result = {"finished_at": datetime.now(UTC).isoformat(), "deleted_objects": len(objects),
              "prefixes_empty": True, "local_evidence_and_gpu_model_files_retained": True}
    (root / "transfer_cleanup.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    print(json.dumps(cleanup(), indent=2))
