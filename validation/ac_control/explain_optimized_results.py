"""Add measured tradeoffs, an error example and experiment wall time to the report."""

import argparse
import json
from datetime import datetime
from pathlib import Path

from all_models_protocol import PROVIDERS, digest, save, stamp
from optimized_all_models_protocol import ROOT
from report_all_models import NAMES, receipt_bytes
from report_optimized_models import PROJECT, render

PROFILES = ("baseline", "compact_catalog", "schema_once")


def minutes(start, end):
    return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() / 60


def explain(root):
    result = json.loads((root / "summary.json").read_text())
    assert result["complete"] and result["completed_profile_models"] == 27
    assert result["calls"] == 55323 and result["total_calls_including_predecessor"] == 57372
    profiles = result["profiles"]
    baseline_cases = json.loads((root / "profiles/baseline/cases.json").read_text())
    compact_cases = json.loads((root / "profiles/compact_catalog/cases.json").read_text())
    assert all(a["payload"]["state"] == b["payload"]["state"]
               for a, b in zip(baseline_cases, compact_cases, strict=True))
    path = render(root, result)
    link = "../validation/ac_control/runs/" + root.name

    def pct(value):
        return f"{value * 100:.1f}%"

    def pair(model):
        layout = model["layouts"]
        return f"{pct(layout['full_accuracy']['rate'])} / {pct(layout['serial_accuracy']['rate'])}"

    gpt_before = profiles["baseline"]["gpt"]
    gpt_after = profiles["schema_once"]["gpt"]
    assert all(profiles[p]["gpt"]["layouts"][layout + "_accuracy"]["rate"] == 1
               for p in PROFILES for layout in ("full", "serial"))
    gpt_tokens_before = gpt_before["tokens"]["full"]["input"]["mean"]
    gpt_tokens_after = gpt_after["tokens"]["full"]["input"]["mean"]
    lines = [
        "## 先看结论", "",
        "**不建议把这两种压缩写法作为九模型统一的默认输入：多数模型虽然更快，"
        "完整任务准确率却明显下降。** 保留完整能力表，并不足以替代清晰的局部任务指令和 omit 条件。", "",
        "GPT 的三种输入在规范场景的全答和串行测试中均为 100%。"
        f"紧凑表版本的全答平均输入从 {gpt_tokens_before:,.1f} 降至 {gpt_tokens_after:,.1f} tokens"
        f"（减少 {pct(1 - gpt_tokens_after / gpt_tokens_before)}），"
        f"耗时从 {gpt_before['layouts']['full_ms']['mean']/1000:.3f} 秒变为 "
        f"{gpt_after['layouts']['full_ms']['mean']/1000:.3f} 秒。"
        "它保住了本批场景的准确率并节省输入 tokens，但本轮没有体现出端到端加速。", "",
        "这轮实验验证了两种具体的输入压缩写法。能力表、候选和离线判分标准保持完整，"
        "**是否适合采用仍须看实际准确率，不能仅凭 tokens 减少判断优化成功。**", "",
        "下表依次为“一次全答 / 30 步串行”的完整任务准确率；每项分母均为 60。", "",
        "| 模型 | 原始输入 | 精简问题与选项 | 再将能力表改成紧凑表 |",
        "|---|---:|---:|---:|",
    ]
    for provider in PROVIDERS:
        lines.append("| " + NAMES[provider] + " | "
                     + " | ".join(pair(profiles[p][provider]) for p in PROFILES) + " |")
    lines += ["", "原始输入也有失败，保留原始写法不代表该模型已满足实际设备控制的可靠性要求。"
              "这些题已用于历史测试，结论限定于本次用例及固定部署。", ""]
    original = path.read_text()
    heading, rest = original.split("\n", 1)
    path.write_text(heading + "\n\n" + "\n".join(lines) + "\n" + rest)

    # Use a fixed specification case, chosen before this comparison, for the explanation.
    refs = json.loads((root / "profiles/baseline/spec_references.json").read_text())
    reference = next(r for r in refs if r["id"] == "S03")
    examples = {}
    for profile in PROFILES:
        folder = root / "profiles" / profile / "results/knowline"
        rows = [json.loads(line) for line in receipt_bytes(folder).splitlines()]
        row = next(r for r in rows if r["case_id"] == "S03" and r["kind"] == "full30" and r["repetition"] == 0)
        item = {
            "purpose": "Offline explanation; expected answers were not sent to the model.",
            "profile": profile, "expected_commands": reference["expected"], "receipt": row,
        }
        save(root / "examples" / ("S03.knowline." + profile + ".observed.json"), item)
        examples[profile] = row

    lines = [
        "## 单指令、多指令与尾部延迟", "",
        "单指令/多指令指 Query 的类别；两类请求均保留全部 30 个字段。"
        "例如 S03 是单指令，但正确输出包含温度和温标两个字段。"
        "每类 10 个场景重复三轮，以下准确率的分母均为 30。", "",
        "| 模型 / 输入 | 全答：单指令 | 全答：多指令 | 串行：单指令 | 串行：多指令 | 全答 p95 秒 | 串行 p95 秒 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for provider in PROVIDERS:
        for profile in PROFILES:
            model = profiles[profile][provider]
            categories = model["layouts_by_category"]
            accuracy = [categories[c][layout + "_accuracy"]["rate"]
                        for layout in ("full", "serial") for c in ("single", "multi")]
            lines.append(f"| {NAMES[provider]} / {profile} | "
                         + " | ".join(pct(value) for value in accuracy)
                         + f" | {model['layouts']['full_ms']['p95']/1000:.3f}"
                         + f" | {model['layouts']['serial_ms']['p95']/1000:.3f} |")
    lines += ["", "预热不计入这些延迟分布。正式请求出现的较慢调用保留在统计中，"
              "没有按耗时删除异常点。", "",
        "## 为什么保留完整能力表，准确率仍会下降", "",
        "第一种压缩 `compact_catalog` 的 state 与 baseline 完全相同，"
        "变化只发生在问题说明和候选描述；第二种压缩才进一步改变能力表的表示。"
        "因此，第一种方案出现的退步已经说明：保留信息并不等于保持模型对任务的理解。", "",
        "以 Power 字段为例，原始问题显式要求从 query 选择请求的值，未请求则选 omit；"
        "精简后主要保留名称和功能区分，选择规则集中在公共 state。omit 的描述也从"
        "“Do not send t_power: Power is not requested.” 缩为 “No change.”。"
        "全局规则仍存在，但局部任务指令的重复和候选措辞对这些模型可能很重要。"
        "本轮同时改动了问题指令和选项描述，没有单独隔离其中某一句的因果作用。"
        "这两种写法精简得较激进；实验未覆盖“只压缩能力表、保留原始问题和 omit 描述”，"
        "因此不能据此认定所有输入压缩都无效。后续应先做小规模单因素对照，"
        "通过准确率检查后再做完整耗时测试。", "",
        f"固定示例 S03：`{reference['query']}`。标准答案只包含 "
        "`t_temp=24` 和 `t_temp_type=0`。以下为 KnowLine 每个版本第一次正式全答的实际结果：", "",
        "| 输入 | 模型实际输出的命令 |",
        "|---|---|",
    ]
    for profile, row in examples.items():
        commands = ", ".join(f"{c['cmdKey']}={c['cmdValue']}" for c in row["commands"]) or "无"
        lines.append(f"| {profile} | `{commands}` |")
    lines += ["", "完整请求、全部选项及原始响应："
              + " · ".join(f"[{p}]({link}/examples/S03.knowline.{p}.observed.json)" for p in PROFILES), ""]
    lines += [
        "下面按 20 个规范场景、原始选项顺序的质量请求统计错误类型。"
        "每格依次为“出现额外字段的场景数 / 漏掉字段的场景数”；"
        "同一场景可能同时计入两类，不能将两数相加当作失败总数。"
        "字段选择正确但值错误另见核算结果的 `value_accuracy_given_correct_key`。", "",
        "| 模型 | 原始输入：多发 / 漏发 | 精简问题：多发 / 漏发 | 紧凑能力表：多发 / 漏发 |",
        "|---|---:|---:|---:|",
    ]
    for provider in PROVIDERS:
        metrics = [profiles[p][provider]["quality"]["spec"]["original"] for p in PROFILES]
        lines.append("| " + NAMES[provider] + " | "
                     + " | ".join(f"{m['cases_with_extra']} / {m['cases_with_missing']}"
                                  for m in metrics) + " |")
    lines += ["", "例如 KnowLine 的压缩版仍选对了用户明确要求字段的值，"
              "却增加了未要求的设置。按原规范，这些额外动作必须算错；"
              "不能事后用规则删除它们来提高本轮成绩。", ""]

    layout_proofs = json.loads((root / "knowline-input-layout-analysis.json").read_text())
    for profile in PROFILES:
        proof = layout_proofs[profile]
        model = profiles[profile]["knowline"]
        assert proof["all_reconstructed_counts_match_recorded_usage"]
        assert proof["matched_actual_requests"] == 1860 and proof["checked_layouts"] == 620
        assert proof["receipts_sha256"] == model["receipts_sha256"]
        assert proof["cases_sha256"] == digest(root / "profiles" / profile / "cases.json")
        assert proof["model_inference_calls"] == 0
    lines += ["## tokens 减少为什么没有等比例加速", "",
              "- 九模型的 usage 口径不同，横向比较绝对 tokens 不能直接比较计算量。"
              "本报告的压缩比例均在同一模型内计算。",
              "- 每个版本仍有相同的 30 个字段和 283 个候选；前向次数、候选评分、"
              "分组选择、CPU/HTTP 开销及固定图长度不会随文本长度同比缩小。",
              "- Perplexity 沿用官方 CUDA graph 的固定长度桶（2,048/4,096/8,192/16,384）。"
              "输入缩短未必改变执行所用的桶。",
              "- GPT 仍需输出同样的字段 JSON。其报告的输入量包含缓存读写；"
              "减少逻辑输入量不代表每次都减少相同数量的实际预填充计算。",
              "- KnowLine 三个版本的实际 prompt 均已离线重建：每版本核对 1,860 次正式请求，"
              "tokens 全部匹配。此次全答均未重复输入，600 种单字段布局均重复输入，"
              "没有因压缩跨过 read-twice 阈值；同一布局压缩前后的准确率变化"
              "不能归因于这项开关切换。", "",
              f"[KnowLine 三版本 prompt 与 tokens 核验]({link}/knowline-input-layout-analysis.json)", ""]
    assert all(p["full30_read_twice"] == 0 and p["single_read_twice"] == 600 for p in layout_proofs.values())
    lines += ["H2O 的两种输入计数也分开列出，均为正式一次全答的均值：", "",
              "| 输入版本 | 逻辑 input_tokens | 累计 processed_input_tokens |",
              "|---|---:|---:|"]
    for profile in PROFILES:
        usage = profiles[profile]["h2o"]["tokens"]["full"]
        cells = [usage[key]["mean"] for key in ("input", "processed_input")]
        lines.append(f"| {profile} | "
                     + " | ".join("未报告" if value is None else f"{value:,.1f}" for value in cells) + " |")
    h2o_before = profiles["baseline"]["h2o"]
    h2o_after = profiles["schema_once"]["h2o"]
    reductions = [
        1 - h2o_after["tokens"]["full"][key]["mean"] / h2o_before["tokens"]["full"][key]["mean"]
        for key in ("input", "processed_input")
    ]
    latency_reduction = 1 - h2o_after["layouts"]["full_ms"]["mean"] / h2o_before["layouts"]["full_ms"]["mean"]
    lines += ["", f"以 H2O 紧凑表版本为例，逻辑输入减少 {pct(reductions[0])}，"
              f"接口报告的累计处理计数减少 {pct(reductions[1])}，"
              f"一次全答平均耗时减少 {pct(latency_reduction)}。"
              "因此，直接用逻辑输入的压缩比例预测端到端加速，会高估本轮收益；"
              "累计处理计数本身也不等同于 GPU FLOPs。", ""]

    models = [m for values in profiles.values() for m in values.values()]
    begin, end = min(m["started_at"] for m in models), max(m["finished_at"] for m in models)
    profile_minutes = sum(minutes(m["started_at"], m["finished_at"]) for m in models)
    startup = json.loads((root / "operations/start-decider-input-optimization.status.json").read_text())
    first_gpu = profiles["schema_once"]["decider"]["started_at"]
    lost = minutes(startup["ExecutionEndDateTime"], first_gpu)
    predecessor_meta = json.loads((root / "attempts/schema-once-distributed-v1/results/jev/run.json").read_text())
    predecessor_minutes = minutes(predecessor_meta["started_at"], predecessor_meta["finished_at"])
    timing = {
        "recorded_at": stamp(), "first_final_profile_started_at": begin, "last_final_profile_finished_at": end,
        "elapsed_minutes": minutes(begin, end), "sum_final_profile_wall_minutes": profile_minutes,
        "discarded_predecessor_wall_minutes": predecessor_minutes, "avoidable_controller_idle_minutes": lost,
        "other_startup_archive_transition_minutes": minutes(begin, end) - profile_minutes - predecessor_minutes - lost,
    }
    assert timing["other_startup_archive_transition_minutes"] >= 0
    save(root / "experiment-wall-time.json", timing)
    lines += ["## 整轮实验为何耗时较长", "",
              "整轮实验耗时与单次决策延迟分开核算。之前九模型共 18,441 次调用，"
              "本轮对照为 55,323 次，另有一次不计入最终成绩的 Jev 早期试跑 2,049 次。"
              "每版本的 2,049 次仍由 1,800 次单字段、156 次质量、60 次正式全答和 33 次预热组成。", "",
              f"从首个对照开始到最后一个对照结束，共 **{timing['elapsed_minutes']/60:.2f} 小时**。"
              f"其中 27 组脚本运行时间合计 {profile_minutes/60:.2f} 小时，"
              f"早期 Jev 试跑 {predecessor_minutes:.2f} 分钟，"
              f"调度中断导致额外空等 **{lost:.2f} 分钟**，"
              f"其他启动、归档和阶段切换约 {timing['other_startup_archive_transition_minutes']:.2f} 分钟。", "",
              "调度脚本曾在 SSM 命令提交后过早查询状态，将暂时查不到记录误判为失败。"
              "Strands 实际已启动，直到恢复调度才开始推理。修复只涉及基础设施轮询和断点恢复，"
              "没有改动冻结推理代码，也没有重试模型请求。故障记录已保留，未算入模型响应时间。", "",
              "托管 API 与 GPU 也采用全局串行，使总时间累加；独立资源本可并行，"
              "同时保持单模型请求串行。本轮保留既定顺序，以便所有数据使用同一协议。"
              "此次 EC2 按用户要求保留运行，自动停机已取消。", "",
              f"[整轮墙钟核算]({link}/experiment-wall-time.json) · "
              f"[调度修复记录]({link}/infrastructure/ssm-controller-recovery.json)", ""]
    path.write_text(path.read_text() + "\n" + "\n".join(lines))
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=ROOT)
    print(explain(parser.parse_args().run))
