"""Regression coverage for binary SDK fields and unknown capture outcomes."""

import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from analyze import grade, summarize  # noqa: E402
from api_ablation_protocol import decode_gpt  # noqa: E402
from resume_api_capture import encode_binary  # noqa: E402


def test_binary_capture_preserves_bytes_and_choice_decoding():
    payload = {"questions": {"power": {"criteria": {"omit": "No command", "1": "On"}}}}
    native = {"stopReason": "end_turn", "output": {"message": {"content": [
        {"reasoningContent": {"redactedContent": b"\x00\xff\x80opaque"}},
        {"text": '{"answers":{"power":"1"}}'},
    ]}}}
    captured = json.loads(json.dumps(native, default=encode_binary))
    encoded = captured["output"]["message"]["content"][0]["reasoningContent"]["redactedContent"]
    assert base64.b64decode(encoded["__sdk_bytes_base64__"]) == b"\x00\xff\x80opaque"
    assert decode_gpt(captured, payload) == decode_gpt(native, payload) == {"power": "1"}


def test_capture_gap_counts_as_failure_without_inventing_timing():
    row = {
        "category": "multi", "status": "capture_error", "client_ms": None, "server_ms": None,
        **grade([{"cmdKey": "t_power", "cmdValue": "1"}], [], "capture_error"),
    }
    result = summarize([row])
    assert result["exact_match"]["denominator"] == 1
    assert result["exact_match"]["numerator"] == 0
    assert result["errors"] == 1
    assert result["client_ms"]["count"] == result["server_ms"]["count"] == 0
