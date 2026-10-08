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
        "category": "业务运营",
        "description": "同一张工单同时判断负责团队、紧急程度和客户情绪。",
        "suggestion": "把付款失败改成咨询升级套餐，观察负责团队与紧急程度如何变化。",
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
        "category": "Agent 流程",
        "description": "根据用户意图选择工具，并判断执行前是否还缺少地点信息。",
        "suggestion": "删除 Shanghai，观察工具选择与补充地点判断是否发生变化。",
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
        "category": "内容理解",
        "description": "将混合了抱怨与肯定的评论映射到情感量表，并判断是否愿意推荐。",
        "suggestion": "把结尾改成不会推荐这个产品，对比情感评分与推荐意愿。",
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
        "category": "内容理解",
        "description": "在给定语言标签中选择一个；候选项可以按你的任务重新定义。",
        "suggestion": "改成中文短句，并在候选项中加入 Chinese，再使用真实模型运行。",
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
    {
        "id": "refund",
        "title": "退款资格审核",
        "category": "业务运营",
        "description": "对照退款规则检查资格、金额审批要求和下一步处理方式；只展示判断。",
        "suggestion": "把购买时间改成 45 天前，或把价格提高到 $350，对比两个规则判断。",
        "subtitle": "把业务规则变成独立判断",
        "icon": "inbox",
        "tag": "POLICY CHECK",
        "state": (
            "Return policy: Items are eligible for return within 30 days of purchase if unused. "
            "Eligible returns over $200 require manual approval; eligible returns of $200 or less "
            "can enter the standard return workflow.\n"
            "Customer request: I bought a jacket 12 days ago for $79. It is unused and still sealed. "
            "The size is wrong. Please help me return it."
        ),
        "questions": {
            "eligible": {
                "type": "noul",
                "instructions": "Does this request meet both the 30-day and unused-item return rules?",
            },
            "manual_approval": {
                "type": "noul",
                "instructions": "Does this return exceed the $200 threshold requiring manual approval?",
            },
            "next_step": {
                "type": "choice",
                "instructions": "Which workflow follows the stated return policy for this request?",
                "criteria": {
                    "standard_return": "Eligible unused item within 30 days, costing $200 or less",
                    "manual_review": "Eligible return over $200 requiring manual approval",
                    "decline": "The request fails the purchase-age or unused-item rule",
                    "ask_for_details": "Required purchase-age, condition or price details are missing",
                },
            },
        },
        "answers": {
            "eligible": {"type": "noul", "noul": 0.97},
            "manual_approval": {"type": "noul", "noul": 0.03},
            "next_step": choice_answer(
                {
                    "standard_return": 0.94,
                    "manual_review": 0.02,
                    "decline": 0.02,
                    "ask_for_details": 0.02,
                }
            ),
        },
    },
    {
        "id": "leads",
        "title": "销售线索优先级",
        "category": "业务运营",
        "description": "从预算、席位数和上线计划判断购买意向，选择合适的跟进方式。",
        "suggestion": "改成尚无预算、只是了解产品，对比购买意向评分与下一步动作。",
        "subtitle": "识别意向与跟进时机",
        "icon": "zap",
        "tag": "CHOICE + SCORE",
        "state": (
            "Inbound lead: We need an enterprise workspace for 200 staff, including SSO and audit logs. "
            "Our annual budget of $60,000 is approved. We want to launch within four weeks. "
            "Could you schedule a product demo with our IT lead this week?"
        ),
        "questions": {
            "purchase_intent": {
                "type": "score",
                "instructions": "How strong is the purchase intent based on stated budget and timeline?",
                "criteria": [
                    "Browsing without a plan",
                    "Exploring a concrete need",
                    "Ready to evaluate a purchase",
                ],
            },
            "near_term": {
                "type": "noul",
                "instructions": "Does the lead state a planned launch within the next 30 days?",
            },
            "follow_up": {
                "type": "choice",
                "instructions": "Which follow-up best matches what this lead explicitly requested?",
                "criteria": {
                    "schedule_demo": "Arrange a product demonstration with the buyer's team",
                    "send_docs": "Send introductory documentation without scheduling a meeting",
                    "nurture_later": "Defer active follow-up for a long-term prospect",
                    "technical_support": "Route an existing customer's product failure to support",
                },
            },
        },
        "answers": {
            "purchase_intent": score_answer(
                [
                    "Browsing without a plan",
                    "Exploring a concrete need",
                    "Ready to evaluate a purchase",
                ],
                [0.02, 0.10, 0.88],
            ),
            "near_term": {"type": "noul", "noul": 0.96},
            "follow_up": choice_answer(
                {
                    "schedule_demo": 0.94,
                    "send_docs": 0.03,
                    "nurture_later": 0.02,
                    "technical_support": 0.01,
                }
            ),
        },
    },
    {
        "id": "moderation",
        "title": "社区内容审核",
        "category": "内容理解",
        "description": "区分正常的负面评价与违规内容，避免把不满意直接当作审核风险。",
        "suggestion": "把评论换成重复的站外促销广告，观察是否转入人工审核。",
        "subtitle": "负面情绪不等于违规",
        "icon": "shield",
        "tag": "CONTENT REVIEW",
        "state": (
            "Community policy: Allow civil product criticism, including negative reviews. "
            "Send unsolicited sales promotions or repeated advertisements for review. "
            "Escalate direct threats of physical harm.\n"
            "Post: My delivery was late twice and support still has not replied. "
            "I am disappointed and would not recommend this service until they improve."
        ),
        "questions": {
            "review_action": {
                "type": "choice",
                "instructions": "Which action fits this post under the stated community policy?",
                "criteria": {
                    "allow": "Civil product criticism with no promotion or direct threat",
                    "review_promotion": "Unsolicited sales promotion or repeated advertising",
                    "escalate_threat": "A direct threat of physical harm",
                },
            },
            "contains_promotion": {
                "type": "noul",
                "instructions": "Is the post promoting or advertising an offer to other users?",
            },
        },
        "answers": {
            "review_action": choice_answer(
                {"allow": 0.95, "review_promotion": 0.03, "escalate_threat": 0.02}
            ),
            "contains_promotion": {"type": "noul", "noul": 0.02},
        },
    },
    {
        "id": "invoice",
        "title": "发票字段校验",
        "category": "数据与运维",
        "description": "先识别单据类型，再按金额规则检查采购单号是否缺失，决定能否继续处理。",
        "suggestion": "补上采购单号 PO-2048，或把金额改成 $800，对比处理条件。",
        "subtitle": "结构识别与必填项检查",
        "icon": "layers",
        "tag": "DOCUMENT CHECK",
        "state": (
            "Processing policy: An invoice above $1,000 must include a purchase order number "
            "before it can be processed.\n"
            "Document: INVOICE INV-2026-042. Supplier: Harbor Labs. Customer: Demo Company. "
            "Description: Software consulting. Total due: $1,250 USD. Due in 7 days. "
            "Purchase order number: not provided."
        ),
        "questions": {
            "document_type": {
                "type": "choice",
                "instructions": "What type of business document is provided?",
                "criteria": {
                    "invoice": "A supplier's request for payment",
                    "receipt": "Confirmation that payment has already been made",
                    "contract": "An agreement defining terms and obligations",
                },
            },
            "missing_required_po": {
                "type": "noul",
                "instructions": "Is a purchase order number required by the amount rule but missing?",
            },
            "ready_to_process": {
                "type": "noul",
                "instructions": "Does this invoice meet the purchase-order requirement for processing?",
            },
        },
        "answers": {
            "document_type": choice_answer({"invoice": 0.97, "receipt": 0.02, "contract": 0.01}),
            "missing_required_po": {"type": "noul", "noul": 0.98},
            "ready_to_process": {"type": "noul", "noul": 0.03},
        },
    },
    {
        "id": "incident",
        "title": "运维告警分级",
        "category": "数据与运维",
        "description": "结合 ECS、ALB 和业务影响的示例信号判断故障级别；不会操作 AWS 资源。",
        "suggestion": "把告警改成仅内部测试环境失败，并注明客户服务正常，对比级别与通知判断。",
        "subtitle": "从技术信号判断业务影响",
        "icon": "cpu",
        "tag": "INCIDENT TRIAGE",
        "state": (
            "Incident policy: SEV1 means a critical customer workflow is unavailable to all users. "
            "SEV2 means partial customer impact. SEV3 means an internal problem without customer impact. "
            "Page the on-call engineer immediately for SEV1 or SEV2.\n"
            "Alert: Production ECS payments-api has 0 running tasks out of 4 desired. "
            "ALB healthy targets: 0. Checkout failure rate: 100%. "
            "All customers are unable to pay, and there have been no successful checkouts for 5 minutes."
        ),
        "questions": {
            "severity": {
                "type": "choice",
                "instructions": "Which incident severity matches the stated customer impact and policy?",
                "criteria": {
                    "SEV1": "A critical customer workflow is unavailable to all users",
                    "SEV2": "Only some customers are affected",
                    "SEV3": "Only internal systems are affected; no customer impact",
                },
            },
            "page_on_call": {
                "type": "noul",
                "instructions": "Does the stated incident policy require paging the on-call engineer now?",
            },
            "customer_impact": {
                "type": "score",
                "instructions": "How severe is the stated impact on customers?",
                "criteria": [
                    "No customer impact",
                    "Partial disruption",
                    "Critical workflow unavailable to all",
                ],
            },
        },
        "answers": {
            "severity": choice_answer({"SEV1": 0.96, "SEV2": 0.03, "SEV3": 0.01}),
            "page_on_call": {"type": "noul", "noul": 0.98},
            "customer_impact": score_answer(
                [
                    "No customer impact",
                    "Partial disruption",
                    "Critical workflow unavailable to all",
                ],
                [0.01, 0.04, 0.95],
            ),
        },
    },
    {
        "id": "rag",
        "title": "RAG 回答依据",
        "category": "Agent 流程",
        "description": "判断检索结果是否足以回答问题，决定继续检索还是依据现有材料作答。",
        "suggestion": "把问题改成国内出差的酒店费用上限，观察现有材料是否已经足够。",
        "subtitle": "材料不够时继续检索",
        "icon": "lightbulb",
        "tag": "GROUNDED ANSWER",
        "state": (
            "Retrieved travel policy: For domestic trips, employees book economy flights. "
            "The hotel limit is $180 per night and the meal limit is $60 per day. "
            "This excerpt contains no rules for international flights.\n"
            "User question: May I book premium economy for an international flight longer than eight hours?"
        ),
        "questions": {
            "can_answer": {
                "type": "noul",
                "instructions": "Does the retrieved text explicitly provide the information needed to answer the user's question?",
            },
            "next_action": {
                "type": "choice",
                "instructions": "What should the assistant do given the available evidence?",
                "criteria": {
                    "retrieve_more": "Find additional source material because the retrieved text lacks the answer",
                    "answer_from_context": "Answer directly because the retrieved text states the relevant rule",
                    "clarify_question": "Ask what the user means because their question is unclear",
                },
            },
            "evidence_quality": {
                "type": "score",
                "instructions": "How complete is the evidence for answering the user's question using only the retrieved text?",
                "criteria": ["No relevant answer", "Partial answer", "Direct answer"],
            },
        },
        "answers": {
            "can_answer": {"type": "noul", "noul": 0.03},
            "next_action": choice_answer(
                {"retrieve_more": 0.94, "answer_from_context": 0.02, "clarify_question": 0.04}
            ),
            "evidence_quality": score_answer(
                ["No relevant answer", "Partial answer", "Direct answer"], [0.93, 0.05, 0.02]
            ),
        },
    },
    {
        "id": "approval",
        "title": "工具操作审批",
        "category": "Agent 流程",
        "description": "核对工具动作是否符合只读请求，并区分重新规划、请求授权与直接执行。",
        "suggestion": "把 SQL 改为只读统计昨日订单数量的 SELECT 查询，观察动作匹配与审批判断。",
        "subtitle": "在写操作前检查用户意图",
        "icon": "lock",
        "tag": "ACTION REVIEW",
        "state": (
            "Policy: A read-only user request must not trigger destructive writes; "
            "replan with a read-only query instead. A destructive write would require explicit authorization.\n"
            "User: Show me how many orders were created yesterday. Do not change any data.\n"
            "Proposed tool: execute_sql. SQL: DELETE FROM orders WHERE created_at < CURRENT_DATE;"
        ),
        "questions": {
            "matches_request": {
                "type": "noul",
                "instructions": "Does the proposed SQL fulfill the user's request without violating the read-only constraint?",
            },
            "requires_authorization": {
                "type": "noul",
                "instructions": "Does the proposed operation change or delete data and therefore require explicit authorization?",
                "criteria": {
                    "true": "The proposed tool deletes or changes data, requiring explicit destructive-write permission",
                    "false": "The proposed tool only reads data and does not require destructive-write permission",
                },
            },
            "next_action": {
                "type": "choice",
                "instructions": "Which action follows the stated policy for this proposed tool call?",
                "criteria": {
                    "replan_read_only": "Reject the mismatched write and prepare a read-only query",
                    "request_authorization": "The write matches the user's task but still needs explicit authorization",
                    "proceed": "The tool call matches the request and all required permissions are present",
                },
            },
        },
        "answers": {
            "matches_request": {"type": "noul", "noul": 0.02},
            "requires_authorization": {"type": "noul", "noul": 0.98},
            "next_action": choice_answer(
                {"replan_read_only": 0.95, "request_authorization": 0.04, "proceed": 0.01}
            ),
        },
    },
    {
        "id": "summary",
        "title": "摘要质量检查",
        "category": "内容理解",
        "description": "对照原文检查摘要是否夸大结论，按忠实度评分并建议是否需要重写。",
        "suggestion": "修正摘要中的人数、错误情况和上线结论，对比忠实度评分。",
        "subtitle": "检查事实一致性与遗漏",
        "icon": "message",
        "tag": "QUALITY SCORE",
        "state": (
            "Source: The pilot lasted 14 days. 24 of 30 customers completed setup. "
            "Four customers reported timeouts. There were no payment errors. "
            "Production rollout is pending a load test.\n"
            "Draft summary: All 30 customers completed setup without any errors. "
            "The product is cleared for production rollout."
        ),
        "questions": {
            "factually_supported": {
                "type": "noul",
                "instructions": "Are all factual claims in the draft summary supported by the source?",
            },
            "faithfulness": {
                "type": "score",
                "instructions": "How faithfully does the draft preserve the source's key facts and qualifications?",
                "criteria": [
                    "Major contradictions",
                    "Partially faithful with important omissions",
                    "Faithful and qualified",
                ],
            },
            "next_step": {
                "type": "choice",
                "instructions": "What should happen to this draft based on the comparison with the source?",
                "criteria": {
                    "rewrite": "Correct material contradictions or unsupported claims using the available source",
                    "approve": "The draft accurately preserves the source's facts and qualifications",
                    "request_source": "No source text is available to check the draft",
                },
            },
        },
        "answers": {
            "factually_supported": {"type": "noul", "noul": 0.02},
            "faithfulness": score_answer(
                [
                    "Major contradictions",
                    "Partially faithful with important omissions",
                    "Faithful and qualified",
                ],
                [0.91, 0.07, 0.02],
            ),
            "next_step": choice_answer({"rewrite": 0.96, "approve": 0.02, "request_source": 0.02}),
        },
    },
]


def public_examples():
    return [{k: v for k, v in example.items() if k != "answers"} for example in EXAMPLES]
