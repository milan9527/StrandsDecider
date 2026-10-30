"""Audit seven providers and render AC specification, request-layout and supplementary results."""

import argparse
import copy
import json
from datetime import datetime
from pathlib import Path

from analyze import display_commands, display_ratio, grade, ratio, summarize, timing
from analyze_candidates import analyze as audit_candidates
from api_ablation_protocol import decode_gpt, decode_jev, gpt_request, jev_request
from prepare import SPEC, payload, read_spec
from run_candidate_benchmark import sha, stamp
from run_spec_cloud import digest, save

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
NAMES = {
    "jev": "Jev", "gpt": "GPT 6.1 Sol · low", "clef": "Clef-Flash",
    "knowline": "KnowLine Gen5.5", "h2o": "H2O", "torchcast": "Torchcast",
    "pplx": "Perplexity Flash",
}


def commands(choices):
    return [{"cmdKey": k, "cmdValue": v} for k, v in choices.items() if v != "omit"]


def read_calls(folder):
    return [json.loads(line) for line in (folder / "receipts.jsonl").read_text().splitlines()]


def business_input(row, provider):
    if provider in ("jev", "gpt"):
        return row["payload"]
    return {k: v for k, v in row["transport_request"].items() if k not in ("model", "attention_mode")}


def schedule_identity(row, provider):
    return tuple(row[k] for k in ("case_id", "dataset", "language", "order", "kind", "repetition")) + (
        sha(business_input(row, provider)),)


def audit(root):
    root = root.resolve()
    plan = json.loads((root / "plan.json").read_text())
    parent = root.parent / plan["parent_run"]
    for name, expected in plan["input_files_sha256"].items():
        assert digest(root / name) == expected, name
    for name, expected in plan["source_sha256"].items():
        assert digest(root / "sources" / name) == expected, name
    for name, expected in plan["parent_evidence_sha256"].items():
        assert digest(parent / name) == expected, name
    assert digest(SPEC) == digest(root / "spec.md"), "Current specification changed"
    capabilities, refs = read_spec()
    assert refs == json.loads((root / "spec_references.json").read_text())
    assert sum(len(r["expected"]) for r in refs) == 40
    cases = json.loads((root / "cases.json").read_text())
    by_case = {(r["case_id"], r["order"]): r for r in cases}
    all_refs = {r["id"]: r for r in json.loads((root / "references.json").read_text())}
    for ref in refs:
        assert all(all_refs[ref["id"]][key] == value for key, value in ref.items())
        for order in ("original", "reversed"):
            assert sha(by_case[ref["id"], order]["payload"]) == sha(
                payload(ref["query"], capabilities, order == "reversed"))
    assert capabilities == json.loads((root / "command_set.json").read_text())
    command_names = {c["key"]: c["name"] for c in capabilities["commandSet"]}
    profile = json.loads((root / "bedrock_profile.json").read_text())
    assert profile["status"] == "ACTIVE" and profile["inferenceProfileId"] == plan["gpt_model"]
    parent_audit = audit_candidates(parent, output_path=root / "candidate_reaudit.json")
    assert parent_audit["input_audit_passed"]
    calls, metadata, evidence = {}, {}, {}
    for provider in NAMES:
        folder = (root if provider in ("jev", "gpt") else parent) / "results" / provider
        calls[provider], metadata[provider] = read_calls(folder), json.loads((folder / "run.json").read_text())
        assert metadata[provider]["status"] in ("complete", "complete_with_errors"), provider
        assert len(calls[provider]) == metadata[provider]["calls"] == 285
        assert sum(row["kind"].startswith("warmup") for row in calls[provider]) == 33
        assert metadata[provider]["errors"] == sum(r["status"] != "ok" for r in calls[provider])
        evidence[provider] = {
            "run": str(folder.relative_to(ROOT)), "receipts_sha256": digest(folder / "receipts.jsonl"),
            "metadata_sha256": digest(folder / "run.json"),
            "started_at": metadata[provider]["started_at"], "finished_at": metadata[provider]["finished_at"],
            "reused_live_observations": provider not in ("jev", "gpt"),
        }
        if provider not in ("jev", "gpt"):
            continue
        assert metadata[provider]["plan_sha256"] == digest(root / "plan.json")
        assert metadata[provider]["external_concurrency"] == 1
        assert metadata[provider]["automatic_retries"] == 0
        for row in calls[provider]:
            task = copy.deepcopy(by_case[row["case_id"], row["order"]]["payload"])
            if row["kind"] in ("warmup_single", "single_key", "serial30"):
                keys = list(row["payload"]["questions"])
                assert len(keys) == 1
                assert row["kind"] != "single_key" or keys == ["t_temp"]
                task["questions"] = {keys[0]: task["questions"][keys[0]]}
            assert sha(task) == sha(row["payload"]) == row["input_sha256"]
            transport = gpt_request(task) if provider == "gpt" else jev_request(task)
            assert sha(transport) == sha(row["transport_request"]) == row["transport_sha256"]
            if row["status"] == "ok":
                assert row["http_status"] == 200 and row["model_id"] == metadata[provider]["expected_model"]
                if provider == "jev":
                    assert row["response"] == json.loads(row["response_text"])
                    selected = decode_jev(row["response"], task, metadata[provider]["expected_model"])
                else:
                    assert row["response"]["ResponseMetadata"]["RetryAttempts"] == 0
                    selected = decode_gpt(row["response"], task)
                assert selected == row["choices"]
                assert commands(selected) == row["commands"]
    baseline = [schedule_identity(row, "pplx") for row in calls["pplx"]]
    all_calls = []
    results = {}
    for provider in NAMES:
        observed = calls[provider]
        assert [schedule_identity(row, provider) for row in observed] == baseline, provider
        meta = metadata[provider]
        blocks = meta["serial30_blocks"]
        assert len(blocks) == 3
        for block in blocks:
            rows = [r for r in observed if r["kind"] == "serial30" and r["repetition"] == block["repetition"]]
            assert len(rows) == 30
            assert block["artifact_operations_inside_block"] == 0
            assert abs(block["http_sum_ms"] - sum(r["client_ms"] for r in rows)) < .01
            assert block["wall_ms"] >= block["http_sum_ms"]
            assert block["started_at"] <= rows[0]["started_at"] <= rows[-1]["finished_at"] <= block["finished_at"]
        scored = []
        for row in observed:
            if row["kind"] != "quality":
                continue
            ref = all_refs[row["case_id"]]
            scored.append({
                **{k: row[k] for k in ("case_id", "dataset", "order", "language", "status", "client_ms")},
                "category": ref["category"], "query": ref["query"],
                "expected": ref["expected"], "commands": row["commands"],
                "cmdList": [{"cmdName": command_names[c["cmdKey"]], **c} for c in row["commands"]],
                "choices": row.get("choices", {}), "server_ms": row.get("server_ms"),
                **grade(ref["expected"], row["commands"], row["status"]),
            })
        primary = [r for r in scored if r["dataset"] == "spec" and r["order"] == "original"]
        reverse = [r for r in scored if r["dataset"] == "spec" and r["order"] == "reversed"]
        assert [r["case_id"] for r in primary] == [r["id"] for r in refs]
        assert len(reverse) == 20
        layouts = []
        for repetition in range(3):
            full = next(r for r in observed if r["kind"] == "full30" and r["repetition"] == repetition)
            serial = [r for r in observed if r["kind"] == "serial30" and r["repetition"] == repetition]
            combined = {k: v for r in serial for k, v in r.get("choices", {}).items()}
            status = "ok" if all(r["status"] == "ok" for r in serial) else "error"
            layouts.append({
                "repetition": repetition,
                "serial_correct": grade(all_refs["S03"]["expected"], commands(combined), status)["correct"],
                "full_correct": grade(all_refs["S03"]["expected"], full["commands"], full["status"])["correct"],
                "serial_choices": combined, "full_choices": full.get("choices", {}),
                "changed_fields": [k for k, v in combined.items() if full.get("choices", {}).get(k) != v],
            })
        expected_choices = dict.fromkeys(by_case["S03", "original"]["payload"]["questions"], "omit")
        expected_choices.update({c["cmdKey"]: c["cmdValue"] for c in all_refs["S03"]["expected"]})
        steps = [r for r in observed if r["kind"] == "serial30"]
        full_rows = [r for r in observed if r["kind"] == "full30"]
        fixed_rows = [r for r in observed if r["kind"] == "single_key"]
        assert len(steps) == 90 and len(full_rows) == len(fixed_rows) == 3
        step_checks = []
        for row in steps:
            keys = list(business_input(row, provider)["questions"])
            assert len(keys) == 1
            key = keys[0]
            actual = row.get("choices", {}).get(key)
            step_checks.append({
                "repetition": row["repetition"], "key": key, "expected": expected_choices[key],
                "actual": actual, "status": row["status"], "client_ms": row["client_ms"],
                "correct": row["status"] == "ok" and actual == expected_choices[key],
            })
        assert all(sum(r["key"] == key for r in step_checks) == 3 for key in expected_choices)
        full_field_hits = sum(
            row["status"] == "ok" and row.get("choices", {}).get(key) == value
            for row in full_rows for key, value in expected_choices.items())
        active = [r for r in step_checks if r["expected"] != "omit"]
        omit = [r for r in step_checks if r["expected"] == "omit"]
        mode_accuracy = {
            "case_id": "S03", "query": all_refs["S03"]["query"], "unique_business_cases": 1,
            "repetitions": 3, "expected_choices": expected_choices,
            "single_step_fields": ratio(sum(r["correct"] for r in step_checks), len(step_checks)),
            "single_step_active_fields": ratio(sum(r["correct"] for r in active), len(active)),
            "single_step_omit_fields": ratio(sum(r["correct"] for r in omit), len(omit)),
            "serial30_tasks": ratio(sum(r["serial_correct"] for r in layouts), len(layouts)),
            "full30_tasks": ratio(sum(r["full_correct"] for r in layouts), len(layouts)),
            "full30_fields": ratio(full_field_hits, len(full_rows) * len(expected_choices)),
            "fixed_t_temp_fields": ratio(sum(
                r["status"] == "ok" and r.get("choices", {}).get("t_temp") == expected_choices["t_temp"]
                for r in fixed_rows), len(fixed_rows)),
            "single_step_checks": step_checks,
        }
        results[provider] = {
            "model": meta.get("model", meta.get("expected_model")),
            "evidence": evidence[provider],
            "calls": len(observed), "warmups": 33, "formal_calls": 252, "errors": meta["errors"],
            "primary": summarize(primary), "reversed": summarize(reverse),
            "primary_rows": primary, "reversed_rows": reverse,
            "s03_latency": {
                "single_key_ms": timing(r["client_ms"] for r in observed if r["kind"] == "single_key"),
                "serial30_step_ms": timing(r["client_ms"] for r in observed if r["kind"] == "serial30"),
                "serial30_wall_ms": timing(b["wall_ms"] for b in blocks),
                "serial30_http_sum_ms": timing(b["http_sum_ms"] for b in blocks),
                "full30_ms": timing(r["client_ms"] for r in observed if r["kind"] == "full30"),
            },
            "s03_layout_comparison": layouts,
            "s03_mode_accuracy": mode_accuracy,
            "supplementary_156": summarize(scored),
            "supplementary_by_dataset": {
                dataset: {order: summarize([r for r in scored if r["dataset"] == dataset and r["order"] == order])
                          for order in ("original", "reversed")}
                for dataset in ("extension", "validation", "chinese")
            },
        }
        all_calls.extend(observed)
    all_calls.sort(key=lambda r: r["started_at"])
    for previous, current in zip(all_calls[:-1], all_calls[1:], strict=True):
        assert datetime.fromisoformat(previous["finished_at"]) <= datetime.fromisoformat(current["started_at"])
    result = {
        "generated_at": stamp(), "spec_sha256": digest(SPEC), "spec_case_count": 20,
        "spec_expected_pair_count": 40, "same_ordered_business_request_schedule": True,
        "request_overlap_count": 0, "references_sent": False, "output_repair": False,
        "new_live_providers": ["jev", "gpt"], "reused_live_providers": list(parent_audit["models"]),
        "observed_calls": len(all_calls), "new_calls": len(calls["jev"]) + len(calls["gpt"]),
        "primary_requests": 140, "formal_calls": 7 * 252, "warmup_calls": 7 * 33,
        "errors": sum(r["status"] != "ok" for r in all_calls),
        "bedrock_profile_sha256": digest(root / "bedrock_profile.json"),
        "analyzer_sha256": digest(Path(__file__)), "models": results,
    }
    save(root / "summary.json", result)
    save(root / "audit.json", {k: v for k, v in result.items() if k != "models"} | {
        "passed": True, "source_and_parent_receipts_unchanged": True, "evidence": evidence,
    })
    (root / "analysis_sources").mkdir(exist_ok=True)
    for name in ("report_spec_unified.py", "analyze.py", "analyze_candidates.py"):
        (root / "analysis_sources" / name).write_bytes((HERE / name).read_bytes())
    examples = root / "examples"
    examples.mkdir(exist_ok=True)
    for ref in refs:
        save(examples / (ref["id"] + ".request.json"), by_case[ref["id"], "original"]["payload"])
    for provider, rows in calls.items():
        first_serial = [r for r in rows if r["kind"] == "serial30" and r["repetition"] == 0]
        save(examples / f"{provider}-S03.layouts.json", {
            "expected_local_only": all_refs["S03"]["expected"],
            "single_step_example": next(r for r in first_serial if "t_temp" in business_input(r, provider)["questions"]),
            "serial30_first_round": first_serial,
            "serial30_first_round_timing": metadata[provider]["serial30_blocks"][0],
            "full30_first_round": next(r for r in rows if r["kind"] == "full30" and r["repetition"] == 0),
        })
        for row in rows:
            if row["kind"] == "quality" and row["order"] == "original" and row["case_id"] in ("S01", "S04", "M08"):
                save(examples / f"{provider}-{row['case_id']}.json", {
                    "expected_local_only": all_refs[row["case_id"]]["expected"], "raw_receipt": row,
                })
    return result


def render(root, result):
    root = root.resolve()
    model_results = result["models"]
    s03_query = next(r["query"] for r in model_results["gpt"]["primary_rows"] if r["case_id"] == "S03")
    link = "../validation/ac_control/runs/" + root.name
    text = [
        "# 空调控制七模型对照总结：测试过程、结果与差异解释", "",
        "2026-10-30。验收依据为 [AC_Control_Test_Spec.md](AC_Control_Test_Spec.md) 的原文、"
        "完整 30 项 Command Set 和全部 20 条标准答案：S01–S10 单指令、M01–M10 多指令。"
        "**主成绩只计原始选项顺序的这 20 题**，共 40 个预期 Key/Value；"
        "中文题、诊断题、新增题和选项反转均不计入主成绩。", "",
        "五个本地模型复用已完成的独占 L4 实测，逐项核验与当前规范完全一致；"
        "Jev 和 GPT 按相同冻结输入、请求顺序及预热流程新增真实调用。"
        "GPT 固定 `us.openai.gpt-6.1-sol`，每次显式设置 `reasoning.effort=low`。"
        "本地原始记录未修改，也没有把历史 Jev/GPT 分数填入新结果。", "",
        "**本批规范题中，GPT 为 20/20，Jev 与 Clef 为 19/20；Jev 完整请求最快，"
        "本地候选中 KnowLine 完整请求最快。** S03 的逐字段与一次全答对照说明，"
        "一次提交全部字段通常能减少总时间，但收益取决于模型服务的内部实现；"
        "Perplexity 全答更快却多发动作，必须同时考察时间和整组正确率。", "",
        "阅读：[测试范围与过程](#test-process) · [规范结果](#spec-results) · "
        "[三种请求方式](#request-layouts) · [模型差异解释](#model-differences) · "
        "[扩展场景](#supplementary) · [结论与历史实验](#conclusions)", "",
        '<a id="test-process"></a>', "",
        "## 测试范围与过程", "",
        "本轮比较 Jev、GPT 6.1 Sol low、Clef-Flash、KnowLine Gen5.5、H2O-Lightning、"
        "Torchcast 与 Perplexity Flash。五个本地模型在同一台独占 g6.xlarge / L4 上依次装载；"
        "Jev/GPT 通过各自托管 API 调用。所有外部推理请求依次执行，业务输入、选项及评分一致。"
        "这是固定部署方案的对照，云服务和本地模型的硬件、精度与网络路径并不相同。", "",
        "| 场景或检查 | 实际覆盖 | 请求与评分口径 |",
        "|---|---|---|",
        "| 规范单指令 | S01–S10，10 条原文 Query | 每条一次回答完整 30 字段；整组命令完全匹配 |",
        "| 规范多指令 | M01–M10，10 条原文 Query | 与单指令相同；两组共同构成 20 题主成绩 |",
        "| 单步决策 | S03，30 种 Key × 3 轮 | 每次只要求回答一个字段；90 次字段准确率及单次耗时 |",
        "| 30 步串行 | 同一 S03 的上述 90 次请求 | 每 30 步合并为一轮；3 轮整组准确率及墙钟时间 |",
        "| 一次回答所有问题 | S03，3 个完整请求 | 每次回答全部 30 字段；3 轮整组准确率及请求耗时 |",
        "| 固定字段附项 | S03，仅 t_temp，独立请求 3 次 | 单独列出，不与 90 次不同字段的单步均值混用 |",
        "| 选项换序 | 规范同 20 题反转选项 | 稳定性观察，不增加独立业务场景数 |",
        "| 扩展场景 | 10 条英文诊断、24 条英文新题及对应中文翻译 | 原序/反序分别统计，不计入规范主成绩 |", "",
        "“一次回答所有问题”指同一条 Query 对应的全部 30 个 Key 选择题。"
        "“30 步串行”仍是处理这一条 Query，只是每次发送一个字段的问题；"
        "每次保留相同完整能力集，不把上一字段的选择传给下一字段。"
        "这些步骤都是模型推理，没有向真实空调执行控制。", "",
        "测试按以下过程执行，原始调用已完成；本次文档整理仅重新离线核验已有记录：", "",
        "1. 从规范提取完整能力集、英文 Query 与离线参考答案，冻结输入、候选顺序、模型版本和源码哈希。"
        "模型只收到 Query、能力集、公共规则及问题选项，标准答案不进入推理请求。",
        "2. 五个本地服务按官方可用路径部署，检查模型身份、输入长度和无静默截断；"
        "Jev 固定首个预热返回版本，GPT 使用保存的 ACTIVE Bedrock 推理配置及 low effort。",
        "3. 每模型先做 3 次 S03 完整请求预热，再按相同顺序执行 156 次质量请求："
        "40 次规范原序/反序、20 次诊断、48 次英文新题、48 次对应中文题。仅规范原序 20 次计入主成绩。",
        "4. 再对 30 个字段各预热一次，进行三轮布局计时。第 1、3 轮按“固定字段→30 步串行→全答”，"
        "第 2 轮反向排列。每模型共 33 次 HTTP 预热、252 次正式调用，即 285 次。",
        "5. 保存原始请求和响应，再离线校验模型身份、全部字段、合法候选、调用顺序及时间线；"
        "只移除 omit、按能力表补 cmdName，不修正值、不补温度单位、不删除多余动作。", "",
        "本地第一轮曾因系统自动维护中断，全部五模型随后按原冻结输入重新完整运行。"
        "本报告采用维护后的完整记录，维护前记录单独保留；不是按答案好坏挑选运行。"
        "部署版本、启动预热与中断过程见[独占 L4 部署记录](AC_CANDIDATE_L4_RESULTS.md)。", "",
        '<a id="spec-results"></a>', "",
        "## 规范主结果", "",
        "整条命令全部匹配才记正确，多发一个未要求的字段也记错。下列时间是"
        "**20 条规范原序请求各一次、每次回答全部 30 个字段**的客户端实测，含错误回答；"
        "不是固定 S03 的重复计时，也不是扩展题平均时间。", "",
        "| 模型 | 单指令 | 多指令 | 全部严格正确 | 每条完整请求均值 | P50 | P95 | 20 条请求耗时之和 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for provider, model in model_results.items():
        m = model["primary"]
        latency = m["client_ms"]
        counts = [f"{m[k]['numerator']}/{m[k]['denominator']}" for k in (
            "single_exact", "multi_exact", "exact_match")]
        text.append(f"| {NAMES[provider]} | " + " | ".join(counts) + " | "
                    + " | ".join(f"{latency[k]/1000:.3f} 秒" for k in ("mean", "p50", "p95", "total")) + " |")
    text += [
        "", "“20 条请求耗时之和”只加总这 20 次调用，不含反序、扩展题、预热、文件保存和其他间隔。"
        "请求实际按原序/反序交替执行；该列不是连续执行一遍脚本的墙钟时间。", "",
        "在这批规范题的本地候选中，Clef 为 **19/20**，KnowLine、H2O 和 Torchcast 均为 **18/20**。"
        "因此此前扩展集得出的“H2O 准确率最高”不能作为本规范的结论。"
        "KnowLine 的规范完整请求均值约 **1.046 秒**，是本轮本地候选中最快的，"
        "其多发温度及扫风字段的问题仍需处理。20 题的差距不足以证明生产可靠性。", "",
        "## Key / Value 与多余、缺失指令", "",
        "| 模型 | Key 集合全对 | Key 精确率 | Key 召回率 | 已选对 Key 的 Value 准确率 | 多余指令比例 | 缺失指令比例 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for provider, model in model_results.items():
        m = model["primary"]
        text.append(f"| {NAMES[provider]} | " + " | ".join(display_ratio(m[k]) for k in (
            "key_set_exact", "key_precision", "key_recall", "value_accuracy_given_correct_key",
            "extra_command_rate", "missing_command_rate")) + " |")
    text += [
        "", "沿用原测试评分器：Key 精确率=选对的 Key/输出 Key 数，Key 召回率=选对的 Key/40；"
        "Value 准确率以选对 Key 为条件。多余比例=(输出命令对−正确命令对)/输出命令对，"
        "缺失比例=(40−正确命令对)/40。错 Value 同时产生一个多余对和一个缺失对。"
        "条件 Value 满分不能掩盖多选、漏选 Key。", "",
        '<a id="request-layouts"></a>', "",
        "## 单步、30 步串行、一次全答：时间与准确率", "",
        f"所有模型使用规范 S03 “{s03_query}”，"
        "每种请求布局测三轮，完整状态和命令集始终保留。"
        "本节沿用此前串行补测的单步定义：30 种 Key × 3 轮，共 90 次实际单字段请求；"
        "单步均值由这 90 次请求统计，单步正确率逐字段评分。"
        "“30 步串行”将这些步骤按轮合并，统计每轮实际总时间及整组正确率；"
        "“一次回答所有问题”每轮用一个请求回答全部 30 个字段。"
        "整组正确要求 `t_temp=24`、`t_temp_type=0`，其他 28 个字段全部为 omit。", "",
        "| 模型 | 单步均值 | 单步字段正确率 | 30 步串行均值 | 串行整组正确率 | 一次全答均值 | 全答整组正确率 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for provider, model in model_results.items():
        t, a = model["s03_latency"], model["s03_mode_accuracy"]
        text.append(
            f"| {NAMES[provider]} | {t['serial30_step_ms']['mean']:.1f} ms"
            f" | {display_ratio(a['single_step_fields'])}"
            f" | {t['serial30_wall_ms']['mean']/1000:.3f} 秒"
            f" | {display_ratio(a['serial30_tasks'])} | {t['full30_ms']['mean']/1000:.3f} 秒"
            f" | {display_ratio(a['full30_tasks'])} |")
    speed_ratios = {name: m["s03_latency"]["serial30_wall_ms"]["mean"] / m["s03_latency"]["full30_ms"]["mean"]
                    for name, m in model_results.items()}
    text += [
        "", "**这是同一条业务指令的三轮重复结果。** 单步的 90 次选择中，"
        "6 次应输出温度或单位、84 次应选 omit；七个模型分别为 6/6、84/84。"
        "单步正确率与整组正确率的分母不同，单步和 30 步串行使用同一组记录，不是两套独立样本。"
        "三种方式尚未都跑完整个规范 20 题，不能用本表的 100% 代替规范主成绩。", "",
        "本场景的结论：", "",
        f"- Jev、GPT、KnowLine、Clef 一次全答均为 3/3 轮正确，相比各自 30 步串行，"
        f"串行/全答耗时比分别为 **{speed_ratios['jev']:.1f}、{speed_ratios['gpt']:.1f}、"
        f"{speed_ratios['knowline']:.1f}、{speed_ratios['clef']:.1f} 倍**。"
        "需要全部字段时，这四个服务在本场景适合一次提交。",
        "- H2O 两种布局均为 3/3 轮正确，耗时约 6.3 秒，差距很小；"
        "Torchcast 两种布局也都正确，逐字段串行约 10.818 秒，比一次全答的 12.541 秒更快。"
        "这些是当前部署路径的结果，不代表所有推理引擎都会如此。",
        "- Perplexity 单步为 90/90、串行整组为 3/3，一次全答却为 0/3："
        "三轮都额外选择 `t_outdoor_selfclean=0`。它全答的字段正确率仍有 87/90（96.7%），"
        "但每轮多发一条动作就足以使整组失败。不能只因全答更快就认为它更适用。", "",
        "另有一个固定 `t_temp` 字段的 3 次独立请求，七个模型均为 3/3 正确。"
        "这项更小的样本与上表覆盖 30 种 Key 的单步均值分别列出；"
        "下面保留原始计时范围，便于核对波动。逐字段各步不传入前一步的选择，"
        "30 步期间不写盘、不上传证据，整轮结束后才保存。", "",
        "| 模型 | 独立 t_temp 均值 | 串行每步均值（90 次） | 30 步实际总时间均值 | 总时间范围 | 一次完整请求均值 | 串行/完整答对轮数 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for provider, model in model_results.items():
        t = model["s03_latency"]
        serial = t["serial30_wall_ms"]
        layouts = model["s03_layout_comparison"]
        text.append(
            f"| {NAMES[provider]} | {t['single_key_ms']['mean']:.1f} ms"
            f" | {t['serial30_step_ms']['mean']:.1f} ms | {serial['mean']/1000:.3f} 秒"
            f" | {serial['min']/1000:.3f}–{serial['max']/1000:.3f} 秒"
            f" | {t['full30_ms']['mean']/1000:.3f} 秒"
            f" | {sum(r['serial_correct'] for r in layouts)}/3 · {sum(r['full_correct'] for r in layouts)}/3 |")
    text += [
        "", "S03 三轮只用于解释请求布局与耗时，**不能把主表 20 题准确率套给逐字段串行模式**。"
        "时间表示收到回答，并不保证回答正确。"
        "完整请求中的模型内部批处理、联合字段评分或选项分组仍使用各自原生实现。", "",
        "### 实际请求、选项与选择示例", "",
        f"[S03 完整请求]({link}/examples/S03.request.json)包含全部状态、30 个问题及各自完整选项。"
        "例如 `t_temp` 的候选包含整个合法温度区间和 omit；模型应选字符串 `24`。"
        "`t_temp_type` 应选 `0`（摄氏），其余字段选 omit。"
        "omit 表示不下发，数值 `0` 则是实际设置，二者含义不同。", "",
        "| 模式 | 发给模型的内容 | 如何得到最终命令 |",
        "|---|---|---|",
        "| 单步示例 | 完整状态与能力集，只保留 t_temp 的一个问题及全部选项 | 记录该次选择 24 及单次耗时 |",
        "| 30 步串行 | 将 30 个字段的问题逐个发送，每步都保留完整状态与能力集 | 收齐 30 个选择后移除 omit，得到两条温度命令 |",
        "| 一次全答 | 同一状态与能力集，一次携带全部 30 个字段问题 | 一个响应含 30 个选择，同样移除 omit 后评分 |", "",
        "每个文件均摘录第一轮真实记录，包含单步示例、完整 30 步请求/响应、整轮计时和一次全答响应；"
        "`expected_local_only` 是导出文件中的离线参考，未发给模型：", "",
        " · ".join(f"[{NAMES[p]}]({link}/examples/{p}-S03.layouts.json)" for p in model_results), "",
        "## 逐题选择与错误", "",
        "| 用例 | Query | 标准命令 | " + " | ".join(NAMES.values()) + " |",
        "|---|---|---|" + "---|" * len(NAMES),
    ]
    refs = json.loads((root / "spec_references.json").read_text())
    for index, ref in enumerate(refs):
        cells = []
        for model in model_results.values():
            row = model["primary_rows"][index]
            if row["correct"]:
                cells.append("正确")
            else:
                extra = ", ".join(f"{k}={v}" for k, v in row["extra"])
                missing = ", ".join(f"{k}={v}" for k, v in row["missing"])
                cells.append("；".join(s for s in (
                    "多发 " + extra if extra else "", "漏发 " + missing if missing else "",
                    row["status"] if row["status"] != "ok" else "") if s))
        text.append(f"| {ref['id']} | {ref['query']} | {display_commands(ref['expected'])} | "
                    + " | ".join(cells) + " |")
    text += [
        "", f"每题的[完整请求与所有选项]({link}/examples/)均已导出；S01、S04、M08"
        "另保存各模型原始响应。所有 20 题的实际命令、Key/Value 选择和差异见 "
        f"[summary.json]({link}/summary.json)，全部原始响应位置及哈希见 "
        f"[audit.json]({link}/audit.json)。", "",
        "M08 按规范只允许 `t_up_down=1`、`t_swing_direction=2`；"
        "多选 `t_swing_angle=0` 仍记错误。虽然其显示名称包含 up/down swing，"
        "本轮遵循规范标准答案，不临时放宽为其他等效动作。", "",
        '<a id="model-differences"></a>', "",
        "## 为什么不同模型的速度与选择不一样", "",
        "### 请求数与内部计算量不同", "",
        "客户端只发一个完整请求，不代表服务只做一次模型计算。"
        "本任务每次携带完整能力说明，部分字段还有大量数值候选。"
        "逐字段请求可能反复处理这些内容；一次全答是否节省时间，取决于服务如何共享计算和调度问题。"
        "本轮统一了外部请求串行，但保留各模型原生服务内部的批处理与并行。", "",
        "| 模型 | 已核对的实现或配置 | 与本次结果的关系及解释边界 |",
        "|---|---|---|",
        "| Jev | 原生托管 API，固定返回 jev-1.14.0 | "
        "S03 串行 1.925 秒、全答 0.094 秒，观察到明显的整体请求优势。"
        "记录没有托管侧硬件、内部算法或缓存明细，不能断言快在某种架构 |",
        "| GPT low | 一次生成包含全部字段选择的 JSON；每次显式 low effort | "
        "全答减少重复请求与重复生成过程，S03 从串行 24.876 秒降至 1.970 秒。"
        "生成一个响应仍可能包含多次计算；原生缓存用量有记录，收益未单独隔离 |",
        "| Clef-Flash | 联合 schema head 在一次前向中评分全部问题；本轮为 9B BF16 Python/Transformers | "
        "共享计算与全答约 4.4 倍的整体时间优势相符。L4 上全答约 3.297 秒；"
        "未测官方面向 H200 等硬件的专用 SGLang 路径，不能据此认定其所有部署都慢 |",
        "| KnowLine | 每题分别前向；官方 SGLang 0.5.21、FP8、前端 16 个评分线程，"
        "保留缓存及 read-twice 策略 | "
        "一个外部请求内可调度多个评分任务并利用缓存，S03 全答约 0.712 秒。"
        "仍不是全部 30 题一次前向；串行三轮为 1.612–5.431 秒，不能只用最快一轮推断稳定延迟 |",
        "| H2O | 每字段产生评分任务；前端可提交多个任务，"
        "当前双向注意力引擎设置 max-num-seqs=1、eager、FP8 | "
        "引擎同时处理的序列数受限，双向模式每题重读状态，无法直接使用因果前缀复用。"
        "S03 全答 6.239 秒、串行 6.361 秒，封装为一次请求未明显减少主要计算成本 |",
        "| Torchcast | 官方图快速路径有问题数/长度限制；超过 26 个候选采用分组初选及终选 | "
        "完整 30 字段展开为 39 个评分输入，并可能与单字段走不同图执行路径。"
        "本次全答 12.541 秒慢于串行 10.818 秒；单字段也使用候选分组，"
        "不能只凭 39 与 30 的差就认定原因，具体耗时贡献尚未隔离 |",
        "| Perplexity Flash | 全部问题共享一条序列并可相互看到；官方 fast=True、BF16、编译与 CUDA graphs | "
        "全答共享计算，与 1.551 秒相对串行 10.921 秒的优势相符；"
        "但问题间上下文和执行形状也发生变化，本例全答多发室外自清洁关闭命令 |", "",
        "模型卡、固定源码版本及官方部署链接见[候选模型研究](AC_MODEL_CANDIDATES.md)，"
        "实际精度、启动参数与输入长度见[部署记录](AC_CANDIDATE_L4_RESULTS.md)，"
        "H2O 的注意力与缓存说明见[官方文档核对](H2O_OFFICIAL_GUIDANCE.md)。"
        "上述机制能解释方向，未通过单变量实验测出各机制分别贡献了多少毫秒。"
        "模型参数更少、只输出选项，均不保证完整 30 字段端到端比 GPT 快。", "",
        "### 答案差异集中在“该不该下发这个字段”", "",
        "本批七模型都选中了规范要求的全部 40 对 Key/Value；失败来自额外命令。"
        "例如 H2O 开机时额外切到制冷、KnowLine 设置华氏 68 度时额外下发摄氏 20 度、"
        "Torchcast 分别开启室内和室外自清洁时额外触发一键清洁。"
        "这些选择与用户提到的功能相关，但未满足“仅输出规范要求动作”的完整匹配要求。", "",
        "完整能力目录包含许多语义相近的字段，而 `omit`、关闭值 `0`、保持现状分别代表不同含义；"
        "提示词和选项的表达确有优化空间。摆风多个编码尤其需要明确优先关系。"
        "但同一输入下 GPT 能达到 20/20，说明不能将所有错误都归因于题目没有明确答案；"
        "也不能从输出倒推出模型内部的具体思考或训练原因。", "",
        "Perplexity 的 S03 是布局影响选择的直接例子：逐字段时室外自清洁为 omit，"
        "一次全答时为 `0`，三轮均如此。共同上下文变化和 BF16/执行形状变化都可能影响临界选择；"
        "本轮未将二者分开实验，不能确定哪一项造成翻转。"
        "合法选项、较高字段准确率及接口成功，都不等于完整任务正确。", "",
        "## 统一方式与保留的部署差异", "",
        "- 每条 Query 完整照搬规范；全模型共享完整能力集、相同 baseline 规则、"
        "字段说明、全部合法选项及 omit。规范 §2.2 允许转为 Decider 选择题格式。"
        "自动除霜清洁状态值 2–4 保留在能力表，但按规范不作为可下发选项；"
        "范围枚举完整整数区间，本批规范未测试小数。",
        "- 各字段必须返回一个合法字符串候选。只移除 omit、按能力表补 cmdName；"
        "不补单位、不删除多余动作、不裁剪错误值。参考答案只用于离线评分。",
        "- GPT 系统提示仅规定读取输入与 JSON 输出格式，不额外增加空调规则。"
        "Jev 使用原生接口，请求 `jev-latest`，以第一次预热返回版本锁定其余响应；"
        f"本次返回 `{model_results['jev']['model']}`。GPT 模型身份由请求 modelId 和保存的 ACTIVE "
        "Bedrock inference profile 核验；Converse 返回本身不回显模型 ID。",
        "- 所有外部请求串行、各模型测试窗口不重叠、无自动重试。"
        "每模型均为 3 次完整 S03 预热→同序 156 次质量请求→30 次单字段预热→3 轮布局计时。"
        "保留扩展请求是为了与已测模型保持相同的请求与预热历史；主成绩始终只取规范原序 20 题，"
        "反序 20 题和非规范 116 次请求分别留作附项。",
        "- 本地模型在独占 L4 上通过 loopback 调用；Jev 为 HTTPS 云服务，GPT 为 Bedrock Converse，"
        "从现有测试主机调用。主表均报告客户端请求往返，保留网络、SDK、部署引擎和精度差异，"
        "不能将其解释成相同硬件上的纯推理速度。完整相同任务不等于服务基础设施相同。",
        "- 各原生服务保留自身缓存；GPT usage 与 Jev 原始响应完整保存。"
        "相同预热序列不保证不同提供方有相同缓存命中状态。"
        "Clef 会按选项 ID 排序，反转字典不能验证其模型对候选位置的敏感度。", "",
        "反序稳定性附项（同一批 20 题，不增加独立样本数）：", "",
        "| 模型 | 原顺序 | 反顺序 |", "|---|---:|---:|",
    ]
    for provider, model in model_results.items():
        text.append(f"| {NAMES[provider]} | {display_ratio(model['primary']['exact_match'])}"
                    f" | {display_ratio(model['reversed']['exact_match'])} |")
    text += [
        "", '<a id="supplementary"></a>', "",
        "## 扩展场景：英文诊断、新问题与中文翻译", "",
        "这些请求与规范题使用相同 baseline、完整 30 字段和严格整组评分。"
        "英文诊断 10 条来自前期错误分析；英文新题为此前提前冻结的 24 条，中文为其对应翻译，"
        "规则与能力表仍使用英文。它们用于观察表达与业务边界，不能作为新的独立盲测或与规范成绩混算。"
        "原序和反序是同题重复，英文及其中文翻译也不是完全独立的业务案例。", "",
        "| 模型 | 英文诊断：原序 / 反序 | 英文新题：原序 / 反序 | 中文翻译：原序 / 反序 |",
        "|---|---:|---:|---:|",
    ]
    for provider, model in model_results.items():
        cells = []
        for dataset in ("extension", "validation", "chinese"):
            counts = [model["supplementary_by_dataset"][dataset][order]["exact_match"]
                      for order in ("original", "reversed")]
            cells.append(" · ".join(f"{r['numerator']}/{r['denominator']}" for r in counts))
        text.append(f"| {NAMES[provider]} | " + " | ".join(cells) + " |")
    text += [
        "", "附项耗时为各数据集**原序**完整请求的客户端均值，保留错误回答；"
        "每条 Query 只测一次，不含反序、预热或布局重复。", "",
        "| 模型 | 英文诊断（10 次） | 英文新题（24 次） | 中文翻译（24 次） |",
        "|---|---:|---:|---:|",
    ]
    for provider, model in model_results.items():
        cells = [f"{model['supplementary_by_dataset'][d]['original']['client_ms']['mean']/1000:.3f} 秒"
                 for d in ("extension", "validation", "chinese")]
        text.append(f"| {NAMES[provider]} | " + " | ".join(cells) + " |")
    text += [
        "", "中文 Z05“开启上下连续扫风，保持左右风向不变。”只要求 `t_up_down=1`。"
        "原序 H2O 与 KnowLine 都多选 `t_swing_angle=0`，KnowLine 还多选 `t_swing_direction=0`。"
        "Clef 在规范为 19/20，但原序诊断、新题、中文分别为 7/10、19/24、18/24，"
        "因此规范高分和作者家电基准都不足以替代不同表达的验证。"
        "本地五模型的完整扩展逐题选择见[扩展原始结果]"
        "(../validation/ac_control/runs/2026-10-30-candidates-l4-v1/RESULTS.zh.md)，"
        f"七模型分项及原始响应入口见 [summary.json]({link}/summary.json)。", "",
        '<a id="conclusions"></a>', "",
        "## 结论、优化方向与历史实验", "",
        "| 使用侧重点 | 本批结果支持的选择 | 尚需解决的问题 |",
        "|---|---|---|",
        "| 规范准确率优先，可调用云 API | GPT low 为 20/20；20 条完整请求均值 2.777 秒 | "
        "仅 20 条规范题，需更多未见表达验证；不代表生产准确率 100% |",
        "| 云 API 低延迟 | Jev 为 19/20，规范完整请求均值 0.095 秒 | "
        "需修复摆风多余动作；历史规则澄清有收益，不能直接填入本轮 baseline 成绩 |",
        "| 本地部署，规范准确率优先 | Clef 为 19/20，完整请求均值 3.241 秒 | "
        "扩展表达有退步，仍需处理摆风多选；专用引擎在 L4 的效果未测 |",
        "| 本地部署，延迟优先 | KnowLine 为 18/20，完整请求均值 1.046 秒 | "
        "处理多发温度、摆风和保持不变语义，并确认缓存波动下的持续延迟 |",
        "| 保留质量与运行时对照 | H2O 为 18/20；本地五模型混合扩展 156 次中得分最高 | "
        "当前完整请求约 6 秒，先前提速设置曾引入新错；需同时验收质量与速度 |",
        "| 当前协议下暂不优先 | Torchcast 为 18/20 且最慢；Perplexity 为 1/20 | "
        "分别定位多字段推理成本和多余动作，不能用榜单分数或单字段满分代替整组验收 |", "",
        "需要完整 30 字段时，本场景优先采用 Jev、GPT、KnowLine、Clef 的一次全答方式；"
        "H2O 全答节省很少，Torchcast 当前路径反而串行较快，Perplexity 必须先解决布局改变答案的问题。"
        "如果业务只需要一个字段，可以只请求该字段，但完整控制任务仍需检查温度单位等伴随动作。", "",
        "后续优化应先固定验收含义，再逐项验证：明确 omit 与关闭值、保持不变及摆风编码；"
        "分别比较规则澄清、问题拆分和引擎设置；在全部规范 20 题与冻结的新题上同时检查"
        "多余/缺失动作和延迟。特别是三种布局尚未全部覆盖 20 题，"
        "这是判断“串行是否整体更准”前仍缺少的对照。这里列出建议，本次整理未新增测试。", "",
        "### 与此前五模型实验的关系", "",
        "本轮七模型只比较同一 baseline，未将五种提示词/流程方案重新跑遍全部七模型。"
        "Strands Decider 和 Liquid 仅出现在历史实验；当前新增了 Perplexity、KnowLine、Torchcast 与 Clef。"
        "旧实验用原常驻服务，新本地测试用独占 L4、固定新运行时；"
        "旧串行补测预热较少，整轮计时还包含中间日志开销，所以新旧时间分别保留。", "",
        "| 历史实验 | 已有发现 | 与本轮的关系 |",
        "|---|---|---|",
        "| [五模型提示词与流程对照](AC_CONTROL_COMPARISON.md) | "
        "比较基线、仅改选项、仅改规则、合并改写及两阶段；Jev 仅改规则为 20/20，"
        "H2O 两阶段为 20/20，但诊断题有回退 | 历史输入方案的结果，不能冒充本轮统一 baseline |",
        "| [原五模型串行补测](AC_CONTROL_COMPARISON.md#单任务串行与单key串行的补测) | "
        "覆盖 Strands、Liquid、H2O、Jev、GPT 的 S03 单字段/串行/全答 | "
        "已有题目与计时解释保留，本轮七模型时间以上表为准 |",
        "| [Liquid 准确率优化](LIQUID_AC_OPTIMIZATION.md) | "
        "最佳开发方案原规范 16/20，但冻结新题 12/24 与原两阶段持平且更慢，未采用 | "
        "说明开发题收益需经过新表达检验；Liquid 未纳入本轮七模型 |",
        "| [H2O 运行时优化](H2O_OPTIMIZATION.md)及[官方建议补测](H2O_OFFICIAL_OPTIMIZATION.md) | "
        "编译/因果路径可降低耗时，但有新增错误；小幅图优化未达到采用条件 | "
        "原配置已恢复，本轮没有按历史最快配置替换主结果 |", "",
        "两阶段是先对 30 个 Key 判断 apply/omit，再为模型选中的字段选 Value；"
        "30 步串行则是每次直接选择一个字段的 Value/omit。"
        "两者改变的决策流程不同，阶段数与字段请求数不能混为一谈。", "",
        "## 审计与复现", "",
        f"七模型共 {result['observed_calls']:,} 次实测调用，其中 {result['formal_calls']:,} 次正式、"
        f"{result['warmup_calls']} 次预热；接口/格式错误 {result['errors']} 次、外部请求重叠 0 次。"
        f"Jev/GPT 新增 {result['new_calls']} 次，其余来自已核验的 L4 完整运行。"
        "上轮维护中断前的 638 次归档调用不混入本轮主比较；原记录及中断解释仍保留。", "",
        f"[冻结计划、规范快照与新增原始响应]({link}/) · "
        "[本地模型版本、部署路径及维护记录](AC_CANDIDATE_L4_RESULTS.md) · "
        "[选型资料](AC_MODEL_CANDIDATES.md)。"
        "OpenAI 官方模型页确认 [GPT-6.1 Sol 支持 low reasoning effort]"
        "(https://developers.openai.com/api/docs/models/gpt-6.1-sol)。", "",
        "仅离线重新审计与生成主报告（不会发推理请求）：", "",
        "```bash",
        "python validation/ac_control/report_spec_unified.py",
        "```", "",
        "文档整理仅离线核验已有记录，未新增推理调用，也未重新启动已停止的新增 L4 实例。", "",
    ]
    (ROOT / "docs/AC_SPEC_UNIFIED_RESULTS.md").write_text("\n".join(text))
    (root / "RESULTS.zh.md").write_text(
        "# 空调控制七模型对照\n\n主报告见 "
        "[测试过程、各场景结果与差异解释](../../../../docs/AC_SPEC_UNIFIED_RESULTS.md)。"
        "\n\n[逐题评分](summary.json) · [审计](audit.json) · [完整问题与回答](examples/)\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=HERE / "runs/2026-10-30-spec-unified-v1")
    args = parser.parse_args()
    result = audit(args.run)
    render(args.run, result)
    print(json.dumps({
        name: {"exact": model["primary"]["exact_match"],
               "full_request_mean_ms": model["primary"]["client_ms"]["mean"],
               "errors": model["errors"]}
        for name, model in result["models"].items()
    }, ensure_ascii=False, indent=2))
