"""Build an offline evidence viewer from recorded runs; no network/model calls."""

import argparse
import html
import json
from pathlib import Path

NAMES = {
    "wikipedia-search": "搜索 Basel III 文章",
    "cfpb-dispute": "查找信用卡账单争议处理指南",
    "ecb-usd": "打开 ECB 美元汇率详情",
    "fdic-faq": "查找 FDIC 存款保险 FAQ",
    "fdic-bank-search": "查询 JPMorgan Chase Bank 的保险资质",
}
CATEGORIES = {
    "financial_news": "金融新闻分类",
    "annual_report_evidence": "财报证据核验",
    "deposit_insurance_triage": "存款保险判断",
    "fx_reporting_and_payment_routing": "汇率报表与付款分流",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run = args.run
    summary = json.loads((run / "scored-summary.json").read_text())
    browsing = json.loads((run / "scored-browser-results.json").read_text())
    finance = json.loads((run / "finance-results.json").read_text())
    plan = json.loads((run / "plan.json").read_text())
    prefix = run.relative_to(args.output.parent).as_posix()
    panels = []
    for task in NAMES:
        for repeat in (1, 2):
            cards = []
            for provider in ("jev", "decider"):
                result = next(
                    r
                    for r in browsing
                    if r["task_id"] == task and r["provider"] == provider and r["repeat"] == repeat
                )
                state = "完成" if result["success"] else "未完成"
                css = "pass" if result["success"] else "fail"
                steps = "".join(
                    f"<li>{html.escape(s.get('description', s.get('status', '')))}</li>"
                    for s in result["steps"]
                )
                base = f"{prefix}/browser/{result['id']}"
                observation = json.loads(
                    (run / "browser" / result["id"] / "final-observation.json").read_text()
                )
                cards.append(
                    f'<article><h3>{provider.upper()} <span class="{css}">{state}</span></h3>'
                    f"<p>{len(result['steps'])} 步 · {result['wall_ms'] / 1000:.2f} 秒（含页面加载）</p>"
                    f'<p class="url">{html.escape(observation["url"])}</p>'
                    f'<div class="shot"><a href="{base}/final.png"><img loading="lazy" src="{base}/final.png" alt="{provider} 真实浏览器最终截图"></a></div>'
                    f'<ol>{steps}</ol><a href="{base}/result.json">原始轨迹 JSON</a></article>'
                )
            panels.append(
                f'<section class="pair" data-task="{task}" data-repeat="{repeat}">{"".join(cards)}</section>'
            )
    rows = []
    for case in plan["finance"]["cases"]:
        answers = {}
        for provider in ("jev", "decider"):
            ordered = [
                next(
                    r
                    for r in finance
                    if r["case_id"] == case["id"]
                    and r["provider"] == provider
                    and r["variant"] == variant
                )
                for variant in ("original_order", "reversed_order")
            ]
            answers[provider] = "<br>".join(
                f'<span class="{"pass" if r["correct"] else "fail"}">{html.escape(r["choice"] or "API error")}</span>'
                for r in ordered
            )
        evidence = html.escape(json.dumps(case["state"], ensure_ascii=False, indent=2))
        rows.append(
            f"<tr><td>{html.escape(CATEGORIES[case['category']])}<br><small>{case['id']}</small>"
            f"<details><summary>查看题目与证据</summary><pre>{evidence}</pre><p>来源：{html.escape(case['source'])}</p></details></td>"
            f"<td>{case['expected']}</td><td>{answers['jev']}</td><td>{answers['decider']}</td></tr>"
        )
    template = """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Jev / Decider 实测证据</title>
<style>
body{font:16px/1.65 system-ui,sans-serif;margin:0;background:#f4f6f9;color:#17283e}
main{max-width:1240px;margin:auto;padding:32px 24px}h1{font-size:30px;margin:0}h2{margin-top:36px}
.muted,small{color:#526278}.metrics,.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}
article,.metric{background:white;border:1px solid #dbe2eb;border-radius:12px;padding:20px}
.metric strong{font-size:28px;display:block}.pass{color:#08794b}.fail{color:#b32629}
select{font:inherit;padding:8px;border:1px solid #b4bfcd;border-radius:6px;max-width:100%}
label{display:inline-block;margin:0 16px 18px 0}.url{font-size:12px;overflow-wrap:anywhere;min-height:40px}
.shot{height:350px;overflow:auto;border:1px solid #dbe2eb}.shot img{width:100%;display:block}
ol{padding-left:24px;font-size:14px;overflow-wrap:anywhere}a{color:#1557a0}
table{border-collapse:collapse;width:100%;background:white}th,td{padding:12px;border:1px solid #dbe2eb;text-align:left;vertical-align:top;font-size:14px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;max-width:520px;font-size:12px}summary{cursor:pointer}
[hidden]{display:none!important}@media(max-width:800px){.metrics,.pair{grid-template-columns:1fr}.table{overflow:auto}}
</style><main>
<p class="muted">2026-10-13 · 178 次真实模型调用 · 页面、操作、答案均可核对</p>
<h1>Jev / Decider 浏览器与金融实测</h1>
<p>模型：Jev 1.13.0 / Strands Decider 2B hobson v19。浏览器实连公开网站；金融资料为公开真实来源，其中业务输入为构造案例。</p>
<div class="metrics"><div class="metric">浏览器完成数<strong>Jev 10/10 · Decider 4/10</strong>5 类任务，各独立运行 2 次。</div>
<div class="metric">金融首轮正确数<strong>Jev 28/30 · Decider 22/30</strong>再反转选项：Jev 28/30 · Decider 24/30。</div></div>
<h2>浏览器操作对比</h2>
<p>浏览器读取页面文字及 DOM 控件；每一步由模型选择。截图用于留证，未作为视觉输入。点击截图查看原图。</p>
<label>业务任务 <select id="task">__OPTIONS__</select></label>
<label>运行 <select id="repeat"><option value="2">第 2 次</option><option value="1">第 1 次</option></select></label>
__PANELS__
<h2>金融逐题结果</h2>
<p>每格第一行为原顺序，第二行为反转顺序。30 道独立题目，60 次回答/模型。红色表示与事先固定的参考答案不一致。</p>
<div class="table"><table><thead><tr><th>业务任务 / 输入证据</th><th>参考答案</th><th>Jev</th><th>Decider</th></tr></thead><tbody>__ROWS__</tbody></table></div>
<h2>如何理解结果</h2>
<p>本轮支持把 Jev 用于有明确目标、有限动作的浏览器流程试点；Decider 在直接链接选择、简单分类上通过，但多步目标跟踪仍需改进。两者均把同一银行同一所有权类别的 18 万＋12 万美元存款误判为全部受保，金额聚合应使用可审计计算规则。</p>
<p>Jev 的银行查询第 1 次也出现重复填表，10 步完成；第 2 次 6 步。完成率不等于操作最优。</p>
<p class="muted">范围：英文页面与输入；小样本；不含登录、交易、支付、真实客户审批。新闻来自公开历史数据集，训练集重叠未知。SEC 403 与 FRED 控件回退在预检中排除。CFPB 评分关键词已按原文从 “60 days” 更正为 “60 calendar days”，保留原始评分，未重跑模型。</p>
<p><a href="README.zh.md">完整中文报告与复现说明</a> · <a href="__PREFIX__/scored-summary.json">汇总 JSON</a> · <a href="__PREFIX__/receipts.jsonl">全部请求与响应</a></p>
</main><script>
const task=document.getElementById('task'),repeat=document.getElementById('repeat');
function render(){document.querySelectorAll('.pair').forEach(p=>p.hidden=p.dataset.task!==task.value||p.dataset.repeat!==repeat.value);}
task.value='fdic-bank-search';task.addEventListener('change',render);repeat.addEventListener('change',render);render();
</script></html>"""
    template = template.replace(
        "__OPTIONS__", "".join(f'<option value="{k}">{v}</option>' for k, v in NAMES.items())
    )
    template = (
        template.replace("__PANELS__", "".join(panels))
        .replace("__ROWS__", "".join(rows))
        .replace("__PREFIX__", prefix)
    )
    assert (
        summary["browser"]["jev"]["success"] == 10 and summary["browser"]["decider"]["success"] == 4
    )
    args.output.write_text(template)
    print(args.output)


if __name__ == "__main__":
    main()
