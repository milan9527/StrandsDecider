"""Reusable Liquid AC client: retain raw choices and explicit protocol mappings."""

import argparse
import json
import time
from pathlib import Path

from liquid_ac_protocol import STRATEGIES, decode_commands, prepare_strategy, second_stage
from run_ablation import call, choices
from run_resident import save, sha, stamp

MODEL = "LiquidAI/d1-2B"


def decide(base, strategy, endpoint="http://127.0.0.1:18801", transport=call):
    prepared = prepare_strategy(base, strategy)
    result = {"strategy": strategy, "started_at": stamp(), "stages": [], "status": "ok"}
    started = time.perf_counter()
    payload = prepared["first"]
    selected = {}
    while payload is not None:
        phase = "gate" if prepared["values"] is not None and not result["stages"] else "value"
        stage = {"phase": phase, "payload": payload, "input_sha256": sha(payload),
                 "started_at": stamp(), **transport(endpoint.rstrip("/") + "/v1/systemone", payload, {}),
                 "finished_at": stamp()}
        result["stages"].append(stage)
        try:
            if stage["status"] != "ok":
                raise ValueError("Transport/model failure")
            selected = choices(stage["response"], payload, MODEL)
            stage["choices"] = selected
            if phase == "gate":
                result["gate_choices"] = selected
                payload = second_stage(prepared, selected)
                selected = {}
            else:
                payload = None
        except (ValueError, KeyError, TypeError) as error:
            result.update(status="error", error=str(error))
            break
    result["model_selections"] = selected
    result["action_mapping"] = prepared["mapping"]
    result["commands"] = decode_commands(base, prepared, selected) if result["status"] == "ok" else []
    result["finished_at"] = stamp()
    result["wall_ms"] = (time.perf_counter() - started) * 1000
    result["client_ms"] = sum(stage["client_ms"] for stage in result["stages"])
    result["protocol"] = "temperature_with_unit_actions" if prepared["mapping"] else "original_key_choices"
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--strategy", choices=STRATEGIES, required=True)
    parser.add_argument("--endpoint", default="http://127.0.0.1:18801")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Refusing to overwrite a decision")
    result = decide(json.loads(args.request.read_text()), args.strategy, args.endpoint)
    save(args.output, result)
    print(json.dumps({"status": result["status"], "commands": result["commands"],
                      "client_ms": result["client_ms"]}, ensure_ascii=False))
