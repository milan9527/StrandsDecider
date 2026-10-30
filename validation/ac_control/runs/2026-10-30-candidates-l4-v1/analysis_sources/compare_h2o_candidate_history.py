"""Compare the same 30 H2O business inputs across the two recorded environments."""

import hashlib
import json
from pathlib import Path

from analyze import grade
from remote_candidates import ROOT


def compare():
    previous = ROOT.parent / "2026-10-30-h2o-official-v2/stages/development/receipts.jsonl"
    current = ROOT / "results/h2o/receipts.jsonl"
    old = [json.loads(line) for line in previous.read_text().splitlines()]
    old = [r for r in old if r["kind"] == "quality" and r["profile"] == "baseline"
           and r["attention"] == "bidirectional"]
    new = [json.loads(line) for line in current.read_text().splitlines()]
    new = {r["case_id"]: r for r in new if r["kind"] == "quality" and r["order"] == "original"}
    references = {r["id"]: r["expected"] for r in json.loads((ROOT / "references.json").read_text())}
    rows = []
    assert len(old) == 30
    for a in old:
        b = new[a["case_id"]]
        assert a["status"] == b["status"] == "ok"
        # The new runner additionally supplies the model ID; all business input is byte-identical.
        assert b["transport_request"] == {
            **a["transport_request"], "model": "h2oai/h2o-lightning-4b",
        }
        assert json.dumps(a["transport_request"]["questions"]) == json.dumps(
            b["transport_request"]["questions"])
        rows.append({
            "case_id": a["case_id"],
            "changed_fields": [k for k in a["choices"] if a["choices"][k] != b["choices"][k]],
            "previous_correct": grade(references[a["case_id"]], a["commands"])["correct"],
            "current_correct": grade(references[a["case_id"]], b["commands"])["correct"],
            "previous_commands": a["commands"], "current_commands": b["commands"],
        })
    result = {
        "previous_receipts_sha256": hashlib.sha256(previous.read_bytes()).hexdigest(),
        "current_receipts_sha256": hashlib.sha256(current.read_bytes()).hexdigest(),
        "same_state_questions_and_attention": True,
        "environment_note": "Different instance and process; same business input. "
                            "This comparison does not isolate the cause of any change.",
        "requests": len(rows), "changed_cases": sum(bool(r["changed_fields"]) for r in rows),
        "previous_correct": sum(r["previous_correct"] for r in rows),
        "current_correct": sum(r["current_correct"] for r in rows), "rows": rows,
    }
    (ROOT / "h2o-history-comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    target = ROOT / "analysis_sources" / Path(__file__).name
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(Path(__file__).read_bytes())
    return result


if __name__ == "__main__":
    print(json.dumps(compare(), ensure_ascii=False, indent=2))
