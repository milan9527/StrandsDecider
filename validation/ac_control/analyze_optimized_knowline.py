"""Verify KnowLine's actual scoring prompts for the three input profiles on CPU."""

import argparse
import json
from pathlib import Path

import analyze_knowline_layout as original
from all_models_protocol import digest, save
from optimized_all_models_protocol import ROOT, business_payload


def analyze(root, tokenizer):
    results = {}
    original.business_payload = business_payload
    for profile in ("baseline", "compact_catalog", "schema_once"):
        original.ROOT = root / "profiles" / profile
        original.analyze(tokenizer)
        path = original.ROOT / "knowline-layout-analysis.json"
        record = json.loads(path.read_text())
        record["input_profile"] = profile
        record["profile_adapter_sha256"] = digest(Path(__file__))
        save(path, record)
        results[profile] = {
            key: value for key, value in record.items() if key not in ("rows", "S04_example")
        }
    save(root / "knowline-input-layout-analysis.json", results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=ROOT)
    parser.add_argument("--tokenizer", type=Path, default=Path("/tmp/ac-nine-knowline-tokenizer"))
    args = parser.parse_args()
    analyze(args.run, args.tokenizer)
