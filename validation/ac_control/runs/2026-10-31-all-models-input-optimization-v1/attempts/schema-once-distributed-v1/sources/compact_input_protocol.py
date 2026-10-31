"""Lossless AC capability representations for Clef; no inference or answer repair."""

import argparse
import ast
import copy
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from prepare import NOTES, RULES, SPEC, wire

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "runs/2026-10-30-all-models-full-v1"
MODEL_REVISION = "f0b7d3cd65296abfe459e6c228b618f5d8b26d2f"
CLEF_SOURCE = HERE.parent / "model_research/2026-10-30-ac-candidates/Cloudflare--clef-flash--joint_schema_model.py"
VARIANTS = ("baseline", "compact_catalog", "schema_once")


def catalog_from_request(request):
    """Recover all original capability metadata, including non-commandable states."""
    state = json.loads(request["state"])
    if "commandSet" in state:
        return {"deviceTypeCode": state["deviceTypeCode"], "commandSet": state["commandSet"]}
    commands = []
    for key, question in request["questions"].items():
        metadata = json.loads(question["instructions"])
        command = {"name": metadata["name"], "key": key, "type": metadata["type"]}
        if command["type"] == "range":
            command.update({name: metadata[name] for name in ("min", "max", "unit")})
        else:
            command["options"] = {
                value: label for value, label in question["criteria"].items() if value != "omit"
            }
            command["options"].update(metadata.get("statusOnly", {}))
            if "userControllableValues" in metadata:
                command["userControllableValues"] = metadata["userControllableValues"]
        commands.append(command)
    return {"deviceTypeCode": state["deviceTypeCode"], "commandSet": commands}


def compact_request(baseline, variant):
    """Use capabilities only; never inspect query text to select fields or values."""
    if variant not in VARIANTS:
        raise ValueError(f"Unknown variant: {variant}")
    request = copy.deepcopy(baseline)
    if variant == "baseline":
        return request
    state = json.loads(baseline["state"])
    commands = {command["key"]: command for command in state["commandSet"]}
    for key, question in request["questions"].items():
        command = commands[key]
        if variant == "compact_catalog":
            question["instructions"] = f"{command['name']}. {NOTES[key]}"
        else:
            metadata = {"name": command["name"], "type": command["type"], "note": NOTES[key]}
            if command["type"] == "range":
                metadata.update({name: command[name] for name in ("min", "max", "unit")})
            if "userControllableValues" in command:
                metadata["userControllableValues"] = command["userControllableValues"]
                metadata["statusOnly"] = {
                    value: label for value, label in command["options"].items()
                    if value not in command["userControllableValues"]
                }
            question["instructions"] = wire(metadata)
        for value in question["criteria"]:
            # Clef explicitly supports None descriptions. Numeric IDs remain in its
            # rendered schema; the unit/range remains in the complete capability map.
            question["criteria"][value] = (
                "No change." if value == "omit"
                else command["options"][value] if command["type"] == "enum"
                else None
            )
    if variant == "schema_once":
        del state["commandSet"]
        request["state"] = wire(state)
    return request


def single_field_request(full_request, key):
    """Keep the complete capability map even when asking only one field."""
    request = copy.deepcopy(full_request)
    state = json.loads(request["state"])
    if "commandSet" not in state:
        state.update(catalog_from_request(full_request))
        request["state"] = wire(state)
    request["questions"] = {key: request["questions"][key]}
    return request


def audit_request(baseline, candidate):
    original = json.loads(baseline["state"])
    state = json.loads(candidate["state"])
    assert state["query"] == original["query"]
    assert state["rules"] == original["rules"] == RULES
    assert catalog_from_request(candidate) == {
        "deviceTypeCode": original["deviceTypeCode"], "commandSet": original["commandSet"],
    }
    assert list(candidate["questions"]) == list(baseline["questions"])
    for key, question in candidate["questions"].items():
        assert question["type"] == "choice"
        assert list(question["criteria"]) == list(baseline["questions"][key]["criteria"])
        assert NOTES[key] in question["instructions"]
    return True


def load_clef_encoder(tokenizer_path):
    """Execute only the pinned release's text encoder; no torch/model/GPU required."""
    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file(str(tokenizer_path))
    cache = {}

    class Adapter:
        def __call__(self, text, **unused):
            if text not in cache:
                cache[text] = tokenizer.encode(text, add_special_tokens=False).ids
            # The official encoder extends lists in place.
            return SimpleNamespace(input_ids=list(cache[text]))

    definitions = {
        "render", "question_options", "_tokens", "_encode_media", "encode_record",
        "EncodedQuestion", "EncodedRecord",
    }
    constants = {
        "SYSTEM_PROMPT", "IMAGE_PLACEHOLDER", "VIDEO_PLACEHOLDER",
        "MEDIA_BATCH_KEYS", "MEDIA_TOKEN_KEYS", "QUESTION_TYPES",
    }
    tree = ast.parse(CLEF_SOURCE.read_text())
    selected = [
        node for node in tree.body
        if getattr(node, "name", None) in definitions
        or isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id in constants for target in node.targets)
    ]
    namespace = {"json": json, "dataclass": dataclass, "dataclass_field": field, "Any": Any}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(CLEF_SOURCE), "exec"), namespace)
    return lambda request: namespace["encode_record"](Adapter(), request)


def prepare(output, tokenizer_path):
    import gzip
    import statistics

    encoder = load_clef_encoder(tokenizer_path)
    cases = json.loads((BASELINE / "cases.json").read_text())
    output.mkdir(parents=True, exist_ok=False)
    samples = output / "examples"
    samples.mkdir()
    report = {
        "model": "Cloudflare/clef-flash", "revision": MODEL_REVISION,
        "inference_performed": False, "accuracy_measured": False, "latency_measured": False,
        "spec_sha256": hashlib.sha256(SPEC.read_bytes()).hexdigest(),
        "cases_sha256": hashlib.sha256((BASELINE / "cases.json").read_bytes()).hexdigest(),
        "tokenizer_sha256": hashlib.sha256(tokenizer_path.read_bytes()).hexdigest(),
        "encoder_sha256": hashlib.sha256(CLEF_SOURCE.read_bytes()).hexdigest(),
        "protocol_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "variants": {}, "verified_baseline_receipts": 0,
        "range_policy": "Keep all existing integer candidates; fractional inputs remain untested.",
    }
    with gzip.open(BASELINE / "results/clef/receipts.jsonl.gz", "rt") as stream:
        for line in stream:
            row = json.loads(line)
            assert len(encoder(row["payload"]).input_ids) == row["response"]["usage"]["input_tokens"]
            report["verified_baseline_receipts"] += 1
    for variant in VARIANTS:
        lengths = []
        primary = []
        single_lengths = []
        for case in cases:
            request = compact_request(case["payload"], variant)
            audit_request(case["payload"], request)
            encoded = encoder(request)
            # None is not removed by Clef: every numeric ID is still a scored option.
            assert all(
                set(question.option_ids) == set(request["questions"][question.question_id]["criteria"])
                for question in encoded.questions
            )
            lengths.append(len(encoded.input_ids))
            if case["dataset"] == "spec" and case["order"] == "original":
                primary.append(lengths[-1])
                for key in request["questions"]:
                    single = single_field_request(request, key)
                    assert catalog_from_request(single) == catalog_from_request(request)
                    single_lengths.append(len(encoder(single).input_ids))
                if case["case_id"] in ("S03", "M08", "M09"):
                    (samples / f"{case['case_id']}.{variant}.json").write_text(
                        json.dumps(request, ensure_ascii=False, indent=2) + "\n"
                    )
        report["variants"][variant] = {
            "audited_requests": len(cases), "full30_tokens_min": min(lengths),
            "full30_tokens_max": max(lengths), "spec_full30_tokens_mean": statistics.mean(primary),
            "single_field_tokens_mean": statistics.mean(single_lengths),
            "serial30_tokens_sum_mean": sum(single_lengths) / len(primary),
            "fields": len(request["questions"]),
            "candidates": sum(len(q["criteria"]) for q in request["questions"].values()),
            "s03_tokens": len(encoder(compact_request(
                next(c["payload"] for c in cases if c["case_id"] == "S03" and c["order"] == "original"),
                variant,
            )).input_ids),
        }
    (output / "analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.output, args.tokenizer)
