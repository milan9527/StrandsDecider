"""Score the frozen screenshot test and generate a reviewable result document."""

import base64
import hashlib
import html
import json
import statistics
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GROUPS = {"payment": "支付状态与下一步动作", "support": "中文客服队列选择", "receipt": "凭证字段与处理动作"}


def prediction(answer):
    return answer["choice"] if answer["type"] == "choice" else answer["noul"] >= 0.5


def metrics(values):
    ordered = sorted(values)

    def percentile(q):
        index = (len(ordered) - 1) * q
        left = int(index)
        right = min(left + 1, len(ordered) - 1)
        return ordered[left] + (ordered[right] - ordered[left]) * (index - left)

    return {"mean_ms": statistics.mean(values), "p50_ms": statistics.median(values),
            "p95_ms": percentile(.95), "min_ms": min(values), "max_ms": max(values)}


def main():
    cases_path = ROOT / "cases.json"
    plan = json.loads(cases_path.read_text())
    cases = {c["id"]: c for c in plan["cases"]}
    env = json.loads((ROOT / "results/environment.json").read_text())
    assert env["cases_sha256"] == hashlib.sha256(cases_path.read_bytes()).hexdigest()
    assert env["runner_sha256"] == hashlib.sha256((ROOT / "run.py").read_bytes()).hexdigest()
    assert plan["frozen_at"] < env["started_at"]
    receipts = [json.loads(line) for line in (ROOT / "results/receipts.jsonl").read_text().splitlines()]
    counts = Counter(r["stage"] for r in receipts)
    assert counts == {"warmup": 3, "image": 36, "reverse": 12, "no_image": 12, "blank": 12}, counts
    for row in receipts:
        case = cases[row["case"]]
        req = row["request"]
        assert req["state"] == case["request"]["state"]
        assert req["questions"].keys() == case["request"]["questions"].keys()
        for key, question in req["questions"].items():
            assert question == case["request"]["questions"][key]
            if question["type"] == "choice":
                wanted = list(case["request"]["questions"][key]["criteria"])
                if row["stage"] == "reverse":
                    wanted.reverse()
                assert list(question["criteria"]) == wanted
        if row["stage"] == "no_image":
            assert "images" not in req
        else:
            expected_image = ROOT / ("images/blank.png" if row["stage"] == "blank" else case["image"])
            assert base64.b64decode(req["images"][0]) == expected_image.read_bytes()
        assert set(req) <= {"state", "questions", "images"}
    failed = [r for r in receipts if r.get("http_status") != 200]
    for row in receipts:
        if row.get("http_status") == 200:
            assert row["response"]["model"] == "strands-decider-2B-hobson-v19-vision"
    first = {r["case"]: r for r in receipts if r["stage"] == "image" and r["repetition"] == 0}
    detail, group_results, errors = [], {}, []
    for case_id, case in cases.items():
        row = first[case_id]
        answers = row.get("response", {}).get("answers", {})
        judged = {}
        for name, expected in case["expected"].items():
            answer = answers.get(name)
            actual = prediction(answer) if answer is not None else None
            judged[name] = {"expected": expected, "actual": actual, "correct": actual == expected,
                            "answer": answer}
            if actual != expected:
                errors.append({"case": case_id, "question": name, **judged[name]})
        runs = [r for r in receipts if r["case"] == case_id and r["stage"] == "image"]
        elapsed = [r["response"]["latency_ms"] for r in runs if r.get("http_status") == 200]
        detail.append({"case": case_id, "group": case["group"], "questions": judged,
                       "latency": metrics(elapsed) if elapsed else None,
                       "first_backend_ms": row.get("response", {}).get("latency_ms")})
    for group in GROUPS:
        part = [d for d in detail if d["group"] == group]
        elapsed = [r["response"]["latency_ms"] for r in receipts
                   if r["stage"] == "image" and cases[r["case"]]["group"] == group and r.get("http_status") == 200]
        group_results[group] = {
            "images": len(part), "questions": sum(len(d["questions"]) for d in part),
            "correct": sum(q["correct"] for d in part for q in d["questions"].values()),
            "all_correct_images": sum(all(q["correct"] for q in d["questions"].values()) for d in part),
            "backend_request": metrics(elapsed) if elapsed else None,
        }
    controls = {}
    for stage in ["reverse", "no_image", "blank"]:
        rows = [r for r in receipts if r["stage"] == stage and r.get("http_status") == 200]
        changed, abstained, choices, matched = 0, 0, 0, 0
        for row in rows:
            for name, answer in row["response"]["answers"].items():
                original = first[row["case"]].get("response", {}).get("answers", {}).get(name)
                if original is None:
                    continue
                changed += prediction(answer) != prediction(original)
                matched += prediction(answer) == cases[row["case"]]["expected"][name]
                if answer["type"] == "choice":
                    choices += 1
                    abstained += answer["choice"] in ("unknown", "review")
        controls[stage] = {
            "requests": len(rows), "changed_vs_first_image_questions": changed,
            "total_questions": sum(len(r["response"]["answers"]) for r in rows),
            "abstained_choices": abstained, "total_choices": choices,
            "matched_original_image_reference": matched,
        }
    repeat_changed = []
    for case_id, case in cases.items():
        runs = [r for r in receipts if r["case"] == case_id and r["stage"] == "image" and r.get("http_status") == 200]
        for name in case["expected"]:
            predictions = [prediction(r["response"]["answers"][name]) for r in runs]
            if len(set(predictions)) > 1:
                repeat_changed.append({"case": case_id, "question": name, "predictions": predictions})
    warm = [r for r in receipts if r["stage"] == "image" and r.get("http_status") == 200]
    summary = {
        "case_count": len(cases), "question_count": plan["independent_questions"],
        "first_pass_correct": sum(g["correct"] for g in group_results.values()),
        "first_pass_all_correct_images": sum(g["all_correct_images"] for g in group_results.values()),
        "requests": dict(counts), "failed_requests": len(failed),
        "warm_image_client": metrics([r["client_ms"] for r in warm]),
        "warm_image_backend": metrics([r["response"]["latency_ms"] for r in warm]),
        "warm_image_tokens": {"min": min(r["response"]["usage"]["input_tokens"] for r in warm),
                              "max": max(r["response"]["usage"]["input_tokens"] for r in warm)},
        "warmup_backend_ms": [r["response"]["latency_ms"] for r in receipts
                              if r["stage"] == "warmup" and r.get("http_status") == 200],
        "groups": group_results, "controls": controls, "repeat_changed": repeat_changed,
        "errors": errors, "cases": detail,
    }
    (ROOT / "results/summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    labels = {True: "是", False: "否", None: "调用失败"}

    def display(value):
        return labels.get(value, str(value))

    lines = [
        "# Strands Decider 图片内容决策实测", "",
        "2026-10-23，原始 **v19 + 官方视觉推理**，现有 **g6.xlarge / NVIDIA L4**，单并发。"
        "此次没有微调，也未修改线上 vLLM 服务。", "",
        f"12 张合成截图共 28 项判断，首轮正确 **{summary['first_pass_correct']}/28**；"
        f"整张截图的问题全部正确 **{summary['first_pass_all_correct_images']}/12**。"
        "重复同一图片不增加独立样本数。", "",
        "已接入独立的[图片决策演示](https://d3i7ogfx5ml7dc.cloudfront.net/#vision)，"
        "可上传图片实时运行，也可回看本批结果。"
        "界面、API、常驻部署及上线验收见[模块说明](../../docs/VISION.md)；本页保留原始实验口径。", "",
        "## 场景结果", "",
        "| 场景 | 图片 | 正确判断 | 整图全对 | 后端请求均值 | 后端 P95 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for group, result in group_results.items():
        m = result["backend_request"]
        lines.append(f"| {GROUPS[group]} | {result['images']} | {result['correct']}/{result['questions']} | "
                     f"{result['all_correct_images']}/{result['images']} | {m['mean_ms']:.1f} ms | {m['p95_ms']:.1f} ms |")
    m, c = summary["warm_image_backend"], summary["warm_image_client"]
    lines += [
        "", f"36 次带图正式请求：后端均值 **{m['mean_ms']:.1f} ms**，P50 **{m['p50_ms']:.1f} ms**，"
        f"P95 **{m['p95_ms']:.1f} ms**；本机 HTTP 往返均值 **{c['mean_ms']:.1f} ms**。"
        "每次请求包含一张图和该图的全部问题：支付、凭证各 3 问，客服 1 问，"
        "**不是每个问题分别计时**。3 次预热及模型加载不纳入这些延迟。",
        f"该 GPU 保留其他既有服务，因而这是功能验证中的请求延迟，不是隔离环境吞吐基准。"
        f"模型加载与服务就绪耗时 {env['model_load_seconds']:.1f} 秒；"
        f"首次预热请求耗时 {summary['warmup_backend_ms'][0] / 1000:.1f} 秒，"
        "原始记录保留该首次调用，不将预热后的延迟误称为首次调用耗时。", "",
        "## 结论与实际案例", "",
        "**清晰截图上的支付状态判断和中文客服分流可用，约 0.17 秒完成一次带图请求。**"
        "本次图片直接进入视觉编码器，没有先 OCR 再把文字送给 Decider。"
        "成功、处理中、失败图片使用相同请求文本，却分别得到 `completed / pending / failed`；"
        "中文客服四类诉求也分别进入正确队列。", "",
        "**识别出字段，不代表组合条件一定执行正确。**"
        "第 11 张凭证有签名、交易编号留空。实际返回：", "",
        "```json",
        json.dumps({name: first["case-11"]["response"]["answers"][name]
                    for name in ("signature", "reference", "action")}, ensure_ascii=False, indent=2),
        "```", "",
        "`signature=0.7839`、`reference=0.1973` 正确反映“有签名、无编号”，"
        "但动作选了 `accept`，预期应为 `request_reference`。"
        "动作 confidence 仅 0.2909；这体现字段判断与后续动作选择之间仍需一致性验收，"
        "本次没有用程序改写模型答案。", "",
        "仅反转候选顺序后，第 10 张从正确的 `request_signature` 变为错误的 `request_both`；"
        "第 11 张从错误的 `accept` 变为同样错误的 `request_both`。"
        "首轮 27/28，反转后 26/28，不能把重复三轮完全一致当作候选换序也稳定。", "",
        "## 测试图片", "", "![12 张合成测试截图](fixtures-overview.png)", "",
        "由 Pillow 绘制 UI：中英文支付状态、中文客服对话、凭证表单。"
        "签名使用手绘线条，不用“已签名”文字代替视觉证据。"
        "全部图片为 448×448，未使用真实客户数据。", "",
        "## 每张图的实际选择", "",
        "| 图片 | 问题 | 预期 | 实际 | 首轮结果 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in detail:
        for name, q in item["questions"].items():
            lines.append(f"| [{item['case']}]({cases[item['case']]['image']}) | {name} | "
                         f"{display(q['expected'])} | {display(q['actual'])} | {'正确' if q['correct'] else '**错误**'} |")
    lines += ["", "## 图片依赖与选项顺序对照", "",
              "| 对照 | 相比带图首轮改变的判断 | 明确选择信息不足 |",
              "| --- | ---: | ---: |"]
    for stage, label in [("reverse", "仅反转 choice 候选顺序"), ("no_image", "移除图片"), ("blank", "替换为纯白图片")]:
        row = controls[stage]
        lines.append(f"| {label} | {row['changed_vs_first_image_questions']}/{row['total_questions']} | "
                     f"{row['abstained_choices']}/{row['total_choices']} 个选择题 |")
    lines += [
        "", f"相同图片重复三轮，发生类别变化的判断项：**{len(repeat_changed)}/28**。",
        "无图／白图时不再使用原图答案作为正确率：缺少证据不能沿用原图的标签。"
        "选择题均提供“图片缺失或信息不足”选项；noul 只能给是／否概率，不能单独表达未知。"
        "无图对照用于观察猜测和证据依赖，不能单凭概率高就认定图片被正确理解。", "",
        "## 方法与复现", "",
        "1. `prepare.py` 生成图片和预期，`cases.json` 在模型调用前冻结并计算 SHA-256。",
        "2. 将图片作为 Base64 放入顶层 `images`，只提交统一 state、问题和候选；不传入文件名、预期或 OCR 文本。",
        "3. 官方视觉服务启用 `vision=True`、CUDA、SDPA、共享上下文、严格 4096 token 窗口；"
        "保持原始 v19 的 LoRA、决策头及温度参数。底座 BF16，决策头 FP32。",
        "4. 3 次预热后，12 图各测 3 轮；再各测反转候选、无图、白图一次，共 75 次 HTTP 调用。",
        "5. choice 按选项 ID 比较，noul 使用事前固定的 0.5 阈值。所有失败与原始概率保留。",
        "", f"上游源码固定到 `{env['source']['commit']}`；"
        f"transformers `{env['packages']['transformers']}`、torch `{env['packages']['torch']}`。"
        f"本次 HTTP 调用失败 {len(failed)}/75。", "",
        "这是 12 张清晰合成图片的冒烟验证，不代表真实票据、小字扫描件、模糊拍照或通用多模态准确率。"
        "未比较 Jev/GPT，也未适配 vLLM 的视觉路径。", "",
        "本批实验结束后，临时视觉容器已移除，既有容器仍运行；两个原有 EC2 保持原状态。"
        "实验的临时 ECS 任务定义已注销，未创建新 EC2。"
        "随后上线的图片模块在同一实验实例启动了独立的常驻视觉容器，"
        "当前状态见[部署记录](../../deployment/DEPLOYED.md)。"
        "环境准备过程中两次启动失败分别涉及离线依赖和结果上传签名，均未进入正式模型评测，"
        "不计入上述 75 次 HTTP 调用。", "",
        "## 文件", "",
        "- [交互结果页](report.html)：图片与实际判断并排查看。",
        "- [冻结的请求模板与预期](cases.json)、[输入生成代码](prepare.py)、[调用代码](run.py)、[评分代码](analyze.py)。",
        "- [汇总 JSON](results/summary.json)、[完整请求与响应](results/receipts.jsonl)、"
        "[环境与权重哈希](results/environment.json)、[官方服务健康状态](results/health.json)。",
        "- [官方视觉说明](https://github.com/strands-labs/strands-decider/blob/main/docs/vision.md)。", "",
    ]
    (ROOT / "README.zh.md").write_text("\n".join(lines))
    cards = []
    for item in detail:
        rows = []
        for name, q in item["questions"].items():
            answer = q["answer"] or {}
            confidence = answer.get("confidence", answer.get("noul"))
            certainty = "" if confidence is None else f"{confidence:.3f}"
            rows.append(
                f"<tr><td>{html.escape(name)}</td><td>{html.escape(display(q['expected']))}</td>"
                f"<td class=\"{'ok' if q['correct'] else 'bad'}\">{html.escape(display(q['actual']))}</td>"
                f"<td>{certainty}</td></tr>"
            )
        cards.append(
            f"<article><img src=\"{cases[item['case']]['image']}\" alt=\"{item['case']}\">"
            f"<div><h2>{item['case']} · {GROUPS[item['group']]}</h2>"
            f"<p>单请求包含全部问题；三轮后端均值 {item['latency']['mean_ms']:.1f} ms</p>"
            "<table><tr><th>问题</th><th>预期</th><th>实际</th><th>confidence / P(是)</th></tr>"
            + "".join(rows) + "</table><details><summary>查看请求问题和原始返回</summary><pre>"
            + html.escape(json.dumps({
                "request": {**cases[item["case"]]["request"], "images": ["图片的 Base64 内容，见完整请求记录"]},
                "response": first[item["case"]].get("response"),
            }, ensure_ascii=False, indent=2)) + "</pre></details></div></article>"
        )
    (ROOT / "report.html").write_text(
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        "<title>Decider 图片内容决策实测</title><style>"
        "body{font-family:system-ui,sans-serif;background:#edf3f7;color:#173346;margin:32px auto;max-width:1180px;padding:0 20px}"
        "article{display:grid;grid-template-columns:320px 1fr;gap:24px;background:white;padding:20px;margin:20px 0;border-radius:16px}"
        "article>div{min-width:0}img{width:100%;border-radius:10px}table{table-layout:fixed;border-collapse:collapse;width:100%;font-size:14px}"
        "td,th{overflow-wrap:anywhere;border-bottom:1px solid #dde5eb;padding:12px 8px;text-align:left}.ok{color:#00877c}.bad{color:#bc3246;font-weight:bold}"
        "details{margin-top:20px}summary{cursor:pointer;color:#006f9e}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;background:#edf3f7;padding:16px}"
        "p{line-height:1.8}a{color:#006f9e}@media(max-width:800px){article{grid-template-columns:1fr}img{max-width:448px}}"
        "</style><h1>Strands Decider 图片内容决策实测</h1>"
        f"<p>v19 · 官方视觉推理 · L4 · 12 张合成截图 · 首轮 {summary['first_pass_correct']}/28 项判断正确"
        f" · 正式带图请求后端均值 {m['mean_ms']:.1f} ms</p>"
        "<p>主要错误：有签名、缺交易编号的凭证被选择接收。反转候选后另有一题由对变错。"
        "这是清晰合成截图上的小样本验证；预热后的延迟不包含首次调用。</p>"
        '<p><a href="README.zh.md">方法、对照和限制</a> · <a href="fixtures-overview.png">图片总览</a> · '
        '<a href="results/receipts.jsonl">完整原始请求</a></p>' + "".join(cards) + "</html>"
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "cases"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
