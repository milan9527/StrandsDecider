"""Capability integrity checks; these do not establish model decision accuracy."""

import copy
import json
import unittest

from compact_input_protocol import (
    BASELINE, VARIANTS, audit_request, catalog_from_request, compact_request, single_field_request,
)


class CompactInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads((BASELINE / "cases.json").read_text())
        cls.example = cls.cases[0]["payload"]

    def test_every_frozen_case_preserves_complete_capabilities_and_candidates(self):
        for case in self.cases:
            for variant in VARIANTS:
                with self.subTest(case=case["case_id"], order=case["order"], variant=variant):
                    self.assertTrue(audit_request(case["payload"], compact_request(case["payload"], variant)))

    def test_query_does_not_filter_or_change_candidate_schema(self):
        altered = copy.deepcopy(self.example)
        state = json.loads(altered["state"])
        state["query"] = "Set capacity to 51%, switch to 73 Fahrenheit, and do not change the power."
        altered["state"] = json.dumps(state)
        for variant in VARIANTS:
            self.assertEqual(compact_request(self.example, variant)["questions"],
                             compact_request(altered, variant)["questions"])

    def test_all_single_field_requests_keep_the_full_catalog(self):
        for variant in VARIANTS:
            full = compact_request(self.example, variant)
            for key in full["questions"]:
                single = single_field_request(full, key)
                self.assertEqual(catalog_from_request(single), catalog_from_request(self.example))
                self.assertEqual(list(single["questions"]), [key])

    def test_status_values_remain_visible_but_cannot_be_commanded(self):
        request = compact_request(self.example, "schema_once")
        question = request["questions"]["t_auto_defrost_clean"]
        self.assertEqual(set(question["criteria"]), {"omit", "0", "1"})
        metadata = json.loads(question["instructions"])
        self.assertEqual(metadata["statusOnly"],
                         {"2": "Enabled and started", "3": "In progress", "4": "Finished"})

    def test_numeric_bounds_and_zero_versus_omit_are_preserved(self):
        for variant in VARIANTS:
            request = compact_request(self.example, variant)
            for key, low, high in (("t_temp", 16, 32), ("t_temp_f", 61, 90),
                                   ("t_dr_offset", 0, 31), ("t_dr_mode", 0, 100)):
                self.assertEqual(set(request["questions"][key]["criteria"]),
                                 {"omit"} | {str(n) for n in range(low, high + 1)})


if __name__ == "__main__":
    unittest.main()
