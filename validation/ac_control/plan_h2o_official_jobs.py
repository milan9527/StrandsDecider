"""Prepare post-selection jobs without modifying frozen prompts or validation data."""

import argparse
import json
from pathlib import Path

from prepare_h2o_official import item, job


def build(root, name, kind):
    cases = json.loads((root / "development_cases.json").read_text())
    original = [case for case in cases if case["order"] == "original"]
    s03 = next(case for case in original if case["case_id"] == "S03")
    if kind in ("restart_stability", "baseline_latency", "baseline_screen"):
        amendment = json.loads((root / "early_stop_amendment.json").read_text())
        assert amendment["graph_candidate_profile"] == "baseline"
        assert amendment["graph_candidate_attention"] == "bidirectional"
        tasks = [item(s03, "baseline", "bidirectional", kind="warmup")]
        for repetition in range(3):
            if kind == "restart_stability":
                tasks.extend(item(case, "baseline", "bidirectional", kind="repeatability",
                                  repetition=repetition) for case in original
                             if case["case_id"] in ("N03", "N09", "N10"))
            else:
                tasks.append(item(s03, "baseline", "bidirectional",
                                  kind="full30", repetition=repetition))
                if kind == "baseline_latency":
                    for key in s03["payload"]["questions"]:
                        row = item(s03, "baseline", "bidirectional",
                                   kind="serial30", repetition=repetition)
                        row["payload"]["questions"] = {key: row["payload"]["questions"][key]}
                        tasks.append(row)
        job(root, name, tasks)
        return
    if kind == "restart_check":
        selection = json.loads((root / "selection.json").read_text())
        arms = [("baseline", "bidirectional"), (selection["profile"], selection["attention"])]
        tasks = [item(s03, *arm, kind="warmup") for arm in arms]
        for index, case in enumerate(original):
            for arm in arms if index % 2 == 0 else list(reversed(arms)):
                tasks.append(item(case, *arm))
        for repetition in range(2):
            for case in original:
                if case["case_id"] in ("N03", "N09", "N10"):
                    tasks.append(item(case, "baseline", "bidirectional", kind="repeatability",
                                      repetition=repetition))
        job(root, name, tasks)
        return
    selection = json.loads((root / "selection.json").read_text())
    candidate = selection["profile"], selection["attention"]
    control = "baseline", "bidirectional"
    if kind in ("latency", "graph_screen"):
        tasks = [item(s03, *arm, kind="warmup") for arm in (control, candidate)]
        for repetition in range(3):
            for arm in ((control, candidate) if repetition % 2 == 0 else (candidate, control)):
                tasks.append(item(s03, *arm, kind="full30", repetition=repetition))
                if kind == "latency":
                    for key in s03["payload"]["questions"]:
                        row = item(s03, *arm, kind="serial30", repetition=repetition)
                        row["payload"]["questions"] = {key: row["payload"]["questions"][key]}
                        tasks.append(row)
        job(root, name, tasks)
    elif kind == "graph_quality":
        job(root, name, [item(s03, *candidate, kind="warmup")]
            + [item(case, *candidate) for case in original])
    elif kind == "validation":
        # Full known suite including reversal plus the independently held-back new suite.
        validation = json.loads((root / "validation_cases.json").read_text())
        tasks = [item(s03, *arm, kind="warmup") for arm in (control, candidate)]
        for index, case in enumerate(cases + validation):
            for arm in ((control, candidate) if index % 2 == 0 else (candidate, control)):
                tasks.append(item(case, *arm))
        job(root, name, tasks)
    else:
        raise ValueError(kind)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--kind", choices=("restart_check", "latency", "graph_screen",
                                         "graph_quality", "validation", "restart_stability",
                                         "baseline_latency", "baseline_screen"), required=True)
    args = parser.parse_args()
    build(args.run, args.name, args.kind)
