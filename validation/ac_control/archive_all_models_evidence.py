"""Losslessly compress completed raw receipts after the complete nine-model audit."""

import gzip
import hashlib
import json

from all_models_protocol import PROVIDERS, ROOT, digest, save, stamp


def archive():
    audit = json.loads((ROOT / "audit.json").read_text())
    assert audit["passed"] and tuple(audit["providers"]) == PROVIDERS and audit["observed_calls"] == 18441
    manifest = ROOT / "receipt-archive.json"
    assert not manifest.exists(), "Archive manifest already exists"
    entries = {}
    for provider in PROVIDERS:
        folder = ROOT / "results" / provider
        meta = json.loads((folder / "run.json").read_text())
        assert meta["status"] in ("complete", "complete_with_errors") and meta["calls"] == 2049
        plain = folder / "receipts.jsonl"
        target = plain.with_suffix(".jsonl.gz")
        assert not target.exists()
        original = plain.read_bytes()
        checksum = hashlib.sha256(original).hexdigest()
        assert checksum == audit["evidence"][provider]["receipts_sha256"]
        compressed = gzip.compress(original, compresslevel=9, mtime=0)
        target.write_bytes(compressed)
        assert gzip.decompress(target.read_bytes()) == original
        entries[provider] = {
            "raw_bytes": len(original), "raw_sha256": checksum,
            "gzip_bytes": len(compressed), "gzip_sha256": digest(target),
            "roundtrip_byte_identical": True, "path": str(target.relative_to(ROOT)),
        }
    # Every archive is verified before removing any generated uncompressed copy.
    save(manifest, {"archived_at": stamp(), "lossless": True, "providers": entries})
    for provider in PROVIDERS:
        (ROOT / "results" / provider / "receipts.jsonl").unlink()
    return entries


if __name__ == "__main__":
    print(json.dumps(archive(), indent=2))
