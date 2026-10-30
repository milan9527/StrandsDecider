"""Retrieve the evidence archive without exposing any private download manifests."""
import io
import tarfile
from pathlib import Path

import boto3

ROOT = Path(__file__).parent
s3 = boto3.client("s3", region_name="us-east-1")
response = s3.get_object(Bucket="strands-decider-tetris-training-632930644527",
                         Key="open-decision-models-20261029/evidence/gpu-results.tar.gz")
with tarfile.open(fileobj=io.BytesIO(response["Body"].read()), mode="r:gz") as archive:
    count = 0
    for member in archive.getmembers():
        if not member.isfile():
            continue
        target = member.name if member.name.startswith(("results/", "environment-", "initial_shared_gpu/")) else "logs/" + member.name
        destination = (ROOT / target).resolve()
        if not destination.is_relative_to(ROOT.resolve()):
            raise ValueError("Evidence archive path escapes validation directory")
        data = archive.extractfile(member).read()
        if destination.exists() and destination.read_bytes() != data and target.endswith("-quality.jsonl"):
            raise ValueError("A completed quality evidence file changed: " + target)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        count += 1
print("Retrieved", count, "evidence files; snapshot", response["LastModified"])
