"""Columnar full-state capabilities for services that score fields independently."""

import copy
import json

from compact_input_protocol import NOTES, RULES
from optimized_all_models_protocol import portable_request
from prepare import wire

COLUMNS = ["key", "name", "type", "values"]
RANGE_COLUMNS = ["min", "max", "unit"]


def compact_full_context(baseline):
    # Same concise questions as compact_catalog. The extra compression comes only
    # from removing repeated metadata key names in the complete shared state.
    request = portable_request(baseline, "compact_catalog")
    state = json.loads(request["state"])
    commands = state["commandSet"]
    table = {
        "columns": COLUMNS,
        "rangeColumns": RANGE_COLUMNS,
        "rows": [
            [c["key"], c["name"], c["type"],
             copy.deepcopy(c["options"]) if c["type"] == "enum"
             else [c[name] for name in RANGE_COLUMNS]]
            for c in commands
        ],
        "userControllableValues": {
            c["key"]: c["userControllableValues"] for c in commands if "userControllableValues" in c
        },
    }
    state["commandSet"] = table
    request["state"] = wire(state)
    audit_full_context(baseline, request)
    return request


def catalog_from_columnar(request):
    state = json.loads(request["state"])
    table = state["commandSet"]
    assert table["columns"] == COLUMNS and table["rangeColumns"] == RANGE_COLUMNS
    commands = []
    for key, name, kind, values in table["rows"]:
        command = {"name": name, "key": key, "type": kind}
        if kind == "enum":
            command["options"] = copy.deepcopy(values)
        else:
            assert kind == "range" and len(values) == len(RANGE_COLUMNS)
            command.update(dict(zip(RANGE_COLUMNS, values)))
        if key in table["userControllableValues"]:
            command["userControllableValues"] = table["userControllableValues"][key]
        commands.append(command)
    return {"deviceTypeCode": state["deviceTypeCode"], "commandSet": commands}


def audit_full_context(baseline, request):
    original = json.loads(baseline["state"])
    state = json.loads(request["state"])
    assert state["query"] == original["query"]
    assert state["rules"] == original["rules"] == RULES
    assert catalog_from_columnar(request) == {
        "deviceTypeCode": original["deviceTypeCode"], "commandSet": original["commandSet"],
    }
    assert list(request["questions"]) == list(baseline["questions"])
    for key, question in request["questions"].items():
        assert question["type"] == "choice"
        assert NOTES[key] in question["instructions"]
        assert list(question["criteria"]) == list(baseline["questions"][key]["criteria"])
        assert all(isinstance(value, str) for value in question["criteria"].values())
    return True
