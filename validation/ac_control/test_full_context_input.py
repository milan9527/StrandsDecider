import json
import unittest

from compact_input_protocol import BASELINE
from full_context_input import audit_full_context, catalog_from_columnar, compact_full_context
from optimized_all_models_protocol import business_payload


class FullContextTests(unittest.TestCase):
    def test_every_request_and_internal_field_preserves_complete_mapping(self):
        cases = json.loads((BASELINE / "cases.json").read_text())
        for case in cases:
            request = compact_full_context(case["payload"])
            self.assertTrue(audit_full_context(case["payload"], request))
            for key in request["questions"]:
                single = business_payload({**case, "payload": request}, key)
                self.assertEqual(catalog_from_columnar(single), catalog_from_columnar(request))


if __name__ == "__main__":
    unittest.main()
