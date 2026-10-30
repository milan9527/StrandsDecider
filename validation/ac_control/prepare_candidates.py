"""Freeze the same AC inputs for isolated L4 candidates, with a separate Chinese set."""

import copy
import hashlib
import json
from pathlib import Path

from prepare import payload
from run_resident import save, sha, stamp
from stage_candidate_models import MODELS

HERE = Path(__file__).resolve().parent
CHINESE = [
    "打开空调，保持运行模式不变。",
    "关闭空调，不要改变静音设置。",
    "将目标温度设为21摄氏度，并开启节能。",
    "将目标温度设为73华氏度，风速调到高档。",
    "开启上下连续扫风，保持左右风向不变。",
    "关闭上下连续扫风，并将左右风向设为正前方。",
    "把上下风向设为位置2，左右风向设为全右。",
    "关闭新风，保持健康风设置不变。",
    "开启健康风，不要改变新风设置。",
    "开启8度防冻保暖，保持需求响应的温度偏移量不变。",
    "关闭8度防冻保暖，并关闭显示灯。",
    "开启室外静音，关闭室内静音。",
    "切换到制热模式，风速调到低档，目标温度保持不变。",
    "开启舒适自动功能，不要改变运行模式。",
    "将运行模式设为自动，保持舒适自动功能不变。",
    "关闭AI智能，并把AI风设为朝向人吹。",
    "开启室外自清洁，保持室内自清洁设置不变。",
    "开启一键自清洁，不要改变单独的室内自清洁和室外自清洁开关。",
    "选择青年睡眠模式，并开启空气净化。",
    "开启需求响应，将温度偏移量设为6度，负载容量设为52%。",
    "关闭需求响应，保持其温度偏移量和负载容量不变。",
    "关闭自动除霜清洁，并关闭强劲模式。",
    "只把温度单位切换为华氏度，保持目标温度数值不变。",
    "保持空调的所有设置不变。",
]


def prepare(root):
    root.mkdir(parents=True, exist_ok=False)
    prior = HERE / "runs/2026-10-30-h2o-official-v2"
    caps = json.loads((prior / "command_set.json").read_text())
    references = json.loads((prior / "references.json").read_text())
    cases = (json.loads((prior / "development_cases.json").read_text())
             + json.loads((prior / "validation_cases.json").read_text()))
    for case in cases:
        case["language"] = "en"
    for number, query in enumerate(CHINESE, 1):
        original = next(r for r in references if r["id"] == f"H{number:02d}")
        ref = {**copy.deepcopy(original), "id": f"Z{number:02d}", "query": query,
               "dataset": "chinese", "translation_of": original["id"]}
        references.append(ref)
        for order in ("original", "reversed"):
            cases.append({"case_id": ref["id"], "dataset": "chinese", "order": order,
                          "language": "zh", "payload": payload(query, caps, order == "reversed")})
    for case in cases:
        assert len(case["payload"]["questions"]) == 30
        reference = next(r for r in references if r["id"] == case["case_id"])
        for command in reference["expected"]:
            assert command["cmdValue"] in case["payload"]["questions"][command["cmdKey"]]["criteria"]
    save(root / "cases.json", cases)
    save(root / "references.json", references)
    save(root / "command_set.json", caps)
    save(root / "models.json", {
        name: {"repository": repo, "revision": revision} for name, (repo, revision) in MODELS.items()})
    save(root / "plan.json", {
        "prepared_at": stamp(), "instance_id": "i-0bd4d9196f1c163c0", "instance_type": "g6.xlarge",
        "model_order": ["pplx", "knowline", "torchcast", "clef", "h2o"],
        "cases_sha256": sha(cases), "references_sha256": sha(references),
        "capabilities_sha256": sha(caps), "models_sha256": sha(json.loads((root / "models.json").read_text())),
        "quality_requests_per_model": 156,
        "quality_sets": {"spec_en": 20, "diagnostic_en": 10, "heldback_en": 24, "chinese_translations": 24},
        "orders": ["original", "reversed"],
        "prompt": "Original full30 baseline; same state, rules, questions and legal options for all models.",
        "chinese_policy": "Translate only the user query of H01-H24; preserve the English catalog and rubric. Gold copied from semantically corresponding frozen English cases; score Chinese separately, not as 24 independent new intentions.",
        "heldback_policy": "Same-domain authored validation frozen before candidate inference; not an external blind benchmark. No tuning on validation.",
        "timing_policy": "One externally submitted HTTP request at a time; one resident model on new GPU. Separate startup/warmup, single t_temp, serial30 and full30. S03 repeated three times per timing mode; retain complete state and candidates.",
        "internal_execution": "Authors' recommended runtime; joint questions, independent question forwards and native option grouping disclosed separately.",
        "warmup_policy": "Three S03 full30 warmups and one for each single-field shape before timed single-field requests; retain warmup receipts separately.",
        "quality_policy": "Strict entire command-set match; omit only means no command. Never repair units or remove extra actions. Transport/format failures count as incorrect; no inference retries.",
        "precision_policy": "Recommended candidate precision; H2O control FP8, seq1 eager with original 4096 context and 0.34 GPU utilization. Record actual packages/runtime, do not label different paths equivalent.",
        "resource_policy": "Only one additional EC2 authorized. Stop it after artifacts are verified; six-hour boot-time stop guard. No changes to protected original services.",
        "unsupported_policy": "If a native runtime cannot serve full inputs within L4 memory, record failure before considering an explicitly labeled fallback. Never silently shrink state/options or claim reference speed is optimized speed.",
        "external_concurrency": 1, "automatic_retries": 0,
        "preparation_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    })
    print(json.dumps({"run": str(root), "quality_requests_per_model": len(cases),
                      "english": 108, "chinese": 48}))


if __name__ == "__main__":
    import sys
    prepare(Path(sys.argv[1]))
