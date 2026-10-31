import json
import unittest

from all_models_protocol import PROVIDERS
from compact_input_protocol import BASELINE, VARIANTS, catalog_from_request
from optimized_all_models_protocol import business_payload, portable_request, profile_order


class OptimizedProtocolTests(unittest.TestCase):
    def test_frozen_portable_inputs_and_single_field_context(self):
        cases = json.loads((BASELINE / "cases.json").read_text())
        for case in cases:
            for variant in VARIANTS:
                full = portable_request(case["payload"], variant)
                self.assertTrue(all(isinstance(v, str) for q in full["questions"].values()
                                    for v in q["criteria"].values()))
                for key in full["questions"]:
                    single = business_payload({**case, "payload": full}, key)
                    self.assertEqual(catalog_from_request(single), catalog_from_request(case["payload"]))
        self.assertEqual(portable_request(cases[0]["payload"], "baseline"), cases[0]["payload"])

    def test_profile_order_is_balanced_across_nine_providers(self):
        for position in range(3):
            self.assertEqual(sorted(profile_order(p)[position] for p in PROVIDERS),
                             sorted(list(VARIANTS) * 3))


if __name__ == "__main__":
    unittest.main()
