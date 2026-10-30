"""Check failure accounting and frozen-input integrity before interpreting results."""
import hashlib
import json
import unittest
from pathlib import Path

from analyze import score
from run import normalize

ROOT = Path(__file__).parent


class EvidenceTests(unittest.TestCase):
    def test_incomplete_or_invented_choices_are_failures(self):
        request = {"questions": {
            "power": {"criteria": {"on": "Turn on", "off": "Turn off"}},
            "mode": {"criteria": {"cool": "Cooling", "heat": "Heating"}},
        }}
        with self.assertRaises(ValueError):
            normalize({"answers": {"power": {"choice": "on"}}}, request)
        with self.assertRaises(ValueError):
            normalize({"answers": {"power": {"choice": "on"}, "mode": {"choice": "auto"}}}, request)

    def test_failure_is_included_in_denominator_not_in_success_latency(self):
        references = {"case": {"expected": {"power": "on", "mode": "cool"}}}
        rows = [
            {"case_id": "case", "variant": "original", "status": "ok",
             "choices": {"power": "on", "mode": "heat"}, "client_ms": 20},
            {"case_id": "case", "variant": "reversed", "status": "error", "client_ms": 90000},
        ]
        result = score(rows, references)
        self.assertEqual(result["correct_decisions"], 1)
        self.assertEqual(result["total_decisions"], 4)
        self.assertEqual(result["decision_accuracy_including_failures"], .25)
        self.assertEqual(result["call_or_format_failures"], 1)
        self.assertEqual(result["valid_order_pairs"], 0)
        self.assertEqual(result["client_p50_ms"], 20)

    def test_frozen_plan_and_payload_separation(self):
        plan = json.loads((ROOT / "plan.json").read_text())
        rows = json.loads((ROOT / "requests.json").read_text())
        canonical = json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), plan["request_list_sha256"])
        self.assertEqual(len(rows), 178)
        for row in rows:
            self.assertEqual(set(row["request"]), {"state", "questions"})
        for original, reversed_row in zip(rows[::2], rows[1::2]):
            self.assertEqual(original["case_id"], reversed_row["case_id"])
            self.assertEqual(original["request"]["state"], reversed_row["request"]["state"])
            for qid, question in original["request"]["questions"].items():
                other = reversed_row["request"]["questions"][qid]
                self.assertEqual(question["instructions"], other["instructions"])
                self.assertEqual(question["criteria"], other["criteria"])
                self.assertEqual(list(question["criteria"]), list(reversed(other["criteria"])))


if __name__ == "__main__":
    unittest.main()
