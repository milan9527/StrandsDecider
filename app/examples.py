"""Illustrative fixtures, never advertised as model-generated predictions or timings."""

import math

GUARD_QUESTIONS = {
    "args_grounded": {
        "type": "noul",
        "instructions": "Are the tool's argument values grounded in facts the user actually provided?",
        "criteria": {
            "true": "every argument value traces back to something the user said",
            "false": "an argument value was guessed or invented, not stated by the user",
        },
    },
    "premature": {
        "type": "noul",
        "instructions": "Is it premature to call this tool now, before clarifying with the user?",
        "criteria": {
            "true": "the assistant should ask a clarifying question before calling the tool",
            "false": "there is nothing left to clarify; calling now is appropriate",
        },
    },
}


def choice_answer(probabilities):
    n = len(probabilities)
    return {
        "type": "choice",
        "choice": max(probabilities, key=probabilities.get),
        "probabilities": probabilities,
        "confidence": (n * max(probabilities.values()) - 1) / (n - 1),
    }


def score_answer(levels, probabilities):
    mean = sum(i * p for i, p in enumerate(probabilities))
    sigma = math.sqrt(sum(p * (i - mean) ** 2 for i, p in enumerate(probabilities)))
    return {
        "type": "score",
        "score": mean,
        "legend": {str(i): label for i, label in enumerate(levels)},
        "probabilities": {str(i): p for i, p in enumerate(probabilities)},
        # Illustrative distribution without ordinal smoothing, not model calibration.
        "confidence": max(0, 1 - sigma / ((len(levels) - 1) / 2)),
    }


EXAMPLES = [
    {
        "id": "support",
        "title": "客服工单分流",
        "subtitle": "一次读取，三个决策",
        "icon": "inbox",
        "tag": "MULTI-QUESTION",
        "state": "Help! My payouts have been failing for 3 days! I need this money to pay my team. Please fix this immediately.",
        "questions": {
            "department": {
                "type": "choice",
                "instructions": "Which team should handle this customer request?",
                "criteria": {
                    "billing": "Payments, payouts, invoices and refunds",
                    "sales": "Pricing, plans and new purchases",
                    "retail": "Physical stores and in-store purchases",
                },
            },
            "is_urgent": {"type": "noul", "instructions": "Does this request convey urgency?"},
            "frustration": {
                "type": "score",
                "instructions": "How frustrated is the writer?",
                "criteria": ["Calm", "Frustrated", "Very angry"],
            },
        },
        "answers": {
            "department": choice_answer({"billing": 0.91, "sales": 0.06, "retail": 0.03}),
            "is_urgent": {"type": "noul", "noul": 0.96},
            "frustration": score_answer(["Calm", "Frustrated", "Very angry"], [0.04, 0.66, 0.30]),
        },
    },
    {
        "id": "tools",
        "title": "Agent 工具选择",
        "subtitle": "让任务找到合适的工具",
        "icon": "route",
        "tag": "CHOICE",
        "state": "What will the weather be like in Shanghai tomorrow? I am planning an outdoor event.",
        "questions": {
            "next_tool": {
                "type": "choice",
                "instructions": "Which tool is most appropriate for fulfilling the user's request?",
                "criteria": {
                    "get_weather": "Get current weather and forecasts for a city",
                    "search_web": "Search the web for general information",
                    "query_database": "Query internal business records",
                    "send_email": "Send a message to an email address",
                },
            },
            "needs_location": {
                "type": "noul",
                "instructions": "Is the user missing a city or location needed for a weather lookup?",
            },
        },
        "answers": {
            "next_tool": choice_answer(
                {
                    "get_weather": 0.96,
                    "search_web": 0.025,
                    "query_database": 0.01,
                    "send_email": 0.005,
                }
            ),
            "needs_location": {"type": "noul", "noul": 0.03},
        },
    },
    {
        "id": "sentiment",
        "title": "评论情感分析",
        "subtitle": "把主观感受变成量表",
        "icon": "heart",
        "tag": "SCORE",
        "state": "The setup took a little longer than expected, but the product is wonderful. Your support team was incredibly helpful. I'd happily recommend it!",
        "questions": {
            "sentiment": {
                "type": "score",
                "instructions": "How positive is the overall sentiment of this review?",
                "criteria": ["Very negative", "Negative", "Neutral", "Positive", "Very positive"],
            },
            "recommends": {
                "type": "noul",
                "instructions": "Does the writer recommend the product to others?",
            },
        },
        "answers": {
            "sentiment": score_answer(
                ["Very negative", "Negative", "Neutral", "Positive", "Very positive"],
                [0.01, 0.01, 0.04, 0.40, 0.54],
            ),
            "recommends": {"type": "noul", "noul": 0.98},
        },
    },
    {
        "id": "language",
        "title": "多语言识别",
        "subtitle": "候选标签由你定义",
        "icon": "globe",
        "tag": "CHOICE",
        "state": "sihamba ngokushesha",
        "questions": {
            "language": {
                "type": "choice",
                "instructions": "What language is this phrase in?",
                "criteria": {"English": None, "Zulu": None, "Dutch": None},
            },
        },
        "answers": {
            "language": choice_answer({"English": 0.015, "Zulu": 0.97, "Dutch": 0.015}),
        },
    },
]


def public_examples():
    return [{k: v for k, v in example.items() if k != "answers"} for example in EXAMPLES]
