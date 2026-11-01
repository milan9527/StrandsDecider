"""Offline exact-command scoring, integrity checks and a concise experiment report."""
import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

from infra import HERE, ROOT, save, stamp


def percentile(values, p=0.95):
    values = sorted(values)
    pos = (len(values)-1)*p
    lo = math.floor(pos)
    return values[lo] + (values[min(lo+1, len(values)-1)]-values[lo])*(pos-lo)


def summarize(rows):
    return {
        "tasks": len(rows), "correct": sum(r["correct"] for r in rows),
        "accuracy": sum(r["correct"] for r in rows)/len(rows),
        "extra": sum(r["extra"] for r in rows), "missing": sum(r["missing"] for r in rows),
        "active_correct": sum(r["active_correct"] for r in rows),
        "active_total": sum(r["active_total"] for r in rows),
        "omit_correct": sum(r["omit_correct"] for r in rows),
        "omit_total": sum(r["omit_total"] for r in rows),
        "wall_mean_ms": statistics.mean(r["wall_ms"] for r in rows),
        "wall_p95_ms": percentile([r["wall_ms"] for r in rows]),
        "errors": sum(r["status"] != "ok" for r in rows),
    }


def analyze():
    complete = json.loads((ROOT / "evaluation/complete.json").read_text())
    assert complete["tasks"] == complete["expected_tasks"]
    heldout = {r["id"]: r for r in json.loads((ROOT / "test.json").read_text())}
    historical = {r["id"]: r for r in json.loads((ROOT / "historical-references.json").read_text())}
    schedule = json.loads((ROOT / "evaluation/schedule.json").read_text())
    requests = {(r["id"], r["order"]): r["request"] for r in schedule}
    rows, raw_rows = [], []
    for line in (ROOT / "evaluation/receipts.jsonl").read_text().splitlines():
        raw_rows.append(json.loads(line))
    assert len(raw_rows) == complete["expected_tasks"]
    groups = defaultdict(list)
    single = defaultdict(list)
    previous_finish, call_count = -math.inf, 0
    for raw in raw_rows:
        req = requests[(raw["id"], raw["order"])]
        expected = heldout[raw["id"]]["labels"] if raw["dataset"] == "heldout" else {
            key: next((str(c["cmdValue"]) for c in historical[raw["id"]]["expected"]
                       if c["cmdKey"] == key), "omit") for key in req["questions"]
        }
        observed = {}
        for call in raw["calls"]:
            call_count += 1
            assert call["started_perf"] >= previous_finish, "Overlapping inference"
            previous_finish = call["finished_perf"]
            payload = req if raw["layout"] == "full30" else {
                "state": req["state"], "questions": {call["key"]: req["questions"][call["key"]]}}
            wire = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
            assert hashlib.sha256(wire).hexdigest() == call["input_sha256"]
            if call["status"] != "ok":
                continue
            got = {k: a["choice"] for k, a in call["raw"]["answers"].items()}
            assert set(got) == set(payload["questions"])
            assert not set(got) & set(observed)
            assert all(v in payload["questions"][k]["criteria"] for k, v in got.items())
            observed.update(got)
            if raw["kind"] == "performance" and raw["layout"] == "serial30":
                single[raw["variant"]].append({"ms": call["http_ms"],
                                               "correct": got[call["key"]] == expected[call["key"]]})
        ok = raw["status"] == "ok"
        assert not ok or set(observed) == set(expected)
        row = {k: v for k, v in raw.items() if k != "calls"}
        row.update(
            correct=ok and observed == expected, expected=expected, choices=observed,
            extra=sum(v != "omit" and v != expected[k] for k, v in observed.items()),
            missing=sum(v != "omit" and v != observed.get(k) for k, v in expected.items()),
            active_total=sum(v != "omit" for v in expected.values()),
            active_correct=sum(v != "omit" and observed.get(k) == v for k, v in expected.items()),
            omit_total=sum(v == "omit" for v in expected.values()),
            omit_correct=sum(v == "omit" and observed.get(k) == v for k, v in expected.items()),
        )
        rows.append(row)
        if row["kind"] != "warmup":
            groups[(row["kind"], row["dataset"], row["order"], row["layout"], row["variant"])].append(row)
    summary = {"/".join(k): summarize(v) for k, v in groups.items()}
    steps = {k: {"calls": len(v), "correct": sum(r["correct"] for r in v),
                 "mean_ms": statistics.mean(r["ms"] for r in v), "p95_ms": percentile([r["ms"] for r in v])}
             for k, v in single.items()}
    pairs = defaultdict(dict)
    for r in rows:
        if r["kind"] == "quality":
            pairs[(r["dataset"], r["id"], r["order"])][r["variant"]] = r
    changes = []
    for key, pair in pairs.items():
        assert set(pair) == {"base", "lora"}
        a, b = pair["base"], pair["lora"]
        if a["choices"] != b["choices"]:
            changes.append({"dataset": key[0], "id": key[1], "order": key[2],
                            "baseline_correct": a["correct"], "lora_correct": b["correct"],
                            "fields": {k: [a["choices"].get(k), b["choices"].get(k)]
                                       for k in a["expected"] if a["choices"].get(k) != b["choices"].get(k)}})
    conditions = {}
    for order in ("original", "reversed"):
        a, b = [summary[f"quality/heldout/{order}/full30/{variant}"] for variant in ("base", "lora")]
        conditions[f"heldout_{order}_exact_improved"] = b["correct"] > a["correct"]
        conditions[f"heldout_{order}_active_not_worse"] = b["active_correct"] >= a["active_correct"]
        a, b = [summary[f"quality/spec/{order}/full30/{variant}"] for variant in ("base", "lora")]
        conditions[f"spec_{order}_not_worse"] = b["correct"] >= a["correct"]
    a, b = [summary[f"performance/spec/original/full30/{variant}"] for variant in ("base", "lora")]
    conditions["full30_mean_within_10pct"] = b["wall_mean_ms"] <= a["wall_mean_ms"]*1.1
    conditions["full30_p95_within_10pct"] = b["wall_p95_ms"] <= a["wall_p95_ms"]*1.1
    conditions["zero_errors"] = not complete["errors"]
    spec_categories = {}
    for category in ("single", "multi"):
        for variant in ("base", "lora"):
            selected = [r for r in rows if r["kind"] == "quality" and r["dataset"] == "spec"
                        and r["order"] == "original" and r["variant"] == variant
                        and historical[r["id"]]["category"] == category]
            spec_categories[f"{category}/{variant}"] = summarize(selected)
    examples = []
    for case_id in ("S01", "S09", "M08"):
        pair = pairs[("spec", case_id, "original")]
        examples.append({"id": case_id, "query": historical[case_id]["query"],
                         "expected": {k: v for k, v in pair["base"]["expected"].items() if v != "omit"},
                         **{variant: {k: v for k, v in pair[variant]["choices"].items() if v != "omit"}
                            for variant in ("base", "lora")}})
    save(ROOT / "summary.json", {"groups": summary, "single_step": steps,
                                 "spec_categories": spec_categories, "conditions": conditions,
                                 "adopted": all(conditions.values()), "production_deployed": False})
    save(ROOT / "scored.json", rows)
    save(ROOT / "choice-changes.json", changes)
    save(ROOT / "examples.json", examples)
    readmes = json.loads((ROOT / "readme-before.json").read_text())
    repo = HERE.parents[2]
    assert all(hashlib.sha256((repo / p).read_bytes()).hexdigest() == h for p,h in readmes.items())
    selected = json.loads((ROOT / "training/selection.json").read_text())["selected"]
    server = json.loads((ROOT / "evaluation/server.json").read_text())
    adapter = ROOT / "training" / selected["path"]
    assert hashlib.sha256(adapter.read_bytes()).hexdigest() == selected["sha256"] == server["selected"]["sha256"]
    for filename, key in (("evaluate.py", "server_sha256"), ("worker.py", "worker_sha256")):
        assert hashlib.sha256((HERE / filename).read_bytes()).hexdigest() == server[key]
    save(ROOT / "audit.json", {"passed": True, "http_calls": call_count, "task_blocks": len(rows),
                               "interface_errors": len(complete["errors"]), "overlaps": 0,
                               "request_hashes_verified": call_count,
                               "readmes_preserved": len(readmes), "test_labels_transferred": False,
                               "training_and_dev_labels_transferred": True,
                               "selected_adapter_sha256_verified": selected["sha256"],
                               "selected_adapter_bytes": adapter.stat().st_size,
                               "served_sources_match_local": True,
                               "github_push": False, "audited_at": stamp()})
    report(summary, steps, changes, conditions, call_count, spec_categories, examples)


def report(summary, steps, changes, conditions, calls, spec_categories, examples):
    def get(kind, dataset="spec", order="original", layout="full30", variant="base"):
        return summary[f"{kind}/{dataset}/{order}/{layout}/{variant}"]
    selection = json.loads((ROOT / "training/selection.json").read_text())
    smoke = json.loads((ROOT / "smoke/result.json").read_text())
    modules = json.loads((ROOT / "smoke/modules.json").read_text())
    merged = json.loads((ROOT / "evaluation/reload-merge.json").read_text())
    overlap = json.loads((ROOT / "split-limitations.json").read_text())
    a, b = [get("quality", "heldout", variant=v) for v in ("base", "lora")]
    base_full, tuned_full = [get("performance", variant=v) for v in ("base", "lora")]
    tuned_serial = get("performance", layout="serial30", variant="lora")
    lines = [
        "# Liquid d1-2B 空调 LoRA 微调实测",
        "",
        f"测试日期：2026-11-01。状态：本轮完成。报告生成时间：{stamp()}。",
        "",
        f"**新表达测试集完整正确数：{a['correct']}/192 → {b['correct']}/192。"
        f"预定相对改进门槛{'全部通过' if all(conditions.values()) else '未全部通过'}，尚未部署到生产。**",
        "",
        f"原规范三轮的一次全答完整正确率从 {base_full['accuracy']:.0%} 提升到 "
        f"{tuned_full['accuracy']:.0%}，平均耗时 {base_full['wall_mean_ms']/1000:.3f} → "
        f"{tuned_full['wall_mean_ms']/1000:.3f} 秒。微调后的 30 步串行正确率为 "
        f"{tuned_serial['accuracy']:.0%}，平均 {tuned_serial['wall_mean_ms']/1000:.3f} 秒。"
        "本轮结果支持优先使用原生一次全答路径；LoRA 合并后提高准确率，推理耗时基本保持。"
        "相对改进门槛通过不代表生产验收通过，剩余漏发和多发仍需处理。",
        "",
        "本轮训练 Liquid 的原生候选选择能力，保留完整输入、30 个字段和 283 个候选。"
        "没有改成生成 JSON、没有增加 Pointer Head、没有压缩输入、筛选候选或事后修复命令。"
        "所有正式微调成绩均来自合并到 BF16 权重后的官方 system_one 推理路径。",
        "",
        "## 数据与训练",
        "",
        "1,024 条训练请求、96 条验证请求、192 条新表达测试请求，均为按规范能力构造的合成数据，"
        "中英文各半。先生成动作意图，再生成表达和完整标签；不使用教师模型。"
        "不同分区使用不同的“执行动作＋明确保持不变功能”条件组合及表达模板，"
        "但共享词汇和生成器，属于同领域合成留出测试，"
        "不是外部盲测，也不能替代真实用户分布验证。",
        "",
        f"若只按最终执行命令集合比较，新测试中有 {overlap['heldout_command_sets_seen_in_training']}/192 "
        "条的命令集合也出现在训练集，只是保持不变的条件和表达不同。"
        "因此不能把整个新测试集称为未见动作组合测试。",
        "",
        "本轮从全部合法取值构造动作，数值范围字段在合成数据中占比较高，"
        "训练和新测试覆盖全部 30 字段，验证集实际执行覆盖 29 字段。"
        "因此同时单列原规范及历史扩展表现，不能只用合成集总正确率判断实际应用效果。",
        "",
        "原规范及历史扩展共 78 条查询不进入训练，另作回归。训练和验证标签可供训练进程读取；"
        "新测试与历史标准答案仅在本机离线评分。测试导出只包含题号、请求和语言，"
        "含标签信息的组合元数据不上传。全部输入、划分及采用条件在正式训练前冻结。",
        "",
        f"固定模型 LiquidAI/d1-2B，revision `cfe5760ff5d5998f91d9ac56bd4b2dbd96996d41`。"
        f"仅文本注意力 q_proj/v_proj 加入 LoRA，共 {modules['trainable']:,} 个可训练参数；"
        "基础权重、视觉部分、输入嵌入和输出层冻结。r=16、alpha=32、dropout=0.05，"
        "AdamW 学习率 5e-5、梯度累积 16、训练一轮。",
        "",
        f"正式训练共 64 次优化器更新，训练及中间验证用时 {selection['elapsed_seconds']/60:.1f} 分钟，"
        "不含初始基线验证、模型加载和后续完整测试。所选适配器为 "
        f"`validation/ac_control/runs/{ROOT.name}/training/{selection['selected']['path']}`，"
        f"SHA-256：`{selection['selected']['sha256']}`。",
        "",
        "LoRA 使用标准 W + (alpha/r)BA 参数化，A 为 Kaiming 初始化、B 为零初始化，"
        "适配器以 FP32 保存，前向计算转为 BF16。实现为本实验的显式线性层包装，"
        "未声称使用官方 d1 训练脚本或 PEFT Trainer。",
        "",
        "训练按官方 set_size=16 编码，每个完整请求的两个问题组分别反向传播，累计同一任务的损失。"
        "随机排列字段及选项，同步更新正确选项位置。对执行字段和省略字段分别平均交叉熵后各占一半；"
        "全部省略的样本使用省略字段均值。官方候选别名最大值评分保留在可求导的 Torch 运算中。",
        "",
        f"梯度验证通过：8 次更新损失 {smoke['losses'][0]:.4f} → {smoke['losses'][-1]:.4f}，"
        "训练评分与官方选择一致，原权重未更新。正式训练从原始权重和新初始化 LoRA 开始，"
        "没有继承梯度验证的适配器。",
        "",
        f"按验证集完整正确数选择训练 {selection['selected']['examples']} 条后的检查点。"
        "正确数相同时依次比较多发加漏发数量及更早检查点；不使用测试成绩换模型或继续调参。",
        "",
        "| 检查点 | 验证正确 | 多发 | 漏发 |",
        "|---|---:|---:|---:|",
        f"| 原模型 | {selection['baseline']['correct']}/96 | {selection['baseline']['extra']} | {selection['baseline']['missing']} |",
    ]
    for r in selection["checkpoints"]:
        lines.append(f"| {r['examples']} 条后 | {r['correct']}/96 | {r['extra']} | {r['missing']} |")
    lines += ["", "## 准确率", "",
              "heldout 是新合成留出集；spec 是原规范；extension 是历史扩展；"
              "validation 是历史英文回归集，不是选检查点的 96 条 dev 验证集；chinese 是历史中文回归集。",
              "",
              "| 数据集／候选顺序 | 原模型完整正确 | LoRA 完整正确 | 原模型多发／漏发 | LoRA 多发／漏发 |",
              "|---|---:|---:|---:|---:|"]
    for dataset in ("heldout", "spec", "extension", "validation", "chinese"):
        for order in ("original", "reversed"):
            a,b = [get("quality", dataset, order, variant=v) for v in ("base","lora")]
            lines.append(f"| {dataset}/{order} | {a['correct']}/{a['tasks']} | {b['correct']}/{b['tasks']} | "
                         f"{a['extra']}/{a['missing']} | {b['extra']}/{b['missing']} |")
    lines += ["", "完整命令集合严格匹配：任何多发、漏发或错值均判整题失败。"
              "“多发”统计错误输出的命令，“漏发”统计未正确输出的目标命令；"
              "字段值选错会同时计入两项。原序和倒序是同一批查询的两个条件，不算新的独立问题。",
              "",
              "改善主要来自减少多发命令。历史中文回归中，原序漏发从 2 增至 4，倒序从 3 增至 5；"
              "原规范也仍有一条显示灯关闭命令漏发。完整正确率改善不能掩盖这些执行字段退化。",
              "", "| 原规范类别（原候选顺序，一次全答） | 原模型 | LoRA |",
              "|---|---:|---:|"]
    for category, label in (("single", "单指令"), ("multi", "多指令")):
        a, b = [spec_categories[f"{category}/{v}"] for v in ("base", "lora")]
        lines.append(f"| {label} | {a['correct']}/{a['tasks']} | {b['correct']}/{b['tasks']} |")
    lines += ["", "## 具体选择示例", "",
              "以下为原规范、原候选顺序、一次全答的真实输出；只列非省略字段。",
              ""]
    for example in examples:
        lines += [f"### {example['id']}：{example['query']}", ""]
        for key, label in (("expected", "标准命令"), ("base", "原模型"), ("lora", "LoRA")):
            lines.append(f"- {label}：`{json.dumps(example[key], ensure_ascii=False, separators=(',', ':'))}`")
        lines.append("")
    lines += ["S09 仍把关闭显示灯省略；M08 仍多发 `t_swing_angle=0`。"
              "这两类错误需要后续补充真实表达及相近功能的区分样本，本轮没有使用测试答案继续训练。",
              "", "## 原规范 20 题 × 三轮：准确率与耗时", "",
              "| 方式 | 原模型 | LoRA |",
              "|---|---|---|"]
    a,b=steps["base"],steps["lora"]
    lines.append(f"| 实测单字段 | {a['correct']}/{a['calls']}；{a['mean_ms']:.1f} ms | "
                 f"{b['correct']}/{b['calls']}；{b['mean_ms']:.1f} ms |")
    for layout in ("serial30","full30"):
        a,b = [get("performance",layout=layout,variant=v) for v in ("base","lora")]
        lines.append(f"| {layout} | {a['correct']}/60；平均 {a['wall_mean_ms']/1000:.3f} s，"
                     f"P95 {a['wall_p95_ms']/1000:.3f} s | {b['correct']}/60；平均 "
                     f"{b['wall_mean_ms']/1000:.3f} s，P95 {b['wall_p95_ms']/1000:.3f} s |")
    lines += ["", "同一 us-east-1d g6.xlarge/L4，原模型和合并后的微调模型同时常驻，"
              "所有外部调用严格串行，配对任务交替先后顺序。使用相同软件、精度、输入和推理接口。"
              "正式耗时包含 loopback HTTP 与 SDK，模型加载、检查点验证、预热、写盘和上传不计入。"
              "单步时间来自实际单字段调用，不用整任务除以 30。"
              "单字段正确率包括大量应当省略的字段，不能等同于整条用户指令正确率；"
              "三轮重复用于测量耗时，也不是 60 条不同的测试指令。",
              "", "## 保存、重载与采用判定", "",
              f"独立评估进程重新加载适配器；再次加载的 8 条验证探针输出一致。"
              f"合并及恢复原生投影融合后，{len(merged['merge_choice_changes'])} 条探针选择变化；"
              f"最大概率差 {merged['merge_max_probability_difference']:.6f}。"
              "最终完整质量测试覆盖合并后的实际模型，不能假定 BF16 合并必然数值等价。",
              "",
              "保留原模型的概率温度配置，没有重新校准微调后的置信度。本轮只验收候选选择和命令集合，"
              "不把返回概率视为已验证的正确率，也不使用置信度阈值过滤输出。",
              "", "| 预定门槛 | 通过 |", "|---|---|"]
    for name,passed in conditions.items():
        lines.append(f"| {name} | {'是' if passed else '否'} |")
    newly_wrong = [r for r in changes if r["baseline_correct"] and not r["lora_correct"]]
    lines += ["", f"全部质量条件中，原先正确而微调后错误的条件有 {len(newly_wrong)} 个。"
              "总准确率改善不代表每题都改善；逐题变化保留在证据中。",
              "", "## 证据", "",
              f"共 {calls:,} 次实际推理 HTTP 调用，接口错误 "
              f"{sum(r['errors'] for r in summary.values())} 次，请求无重叠。README 保持不变，EC2 保持运行。",
              ""]
    for filename,label in [("plan.json","冻结计划"),("data-audit.json","数据审计"),
                           ("evaluation-export-audit.json","测试输入导出审计"),
                           ("data-coverage.json","字段覆盖与划分核查"),
                           ("split-limitations.json","训练与测试命令集合重叠"),
                           ("training/selection.json","检查点选择"),("summary.json","完整汇总"),
                           ("scored.json","逐题评分"),("choice-changes.json","选择变化"),
                           ("examples.json","示例原始选择"),
                           ("evaluation/reload-merge.json","重载与合并"),("audit.json","推理审计"),
                           ("final-environment.json","最终 EC2 状态"),
                           ("evaluation/receipts.jsonl","原始请求回执")]:
        lines.append(f"- [{label}](../validation/ac_control/runs/{ROOT.name}/{filename})")
    (HERE.parents[2] / "docs/LIQUID_AC_LORA_RESULTS.md").write_text("\n".join(lines)+"\n")


if __name__ == "__main__":
    analyze()
