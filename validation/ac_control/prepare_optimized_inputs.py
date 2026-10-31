"""Prepare the final three input profiles, including the full shared columnar table.

Use this entry point for a new run. The original optimized_all_models_protocol
remains unchanged because its inference helpers were frozen in the live runs.
"""

import argparse
import json
from pathlib import Path

from all_models_protocol import digest, save, stamp
from compact_input_protocol import BASELINE
from full_context_input import compact_full_context
from optimized_all_models_protocol import prepare


def prepare_final(root):
    prepare(root)
    target = root / "profiles/schema_once"
    cases = json.loads((BASELINE / "cases.json").read_text())
    save(target / "cases.json", [
        {**case, "payload": compact_full_context(case["payload"])} for case in cases
    ])
    source = Path(__file__).with_name("full_context_input.py")
    (root / source.name).write_bytes(source.read_bytes())
    plan = json.loads((target / "plan.json").read_text())
    plan.update(
        prepared_at=stamp(),
        input_encoding="columnar_full_state_v2",
        prompt="Complete shared capability table in columnar form; concise questions; no answer repair.",
        preparation_source_sha256={source.name: digest(source)},
    )
    plan["input_sha256"]["cases.json"] = digest(target / "cases.json")
    save(target / "plan.json", plan)
    overall = json.loads((root / "plan.json").read_text())
    overall.update(
        preparation_entrypoint=Path(__file__).name,
        preparation_entrypoint_sha256=digest(Path(__file__)),
        schema_once_encoding="columnar_full_state_v2",
        prepared_at=stamp(),
    )
    save(root / "plan.json", overall)
    return root


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True, help="New, nonexistent output directory")
    print(prepare_final(parser.parse_args().run))
