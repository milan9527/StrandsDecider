"""H2O AC protocol adapter: explicit reading mode, unchanged legal action space."""

import argparse
import json
from pathlib import Path

from ablation_protocol import make_payload
from run_ablation import call, choices
from run_resident import save, sha, stamp

MODEL = "h2oai/h2o-lightning-4b"
PROFILES = ("baseline", "rules_only")
MODES = ("bidirectional", "causal")


def request(base, profile="baseline", attention="bidirectional"):
    if profile not in PROFILES or attention not in MODES:
        raise ValueError("Unsupported profile or attention mode")
    value = make_payload(base, profile)
    value["attention_mode"] = attention
    return value


def decide(payload, endpoint="http://127.0.0.1:18803", transport=call):
    row = {"started_at": stamp(), "transport_request": payload, "input_sha256": sha(payload)}
    row.update(transport(endpoint.rstrip("/") + "/v1/systemone", payload, {}))
    row["finished_at"] = stamp()
    row["commands"] = []
    if row["status"] == "ok":
        try:
            if row["response"].get("attention_mode") != payload["attention_mode"]:
                raise ValueError("Unexpected attention mode")
            selected = choices(row["response"], payload, MODEL)
            row["choices"] = selected
            row["commands"] = [{"cmdKey": key, "cmdValue": value}
                               for key, value in selected.items() if value != "omit"]
        except (ValueError, TypeError, KeyError) as error:
            row.update(status="format_error", error=str(error))
    return row


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--profile", choices=PROFILES, default="baseline")
    parser.add_argument("--attention", choices=MODES, default="bidirectional")
    parser.add_argument("--endpoint", default="http://127.0.0.1:18803")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Refusing to overwrite a decision")
    payload = request(json.loads(args.request.read_text()), args.profile, args.attention)
    result = decide(payload, args.endpoint)
    save(args.output, result)
    print(json.dumps({key: result[key] for key in ("status", "commands", "client_ms")}))
