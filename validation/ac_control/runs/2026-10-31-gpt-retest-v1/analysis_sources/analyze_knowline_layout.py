"""Reconstruct KnowLine prompts on CPU and compare token counts with recorded responses."""

import argparse
import gzip
import hashlib
import importlib.metadata
import json
import platform
import sys
from pathlib import Path

from all_models_protocol import ROOT, business_payload, digest, save, stamp


def analyze(tokenizer_path):
    versions = {p: importlib.metadata.version(p) for p in ("transformers", "tokenizers", "jinja2")}
    assert versions == {"transformers": "5.12.1", "tokenizers": "0.22.2", "jinja2": "3.1.6"}
    from transformers import AutoTokenizer

    source = ROOT / "runtime_sources/knowline"
    for manifest_name in ("provenance.json", "tokenizer-provenance.json"):
        manifest = json.loads((source / manifest_name).read_text())
        for entry in manifest["files"]:
            path = (tokenizer_path if manifest_name.startswith("tokenizer") else source) / entry["path"]
            assert digest(path) == entry["sha256"]
    sys.path.insert(0, str(source))
    from knowline_layout import Layout, render_request
    from knowline_server import find_labels, render

    tokenizer = AutoTokenizer.from_pretrained(tokenizer_path, local_files_only=True)
    _, probe, _ = render(tokenizer, "x", {"q": {"type": "noul"}}, ["A", "B"])
    labels, _ = find_labels(tokenizer, probe["q"][0])
    health = json.loads((ROOT / "results/knowline/health_before.json").read_text())
    layout = Layout(**health["response"]["layout"])
    cases = [c for c in json.loads((ROOT / "cases.json").read_text())
             if c["dataset"] == "spec" and c["order"] == "original"]
    receipt_path = ROOT / "results/knowline/receipts.jsonl"
    raw = (receipt_path.read_bytes() if receipt_path.exists()
           else gzip.decompress(receipt_path.with_suffix(".jsonl.gz").read_bytes()))
    rows = [json.loads(line) for line in raw.splitlines()]
    observations = {(r["case_id"], r["field"], r["repetition"]): r for r in rows
                    if r["kind"] in ("full30", "serial30")}
    checked, example = [], {}
    for case in cases:
        for key in (None, *case["payload"]["questions"]):
            payload = business_payload(case, key)
            rendered = render_request(payload, tokenizer, layout, labels=labels)
            prompts = {qid: rendered["prompts"][qid][0][0] for qid in payload["questions"]}
            count = sum(len(tokenizer.encode(text, add_special_tokens=False)) for text in prompts.values())
            observed = observations[case["case_id"], key, 0]
            actual = [observations[case["case_id"], key, repetition]["response"]["usage"]["input_tokens"]
                      for repetition in range(3)]
            assert all(count == n for n in actual), (case["case_id"], key, count, actual)
            checked.append({
                "case_id": case["case_id"], "field": key, "read_twice": rendered["twice"],
                "once_tokens_for_request_gate": rendered["once_tokens"],
                "scoring_prompt_tokens": count, "recorded_input_tokens": actual,
                "prompt_sha256": {qid: hashlib.sha256(text.encode()).hexdigest() for qid, text in prompts.items()},
            })
            if case["case_id"] == "S04" and key in (None, "t_temp"):
                example["full30" if key is None else "single"] = {
                    "read_twice": rendered["twice"], "once_tokens_for_request_gate": rendered["once_tokens"],
                    "t_temp_prompt": prompts["t_temp"], "actual_t_temp_choice": observed["choices"]["t_temp"],
                }
    assert len(checked) == 620
    result = {
        "analyzed_at": stamp(), "python": platform.python_version(), "packages": versions,
        "model_inference_calls": 0, "cpu_tokenization_only": True,
        "all_reconstructed_counts_match_recorded_usage": True,
        "matched_actual_requests": len(observations),
        "cases_sha256": digest(ROOT / "cases.json"),
        "receipts_sha256": hashlib.sha256(raw).hexdigest(),
        "full30_read_twice": sum(r["field"] is None and r["read_twice"] for r in checked),
        "single_read_twice": sum(r["field"] is not None and r["read_twice"] for r in checked),
        "checked_layouts": len(checked), "rows": checked, "S04_example": example,
        "analyzer_sha256": digest(Path(__file__)),
    }
    save(ROOT / "knowline-layout-analysis.json", result)
    print(json.dumps({k: v for k, v in result.items() if k not in ("rows", "S04_example")}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tokenizer", type=Path, default=Path("/tmp/ac-nine-knowline-tokenizer"))
    analyze(parser.parse_args().tokenizer)
