"""Offline effect audit; nothing here is fed back into model requests."""
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1]))
from app.crypto import Snapshot, Transition, apply


def device_state(choices):
    state = {"power": "off", "temperature": "26", "mode": "heat", "clarify": False}
    for key, value in choices.items():
        if value == "clarify":
            state["clarify"] = True
        elif value != "unchanged":
            state[key] = value
    return state


def main():
    references = json.loads((ROOT / "references.json").read_text())
    parent = json.loads((ROOT.parent / "model_routing/plan-2026-10-13.json").read_text())
    routing = {"routing-" + row["id"]: row for row in parent["cases"]}
    details, summary = [], {}
    for path in sorted((ROOT / "results").glob("*-quality.jsonl")):
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        if not rows:
            continue
        stats = collections.Counter()
        provider = rows[0]["provider"]
        for row in rows:
            ref = references[row["case_id"]]
            detail = {k: row[k] for k in ["case_id", "variant", "provider", "group", "status"]}
            if row["group"] == "payment":
                reference_result = apply(Transition(snapshot=Snapshot(**ref["snapshot"]), stage=ref["stage"],
                                                    choice=ref["expected"]["action"]))
                stats["payment_reference_ledger_opportunities"] += reference_result["ledger_entry"] is not None
            if row["status"] != "ok":
                stats[row["group"] + "_failures"] += 1
                continue
            choices = row["choices"]
            if row["group"] == "payment":
                result = apply(Transition(snapshot=Snapshot(**ref["snapshot"]), stage=ref["stage"],
                                          choice=choices["action"]))
                stats["payment_valid"] += 1
                stats["payment_safety_adjustments"] += result["safety_adjusted"]
                stats["payment_simulated_ledger_entries"] += result["ledger_entry"] is not None
                detail.update({k: result[k] for k in ["requested_action", "action", "safety_adjusted",
                                                     "safety_reason", "external_action_executed"]})
                detail["simulated_ledger_entry"] = result["ledger_entry"]
                detail["reference_ledger_entry"] = reference_result["ledger_entry"]
                assert result["external_action_executed"] is False
            elif row["group"] == "routing":
                rule = routing[row["case_id"]]["reference"]
                if "hard_eligible" not in rule:
                    continue
                stats["routing_constraint_cases_valid"] += 1
                selected = choices["action"]
                if selected == ref["expected"]["action"]:
                    kind = "exact"
                elif selected in rule["hard_eligible"]:
                    kind = "eligible_but_not_preferred"
                elif selected == "no_route":
                    kind = "false_no_route"
                else:
                    kind = "hard_constraint_violation"
                stats["routing_" + kind] += 1
                detail.update(kind=kind, selected=selected,
                              reasons=rule.get("details", {}).get(selected, {}).get("ineligible_reasons", []))
            elif row["group"] == "device_control":
                actual, expected = device_state(choices), device_state(ref["expected"])
                stats["device_valid"] += 1
                stats["device_final_state_matches"] += actual == expected
                detail.update(actual_final_state=actual, expected_final_state=expected,
                              actions_match=choices == ref["expected"], final_state_matches=actual == expected)
            else:
                continue
            details.append(detail)
        summary[provider] = dict(stats)
    (ROOT / "results/business_audit.json").write_text(json.dumps(
        {"summary": summary, "details": details}, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
