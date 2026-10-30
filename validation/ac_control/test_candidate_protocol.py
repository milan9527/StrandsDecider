"""Check native response compatibility without repairing wrong control decisions."""

import unittest

from run_candidate_benchmark import selected


class NativeChoiceTests(unittest.TestCase):
    def setUp(self):
        self.payload = {"questions": {
            "t_fresh_air": {"type": "choice", "criteria": {"omit": "Keep", "1": "On"}},
            "t_health_fan": {"type": "choice", "criteria": {"omit": "Keep", "1": "On"}},
        }}

    def test_optional_native_type_and_extra_action_are_preserved(self):
        response = {"answers": {
            "t_fresh_air": {"type": "choice", "choice": "1"},
            "t_health_fan": {"choice": "1"},
        }}
        self.assertEqual(selected(response, self.payload),
                         {"t_fresh_air": "1", "t_health_fan": "1"})

    def test_missing_question_is_not_filled_with_omit(self):
        with self.assertRaises(AssertionError):
            selected({"answers": {"t_fresh_air": {"choice": "1"}}}, self.payload)

    def test_unlisted_value_is_not_clamped(self):
        response = {"answers": {
            "t_fresh_air": {"choice": "7"},
            "t_health_fan": {"choice": "omit"},
        }}
        with self.assertRaises(AssertionError):
            selected(response, self.payload)

    def test_non_choice_output_is_not_converted(self):
        response = {"answers": {
            "t_fresh_air": {"type": "noul", "choice": "1", "noul": .9},
            "t_health_fan": {"choice": "omit"},
        }}
        with self.assertRaises(AssertionError):
            selected(response, self.payload)


if __name__ == "__main__":
    unittest.main()
