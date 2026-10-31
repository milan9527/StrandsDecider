import unittest

from report_optimized_models import normalized_usage, usage_summary


class UsageTests(unittest.TestCase):
    def test_bedrock_cached_input_counts_once(self):
        row = {"provider": "gpt", "response": {"usage": {
            "inputTokens": 2, "cacheReadInputTokens": 100,
            "cacheWriteInputTokens": 5220, "outputTokens": 207,
        }}}
        self.assertEqual(normalized_usage(row), {
            "input": 5322, "output": 207, "cache_read": 100, "cache_write": 5220,
        })

    def test_h2o_logical_and_processed_tokens_stay_separate(self):
        row = {"provider": "h2o", "response": {"usage": {
            "input_tokens": 6468, "processed_input_tokens": 40137,
        }}}
        self.assertEqual(normalized_usage(row), {"input": 6468, "processed_input": 40137})

    def test_error_without_usage_is_missing_not_zero_tokens(self):
        result = usage_summary([
            {"provider": "jev", "response": None},
            {"provider": "jev", "response": {"usage": {"input_tokens": 100}}},
        ])
        self.assertEqual(result["requests"], 2)
        self.assertEqual(result["input"], {"observed_requests": 1, "sum": 100, "mean": 100})


if __name__ == "__main__":
    unittest.main()
