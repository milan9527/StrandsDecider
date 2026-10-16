"""Extend the existing v8 deck with recorded routing, vLLM and cost evidence."""

import hashlib
import io
import json
from datetime import UTC, datetime
from pathlib import Path

import cairosvg
import matplotlib
import presentation_layout as L
from build_presentation_v5 import replace_text
from fontTools.ttLib import TTFont
from matplotlib import font_manager
from PIL import Image
from pptx import Presentation
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/presentations/v9"
ASSETS = OUT / "assets"
SOURCES = OUT / "sources"
BASE = next((ROOT / "docs/presentations/v8").glob("*.pptx"))
PAGE_COUNT = 52
NAME = "Strands-Decider-模型原理与业务演示-v9-适用场景-模型路由-vLLM与成本对比-52页-20261013"
REPO = "https://github.com/milan9527/StrandsDecider"
VREPO = "https://github.com/milan9527/StrandsDeciderVLLM"
DEMO = "https://d3i7ogfx5ml7dc.cloudfront.net"
API = "https://d1e9udi8st2p3g.cloudfront.net"
PURPLE = "8055A4"
PROVIDERS = ("decider", "jev", "bedrock")
LABELS = ("Decider", "Jev", "GPT-6 Sol low")
COLORS = (L.TEAL, PURPLE, L.BLUE)
CASES = ("support", "code", "analysis", "retrieval")
CASE_NAMES = ("支付客服", "交易代码", "结算分析", "中英文索引")


def load(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def chart(name, build, width=11, height=3.8):
    fig, ax = plt.subplots(figsize=(width, height))
    fig.set_facecolor("#" + L.BG)
    ax.set_facecolor("#" + L.BG)
    build(ax)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#" + L.LINE)
    ax.grid(axis="y", alpha=0.18)
    ax.set_axisbelow(True)
    fig.tight_layout(pad=1.0)
    for ext in ("png", "svg"):
        fig.savefig(ASSETS / f"{name}.{ext}", dpi=190, facecolor=fig.get_facecolor())
    plt.close(fig)
    return ASSETS / f"{name}.png"


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    ttc = Path("/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc")
    if ttc.exists():
        font = ROOT / ".deployment/presentation-fonts/NotoSansCJKSC-Regular.otf"
        font.parent.mkdir(parents=True, exist_ok=True)
        if not font.exists():
            TTFont(ttc, fontNumber=2).save(font)
        font_manager.fontManager.addfont(str(font))
    plt.rcParams.update({"font.family": "Noto Sans CJK SC", "font.size": 11})

    base_hash = digest(BASE)
    prs = Presentation(BASE)
    original = list(prs.slides)
    original_ids = list(prs.slides._sldIdLst)
    routing_path = ROOT / "docs/results/workflow-routing-2026-10-13"
    rt = load(routing_path / "summary.json")
    js = load(SOURCES / "vllm/jev-summary.json")
    sweep = load(SOURCES / "vllm/sweep-1-128.json")["cells"]
    batches = load(SOURCES / "vllm/batch-summary.json")
    reference = load(SOURCES / "vllm/original-benchmark.json")["cells"]
    recheck = load(SOURCES / "vllm/vllm-recheck.json")["cells"]
    cost = load(SOURCES / "cost-calculation.json")
    manifests, crops, order = [], [], []
    base_titles = load(ROOT / "docs/presentations/v8/build-manifest.json")["slides"]

    routing_notes = (
        "实测：2026-10-13，workflow-model-v1。四场景×三模型×两次真实调用=24次正式返回，"
        "6次预热另存。来源：docs/results/workflow-routing-2026-10-13/results.json、summary.json。"
        "本批三侧两步输入指纹一致。官方Decider v19运行于g6.xlarge，未使用vLLM。"
        "Jev经ECS/Lambda访问Typesafe；GPT决策器为us.openai.gpt-6-sol / low。"
        "计时为backend_total_ms，两步相加，不含目标执行；没有运行所选目标模型。"
        "首轮GPT分析场景型号选择40秒超时保留在initial-run/results.json；表内使用完整复测批次。"
        "仅四个任务，各测一次，不提供通用准确率或稳定延迟。"
        f"\n详细报告：{REPO}/blob/main/docs/MODEL_ROUTING_COMPARISON.md\nDemo：{DEMO}/#routing"
    )
    vllm_notes = (
        "原始证据来自独立StrandsDeciderVLLM项目，复制文件与原仓库提交/SHA-256见sources/vllm/provenance.json。"
        "模型v19，vLLM0.31.0，BF16底座/FP32 Pointer Head，单L4。"
        "原版同机比较为g6.4xlarge，推理容器限制4vCPU/14GiB、回环HTTP；"
        "后续公网性能为g6.xlarge，经CloudFront VPC源站；Jev对比直接访问Typesafe，不经支付演示Lambda。"
        "20条固定支付输入，每请求一个choice；固定worker收到完整响应后补发，失败不重试。"
        "所有预热单独记录并排除。成功吞吐=成功数/正式阶段总耗时，失败仍占总时间。"
        "P95/P99只统计成功响应，不包含失败等待时长。"
        "重复输入不是更多独立质量样本；动作相同不是准确率。当前支付/路由演示没有切换至vLLM。"
        f"\n适配：{VREPO}/blob/main/docs/ADAPTER.zh-CN.md"
        f"\n性能：{VREPO}/blob/main/docs/VLLM_PERFORMANCE.zh-CN.md"
        f"\nJev对比：{VREPO}/blob/main/docs/JEV_CONCURRENCY.zh-CN.md"
    )
    cost_notes = (
        "2026-10-13查询AWS Price List API：us-east-1、Linux、Shared、On-Demand、g6.2xlarge，"
        "0.9776 USD/小时。EBS gp3 0.08 USD/GB月，按独立API的160GB配置举例。"
        "Jev官方博客当天抓取：0.042 USD/百万输入token，输出免费。"
        "使用实测响应中的Jev usage计算，不使用Decider token数代替Jev。"
        "价格与用量是可核验数据，月费用和交点是按公开单价的估算，不是账单。"
        "月按730小时、不计折扣/税/免费额度；计算费比较未含网络、CloudFront、代理、日志、运维、冗余。"
        "目标模型生成/embedding费用另计。g6.2xlarge未进行本次性能实测，不能把g6.xlarge吞吐视为其容量保证。"
        "sources/cost-calculation.json保留公式输入、逐场景token与结果。"
        "\nAWS：https://aws.amazon.com/ec2/pricing/on-demand/"
        "\nJev：https://typesafe.ai/blog/introducing-system-one-models-and-jev"
    )

    def text(s, value, x, y, w, h=0.4, size=18, color=L.INK, bold=False, align=None):
        return L.text(s, str(value), x, y, w, h, size, color, bold, align)

    def note(s, value):
        text(s, value, 0.65, 6.70, 12.0, 0.27, 10.7, L.MUTED)

    def link(s, label, url, x=0.65, y=6.35, w=12.0):
        sh = text(s, label, x, y, w, 0.26, 11.5, L.BLUE)
        for p in sh.text_frame.paragraphs:
            for run in p.runs:
                run.hyperlink.address = url
        return sh

    def icon(s, name, x, y, size=0.42, color=L.TEAL, aws=False):
        path = ROOT / (
            f"docs/diagrams/aws-icons/{name}.svg"
            if aws
            else f"docs/presentations/v3/icons/{name}.svg"
        )
        svg = path.read_text().replace("currentColor", "#" + color)
        blob = cairosvg.svg2png(bytestring=svg.encode(), output_width=180, output_height=180)
        s.shapes.add_picture(io.BytesIO(blob), Inches(x), Inches(y), Inches(size), Inches(size))

    def new(title, section, subtitle, notes):
        s = prs.slides.add_slide(prs.slide_layouts[6])
        s.background.fill.solid()
        s.background.fill.fore_color.rgb = L.rgb(L.BG)
        text(s, "STRANDS DECIDER  /  " + section, 0.6, 0.27, 12, 0.25, 10, L.TEAL, True)
        text(s, title, 0.6, 0.79, 12.1, 0.7, 28.5, L.INK, True)
        text(s, subtitle, 0.62, 1.56, 12.0, 0.46, 15.3, L.MUTED)
        s.notes_slide.notes_text_frame.text = notes
        order.append(prs.slides._sldIdLst[-1])
        manifests.append({"title": title, "section": section, "source": "new"})
        return s

    def keep(n):
        order.append(original_ids[n - 1])
        manifests.append(
            {"title": base_titles[n - 1]["title"], "source": "v8", "v8_page": n}
        )
        return original[n - 1]

    def card(s, x, y, w, h, title, body, color=L.TEAL, glyph=None, size=17):
        L.rect(s, x, y, w, h, L.WHITE, L.LINE, True)
        tx = x + 0.22
        if glyph:
            icon(s, glyph, tx, y + 0.18, color=color)
            tx += 0.55
        text(s, title, tx, y + 0.17, w - (tx - x) - 0.15, 0.45, 19, color, True)
        text(s, body, x + 0.22, y + 0.82, w - 0.44, h - 0.91, size)

    def flow(s, items, y=2.4, h=1.65):
        gap, width = 0.3, (12.0 - (len(items) - 1) * 0.3) / len(items)
        for i, (title, body, glyph) in enumerate(items):
            x = 0.65 + i * (width + gap)
            card(s, x, y, width, h, title, body, glyph=glyph, size=15)
            if i + 1 < len(items):
                L.line(s, [(x + width + .04, y + h / 2), (x + width + gap - .04, y + h / 2)], L.TEAL, arrow=True)

    def table(s, headers, rows, widths, y=2.25, rh=0.52, size=16, x=0.65, highlights=()):
        for i, row in enumerate([headers, *rows]):
            xx = x
            for value, width in zip(row, widths, strict=True):
                fill = L.NAVY if i == 0 else L.PALE_ORANGE if i - 1 in highlights else L.WHITE if i % 2 else "EDF1F6"
                L.rect(s, xx, y + rh * i, width, rh, fill, L.LINE)
                text(s, value, xx + .10, y + rh * i + .075, width - .20, rh - .09, size, L.WHITE if i == 0 else L.INK, i == 0)
                xx += width

    def crop(case, box, suffix):
        source = routing_path / f"{case}-desktop.png"
        target = ASSETS / f"routing-{case}-{suffix}.png"
        with Image.open(source) as image:
            image.crop(box).save(target)
        crops.append({"source": str(source.relative_to(ROOT)), "source_sha256": digest(source), "box": list(box), "file": str(target.relative_to(OUT)), "sha256": digest(target)})
        return target

    for i in range(1, 8):
        keep(i)

    scenario_notes = (
        "适用场景依据Strands Decider官方介绍、Typesafe System One介绍和本项目app/examples.py。"
        "基础工作台包含16个输入模板，包括客服、工具、退款、线索、内容审核、运维、RAG与支付。"
        "这是能力使用方式与可验证的应用方向，不代表所有场景已经达到生产质量。"
        "本版正式质量/速度结果限于已注明的支付和模型路由任务；并发重复固定20条支付输入。"
        "noul是模型对陈述支持程度的输出，不能在未经业务校准时当作真实事件发生概率。"
        "决策模型只给结构化建议；业务执行、权限与资金条件由应用校验。"
        "\nStrands官方：https://strandsagents.com/blog/introducing-strands-decider/"
        f"\n场景代码：{REPO}/blob/main/app/examples.py"
    )
    s = new("决策模型适用场景：把高频判断接入软件流程", "适用场景 / 六类任务",
            "在明确候选中选择、判断陈述支持程度、输出等级；业务系统消费结构化结果。", scenario_notes)
    for x, y, title, body, glyph in [
        (.65, 2.23, "客服与运营", "工单队列、升级路径、跟进等级\nchoice / score", "headset"),
        (4.79, 2.23, "支付与风控", "等待确认、补款、地址核验\nchoice；执行系统保留资金校验", "shield-check"),
        (8.93, 2.23, "工具与模型路由", "选处理流程、工具或目标型号\nchoice；需要候选能力事实", "route"),
        (.65, 4.40, "RAG 与质量检查", "依据是否充分、是否继续检索\nnoul / choice", "search"),
        (4.79, 4.40, "内容审核", "内容类别、风险等级、人工升级\nchoice / score", "scan-eye"),
        (8.93, 4.40, "告警与销售线索", "业务影响分级、线索跟进优先级\nscore / choice", "chart-no-axes-combined"),
    ]:
        card(s, x, y, 3.74, 1.85, title, body, glyph=glyph, size=15.5)
    note(s, "工作台提供相关示例；以下正式实测聚焦支付流程与模型路由，不宣称六类任务已全部验证。")

    s = new("适用条件：候选清晰、事实可得、结果可验证", "适用场景 / 落地边界",
            "先确认问题适合有限判断，再以独立业务样本验收质量、延迟和自动化覆盖率。", scenario_notes)
    flow(s, [("明确问题", "选项有清楚语义\n例：补款 / 等确认 / 人工", "list-filter"),
             ("提供事实", "已知状态 + 候选能力\n缺失证据不能凭空补齐", "receipt-text"),
             ("模型建议", "结构化选择与分数\n阈值需单独校准", "brain-circuit"),
             ("执行与反馈", "条件 / 权限校验后执行\n结果回传，必要时重判", "check-check")], h=1.92)
    card(s, .65, 4.80, 5.85, 1.45, "适合优先试点", "重复高频判断、边界明确、可留痕并验证结果", glyph="target", size=16)
    card(s, 6.8, 4.80, 5.85, 1.45, "需要其他能力配合", "长文本与代码生成交给生成模型；复杂异常可人工复核", PURPLE, "workflow", 16)
    note(s, "类型合法不等于语义正确；金额计算、账本更新、权限和交易执行仍由业务系统负责。")

    for i in range(8, 24):
        keep(i)

    # Routing, with real model choices and original UI crops.
    s = new("从选业务动作，到选择执行任务的模型", "模型路由 / 实现",
            "用户只输入任务；三个决策模型分别完成「选流程 → 选型号」。", routing_notes)
    flow(s, [("任务输入", "原始业务请求\n无速度 / 成本优先级", "receipt-text"),
             ("决策 1", "选择处理流程\n客服 / 代码 / 分析 / 向量", "route"),
             ("决策 2", "任务 + 已选流程\n+ 候选能力证据", "brain-circuit"),
             ("结果展示", "真实型号与两步耗时\n用户另行执行目标", "check-check")], h=1.85)
    card(s, .65, 4.62, 5.85, 1.60, "程序提供事实与校验", "区域可用性、模态、评测映射、候选 ID 合法性", glyph="shield-check", size=16)
    card(s, 6.8, 4.62, 5.85, 1.60, "模型决定流程与型号", "保留原始选择；不按排名自动替换，不强制三者一致", PURPLE, "list-filter", 16)
    note(s, "两次 /api/routing/decision；执行另用 /api/routing/execute。本批未运行目标任务。")

    s = new("四个任务，统一的候选事实", "模型路由 / 输入",
            "第一步看任务；第二步再看已选流程及型号评测。", routing_notes)
    table(s, ["场景", "任务核心", "三者共同选中的流程"], [
        ["支付客服", "USDC 已转出，确认数 3/12，解释待支付", "直接答复客户"],
        ["交易代码", "Webhook 去重、验签、Decimal、并发入账与测试", "编写代码与测试"],
        ["结算分析", "12000 应结算；11880 到账；0.8% 费率；24 暂扣", "核算与分析"],
        ["中英文索引", "将中英文支付工单转换为检索向量", "生成检索向量"],
    ], [1.5, 7.4, 3.1], rh=.68, size=15.5)
    L.label(s, "区域目录 124 条", .72, 5.97, 2.7)
    L.label(s, "文本候选 22 个", 3.8, 5.97, 2.7)
    L.label(s, "向量候选 3 个", 6.88, 5.97, 2.7)
    L.label(s, "LiveBench + MTEB", 9.96, 5.97, 2.65)
    note(s, "当前未启用 Artificial Analysis；缺少评测映射的型号仍可在目录查看，但不进入本批候选。")

    s = new("路由实测：速度领先，选择质量仍需检验", "模型路由 / 结果",
            "每格：目标型号 / 两步累计后端耗时；4 场景 × 3 模型 × 2 次调用。", routing_notes)
    rows = []
    for case, label in zip(CASES, CASE_NAMES, strict=True):
        row = [label]
        for provider in PROVIDERS:
            d = rt["cases"][case][provider]
            row.append(f"{d['model']}\n{d['total_ms']:.1f} ms")
        rows.append(row)
    table(s, ["场景", *LABELS], rows, [1.4, 3.55, 3.55, 3.5], rh=.80, size=16)
    text(s, "两步均值", .75, 6.37, 1.4, .29, 13, L.MUTED, True)
    for x, p, color in zip((2.3, 5.9, 9.5), PROVIDERS, COLORS, strict=True):
        text(s, f"{rt['timings'][p]['total_ms']:.1f} ms", x, 6.34, 2.8, .33, 18, color, True)
    note(s, "24/24 为有效返回，不是全部选对；每场景仅一次正式样本。首轮 GPT 超时另行保留。")

    s = new("客服与分析：保留差异，验证目标任务后再判优劣", "模型路由 / 实际界面",
            "同一输入产生不同型号；当前没有目标回答质量、生成延迟或实际费用的比较。", routing_notes)
    for y, case, label in [(2.12, "support", "支付客服"), (4.23, "analysis", "结算分析")]:
        text(s, label, .7, y, 2.4, .4, 19, L.TEAL, True)
        image = crop(case, (278, 1074, 1550, 1205), "models")
        L.picture(s, image, .72, y + .50, 11.86, 1.22, frame=True)
    note(s, "来自真实结果截图的型号区域裁剪；没有修改图片内的选择或数据。")

    s = new("交易代码：Jev 与 GPT 更贴合代码能力证据", "模型路由 / 实际界面",
            "三者都识别代码任务；Decider 选 Opus 5，其余两者选 Sonnet 5.5。", routing_notes)
    L.picture(s, crop("code", (260, 825, 1565, 1210), "results"), .72, 2.2, 11.86, 3.55, frame=True)
    text(s, "LiveBench Coding", .75, 5.97, 2.6, .36, 18, L.MUTED, True)
    text(s, "Opus 5：81.45", 3.65, 5.97, 3.3, .36, 21, L.TEAL, True)
    text(s, "Sonnet 5.5：91.37", 7.95, 5.97, 4.2, .36, 21, PURPLE, True)
    note(s, "Opus 5 综合分更高；接口没有给出选择理由。未生成并运行代码，不能直接断言代码一定失败。")

    s = new("中英文索引：Decider 的型号选择不合适", "模型路由 / 实际界面",
            "流程识别正确，但选择 Embed English；Jev / GPT 选择 Embed Multilingual。", routing_notes)
    L.picture(s, crop("retrieval", (260, 825, 1565, 1210), "results"), .72, 2.2, 11.86, 3.55, frame=True)
    text(s, "中文检索分", .75, 5.97, 2.6, .36, 18, L.MUTED, True)
    text(s, "English：4.18", 3.65, 5.97, 3.3, .36, 21, L.ORANGE, True)
    text(s, "Multilingual：60.65", 7.65, 5.97, 4.75, .36, 21, PURPLE, True)
    note(s, "MIRACL nDCG@10 × 100；当时三者收到相同名称与正确均分，分语言成绩仅用于本页分析。")

    s = new("正确上下文，还需要模型正确使用证据", "模型路由 / 结论",
            "改善输入协议不等于训练了模型；vLLM 提速也不会自动修正选型错误。", routing_notes)
    for x, title, body, color, glyph in [
        (.65, "已观察", "三者流程识别均正确\nDecider 索引型号选错\n代码选型依据较弱", L.TEAL, "scan-eye"),
        (4.79, "能得出的结论", "当前索引任务 Jev / GPT 更好\n代码选择更符合评测证据\n客服、分析需目标任务验证", PURPLE, "clipboard-check"),
        (8.93, "下一步验证", "更多任务与语言变体\n打乱候选顺序做对照\n运行目标任务，测质量与成本", L.BLUE, "target"),
    ]:
        card(s, x, 2.5, 3.74, 3.15, title, body, color, glyph, 17)
    text(s, "当前建议：优先继续评估 Jev 做模型选型；Decider 需要专项质量验收。", .8, 6.03, 11.8, .42, 20, L.INK, True)
    note(s, "四个任务不足以得出通用排名；没有内部推理证据，不能编造品牌偏好或指标权重作为原因。")

    for i in range(24, 28):
        keep(i)

    # 35–43: deployment and separately scoped performance batches.
    s = new("vLLM 适配：保留决策头，换成并发调度", "vLLM / 推理实现",
            "继续输出候选 ID、概率与置信度；不改造成逐 token 生成 JSON。", vllm_notes)
    flow(s, [("官方输入处理", "模板、tokenizer\n每请求独立候选位置", "receipt-text"),
             ("vLLM 调度", "Qwen3.5 + 已合并 LoRA\n完整 prefill 隐藏状态", "layers"),
             ("Pointer Head", "GPU 候选评分 + 温度校准\nBF16 底座 / FP32 头", "brain-circuit"),
             ("原答案转换", "choice / noul / score\n/v1/systemone", "check-check")], h=2.05)
    card(s, .65, 4.91, 5.85, 1.42, "保留", "官方模板、候选语义、权重与数值校验", glyph="shield-check", size=16)
    card(s, 6.8, 4.91, 5.85, 1.42, "改变", "多请求进入引擎调度，GPU 批量候选评分", PURPLE, "workflow", 16)
    note(s, "自定义 pooling 插件需要候选位置 metadata；普通 chat/completions 接口不是等价替代。")

    s = new("部署过程：导出 → 校验 → 容器 → 对齐", "vLLM / 可复现步骤",
            "固定 vLLM 0.31.0 与官方 Decider 源码提交；通过独立服务验证后再考虑集成。", vllm_notes)
    flow(s, [("1 合并导出", "官方加载器合并 LoRA\n保留原 head.safetensors", "code-xml"),
             ("2 检查产物", "清单与 SHA-256 校验\n不覆盖已有权重目录", "shield-check"),
             ("3 GPU 启动", "Docker + NVIDIA Runtime\n单 Uvicorn worker", "layers"),
             ("4 真实对齐", "选择一致；概率 / 置信度\n绝对偏差阈值 0.02", "check-check")], h=1.8)
    L.rect(s, .68, 4.62, 11.96, 1.53, L.NAVY, radius=True)
    text(s, "decider-vllm export --checkpoint CHECKPOINT --base BASE --output MODEL\n"
         "decider-vllm verify-artifacts --model MODEL\n"
         "decider-vllm serve --model MODEL --max-num-seqs 128 --max-num-batched-tokens 8192",
         .88, 4.83, 11.5, 1.17, 13.2, L.WHITE)
    note(s, "完整 prefill；前缀缓存、分块预填充和 CUDA Graph 均关闭。多问题独立提交，完整命令见来源链接。")

    s = new("独立公共 API：私网源站，GPU 持续驻留", "vLLM / AWS 架构",
            "与原支付 / 路由演示并行运行；当前演示仍调用官方原版推理服务。", vllm_notes)
    for x, glyph, title, body in [
        (.72, "client", "调用方", "Bearer API Key\nPOST /v1/systemone"),
        (3.85, "cloudfront", "CloudFront", "HTTPS\nVPC Origin 私网访问"),
        (6.98, "ec2", "EC2 g6.xlarge", "单张 L4 · 常驻\nvLLM 模型容器"),
        (10.11, "ebs", "EBS gp3", "160 GB 加密盘\n权重与运行缓存"),
    ]:
        L.rect(s, x, 2.4, 2.48, 2.5, L.WHITE, L.LINE, True)
        icon(s, glyph, x + .89, 2.6, .7, aws=True)
        text(s, title, x + .1, 3.51, 2.28, .4, 18, L.INK, True, PP_ALIGN.CENTER)
        text(s, body, x + .12, 4.06, 2.24, .67, 14.5, L.MUTED, align=PP_ALIGN.CENTER)
        if x < 10:
            L.line(s, [(x + 2.52, 3.62), (x + 3.05, 3.62)], L.TEAL, arrow=True)
    text(s, "部署：私有 S3 / ECR → SSM 安装与校验 → systemd 常驻 → HTTPS 验证", .8, 5.36, 11.8, .5, 18, L.TEAL, True)
    link(s, API + "/docs", API + "/docs", y=6.06)
    note(s, "服务端 HTTP / 问题准入 256；引擎序列上限 128。它们是上限，不代表 GPU 吞吐保证。")

    s = new("压测怎么做：固定输入，完整响应后再补请求", "vLLM / 测试方法",
            "20 条支付步骤输入；每个请求只包含一个选择题，测的是单次决策。", vllm_notes)
    card(s, .65, 2.4, 3.74, 3.55, "输入与用量", "四场景 × 五个独立步骤\nDecider：304–445 tokens\n平均 373.9 tokens\nJev：575–744 tokens\n平均 656.95 tokens", glyph="receipt-text", size=17)
    card(s, 4.79, 2.4, 3.74, 3.55, "负载与样本", "并发：1 → 128\n固定数量 worker\n每档 1280 次正式请求\n每条输入重复 64 次\n预热另存；失败不重试", PURPLE, "repeat-2", 17)
    card(s, 8.93, 2.4, 3.74, 3.55, "计时与统计", "客户端至完整响应\n包含网络、排队与处理\nRPS = 成功数 / 总时间\nP95 仅统计成功响应\n失败与数值偏差另报", L.BLUE, "timer", 17)
    note(s, "本页为公网 1–128 扫描口径。两服务 tokenizer / 用量口径不同；重复请求不是独立业务质量样本。")

    def comparison_plot(ax):
        for cells, label, color in [(reference, "官方原版", L.MUTED), (recheck, "vLLM 适配", L.TEAL)]:
            ax.plot(range(len(cells)), [r["successful_rps"] for r in cells], marker="o", linewidth=2.4, label=label, color="#" + color)
        ax.set_xticks(range(6), [str(r["concurrency"]) for r in reference])
        ax.set_xlabel("客户端并发")
        ax.set_ylabel("成功决策请求 / 秒")
        ax.set_ylim(0, 40)
        ax.legend(frameon=False)
    comparison = chart("original-vllm-rps", comparison_plot, 7.4, 3.9)
    s = new("同一块 L4：vLLM 在 8 并发约提升 2.36 倍吞吐", "vLLM / 原版对照",
            "相同权重与输入，两个服务分别独占 GPU；完整复测每档 80 次。", vllm_notes)
    L.picture(s, comparison, .65, 2.18, 7.65, 4.15)
    card(s, 8.55, 2.4, 4.1, 1.65, "8 并发吞吐", "14.76 → 34.91 次/秒", glyph="chart-no-axes-combined", size=22)
    card(s, 8.55, 4.40, 4.1, 1.65, "8 并发 P95", "542.8 → 237.6 ms", PURPLE, "timer", 22)
    note(s, "g6.4xlarge 同机；推理容器限制 4 vCPU / 14 GiB。三轮共 5 次超时保留；收益不只来自批处理。")

    s = new("1–128 并发：吞吐进入平台，等待时间持续增加", "vLLM / 公网扫描",
            "g6.xlarge · 单 L4 · 8192 token 预算；每档 1280 次，全部成功。", vllm_notes)
    table(s, ["并发", "成功次/秒", "平均 ms", "P95 ms", "P99 ms"], [
        [str(r["concurrency"]), f"{r['successful_rps']:.2f}", f"{r['mean_ms']:.1f}", f"{r['p95_ms']:.1f}", f"{r['p99_ms']:.1f}"] for r in sweep
    ], [1.5, 2.4, 2.7, 2.7, 2.7], rh=.44, size=15.5, highlights=(3, 7))
    text(s, "8 并发：33.84 次/秒      128 并发：29.65 次/秒，P95 4.99 秒", .75, 6.35, 11.8, .3, 17.5, L.TEAL, True)
    note(s, "含高并发复测共 12800 次成功；一次置信度差 0.0202 超过 0.02 阈值，候选选择仍一致。")

    bybudget = {r["max_num_batched_tokens"]: r["cells"] for r in batches["reports"] if "repeat" not in r["label"]}
    s = new("批次 token 预算更大，没有提高这批短输入吞吐", "vLLM / 调参实测",
            "每格为成功次/秒 / P95 毫秒；只改变 max_num_batched_tokens。", vllm_notes)
    table(s, ["并发", "8192 tokens", "16384 tokens", "32768 tokens"], [
        [str(n), *[f"{next(r for r in bybudget[b] if r['concurrency'] == n)['successful_rps']:.2f} / "
                  f"{next(r for r in bybudget[b] if r['concurrency'] == n)['p95_ms']:.1f}" for b in (8192, 16384, 32768)]]
        for n in (8, 16, 32, 64, 128)
    ], [1.5, 3.5, 3.5, 3.5], rh=.59, size=17)
    text(s, "当前保留 8192；先测实际批次和各层耗时，再决定下一项优化。", .78, 6.11, 11.8, .4, 19, L.TEAL, True)
    note(s, "本表使用该实验自己的基线；含复测共 23040/23040 成功。预算是上限，不等于实际批大小。")

    cells = {(r["provider"], r["concurrency"]): r for r in js["cells"]}
    levels = (1, 2, 4, 8, 16, 32, 64, 128)
    s = new("vLLM vs Jev：低并发延迟与高并发吞吐各有优势", "vLLM / Jev 直接对比",
            "相同 20 条业务输入、相同客户端；Decider 经 CloudFront，Jev 直接访问供应商 API。", vllm_notes)
    table(s, ["并发", "vLLM 次/秒", "平均 / P95 ms", "Jev 次/秒", "平均 / P95 ms"], [
        [str(n), f"{cells['decider', n]['successful_rps']:.2f}",
         f"{cells['decider', n]['latency_ms']['mean']:.1f} / {cells['decider', n]['latency_ms']['p95']:.1f}",
         f"{cells['jev', n]['successful_rps']:.2f}",
         f"{cells['jev', n]['latency_ms']['mean']:.1f} / {cells['jev', n]['latency_ms']['p95']:.1f}"]
        for n in levels
    ], [1.0, 2.05, 3.45, 2.05, 3.45], rh=.44, size=15, highlights=(0, 5, 7))
    note(s, "正式成功：vLLM 10239/10240，Jev 10240/10240；预热各 560 次另存。两者基础设施不同。")

    s = new("选择并发档位，要同时看尾延迟与失败", "vLLM / 性能结论",
            "Jev 32 并发较长复测保持约 245 次/秒；128 并发出现明显退化。", vllm_notes)
    card(s, .65, 2.4, 3.74, 3.5, "低并发", "并发 1 平均延迟\nvLLM：55.4 ms\nJev：126.5 ms\n\n本批 vLLM 更快", glyph="timer", size=18)
    card(s, 4.79, 2.4, 3.74, 3.5, "中等并发", "并发 32 成功吞吐\nvLLM：30.61 次/秒\nJev：240.94 次/秒\n\n本批 Jev 更高", PURPLE, "chart-no-axes-combined", 18)
    card(s, 8.93, 2.4, 3.74, 3.5, "高并发尾部", "并发 128 的 P95\nvLLM：11.24 秒\nJev：5.50 秒\n\n继续加并发会增加等待", L.ORANGE, "scan-eye", 18)
    note(s, "vLLM 有一次 HTTP 502、十次数值偏差超阈值；Jev 128 并发较长复测 P95 7.31 秒。均保留。")

    # 44–46: list prices grounded in API usage, with workload-specific break-even.
    s = new("成本：g6.2xlarge 常驻，与 Jev 按量计费", "成本 / 公开价格与实测用量",
            "us-east-1 · Linux On-Demand · USD；以真实 token 用量计算公开单价估算。", cost_notes)
    card(s, .65, 2.35, 5.85, 2.82, "Strands Decider 自部署", "$0.9776 / 小时\n730 小时：$713.65 / 月\n160 GB gp3：另加 $12.80 / 月\n计算 + 磁盘：$726.45 / 月", glyph="banknote", size=21)
    card(s, 6.8, 2.35, 5.85, 2.82, "Jev API", "$0.042 / 百万输入 tokens\n输出免费\n实测每次平均 656.95 输入 tokens\n约 $27.59 / 百万次决策", PURPLE, "receipt-text", 21)
    text(s, "实测 10240 次 Jev 请求：6727168 输入 tokens → 按公开价约 $0.283", .8, 5.66, 11.8, .5, 19, L.INK, True)
    note(s, "公开价估算，不是账单。g6.2xlarge 未实测容量；本页不将 g6.xlarge 吞吐直接套用。")
    link(s, "来源：AWS 按需价格", "https://aws.amazon.com/ec2/pricing/on-demand/", y=6.34, w=4.8)
    link(s, "来源：Jev 官方价格说明", "https://typesafe.ai/blog/introducing-system-one-models-and-jev", x=6.8, y=6.34, w=5.6)

    def cost_plot(ax):
        xs = [0, 1, 5, 10, 20, 25.86440223399, 30, 40, 50]
        ax.plot(xs, [cost["jev_usd_per_million_decisions"] * x for x in xs], color="#" + PURPLE, linewidth=2.5, label="Jev：按实测平均输入")
        ax.axhline(cost["instance_monthly_usd"], color="#" + L.TEAL, linewidth=2.5, label="g6.2xlarge：730小时计算费")
        ax.scatter([cost["compute_breakeven_decisions_per_month"] / 1e6], [cost["instance_monthly_usd"]], color="#" + L.ORANGE, s=55, zorder=5)
        ax.set_xlabel("每月单次决策请求量（百万次）")
        ax.set_ylabel("美元 / 月")
        ax.legend(frameon=False, loc="upper left", fontsize=10)
        ax.set_xlim(0, 50)
        ax.set_ylim(0, 1500)
    curve = chart("monthly-cost", cost_plot, 7.6, 4.2)
    s = new("按这批短输入，约 2586 万次/月达到计算费交点", "成本 / 用量敏感性",
            "一次决策平均 656.95 Jev 输入 tokens；常驻 GPU 即使空闲也计时收费。", cost_notes)
    L.picture(s, curve, .60, 2.13, 7.70, 4.27)
    table(s, ["月决策量", "Jev", "EC2 计算"], [
        [f"{n} 百万", f"${cost['jev_usd_per_million_decisions'] * n:.2f}", "$713.65"]
        for n in (1, 10, 30)
    ], [1.45, 1.40, 1.45], x=8.33, y=2.53, rh=.57, size=14)
    text(s, "交点平均约 9.84 次/秒\n加磁盘后约 2633 万次/月", 8.48, 5.13, 3.95, .92, 18, L.TEAL, True)
    note(s, "交点仅比较费用公式，不保证单卡满足容量或 SLA；网络、运维、冗余、折扣、税费另计。")

    s = new("任务变长、一次路由两次判断，成本也会改变", "成本 / 模型路由用量",
            "用路由实测的 Jev usage 重新计算；不能套用支付单步的 656.95 tokens。", cost_notes + "\n" + routing_notes)
    table(s, ["路由任务", "两次调用输入 tokens", "Jev / 百万次完整路由"], [
        [name, str(cost["routing_cases"][case]["input_tokens"]), f"${cost['routing_cases'][case]['usd_per_million_routes']:.2f}"]
        for case, name in zip(CASES, CASE_NAMES, strict=True)
    ], [3.2, 4.2, 4.6], rh=.64, size=18)
    text(s, "四场景等权平均：$117.84 / 百万次路由", .8, 5.77, 11.8, .45, 22, PURPLE, True)
    text(s, "g6.2xlarge 计算费交点约 606 万次路由/月；目标模型执行费用另计。", .8, 6.29, 11.8, .3, 16.5, L.TEAL, True)
    note(s, "这是同等四场景配比的价格模型，非月度实测账单；尚未测量 g6.2xlarge 对路由长输入的吞吐。")

    keep(28)
    summary = keep(29)
    for sh in summary.shapes:
        if sh.has_text_frame:
            replace_text(sh, "总结：同时看速度、选择和真实业务结果", "支付演示回顾：速度、选择和真实业务结果")
    manifests[-1]["title"] = "支付演示回顾：速度、选择和真实业务结果"

    s = new("最终选型：质量、性能、成本分别验收", "总结 / 新增实测",
            "同一模型可以决策很快，同时仍在某些业务上选错；引擎优化与质量优化分开推进。",
            routing_notes + "\n\n" + vllm_notes + "\n\n" + cost_notes)
    card(s, .65, 2.30, 5.85, 1.75, "路由质量", "索引选型：Jev / GPT 优于 Decider。\n扩大任务集，并运行目标任务验收。", glyph="target", size=16.8)
    card(s, 6.8, 2.30, 5.85, 1.75, "推理性能", "同机 8 并发吞吐约为原版的 2.36 倍。\n公网先从 4–8 并发评估负载。", PURPLE, "timer", 16.8)
    card(s, .65, 4.44, 5.85, 1.75, "托管服务", "Jev 在本批 8–32 并发时吞吐更高。\n提高并发前，核对尾延迟与失败。", L.BLUE, "workflow", 16.8)
    card(s, 6.8, 4.44, 5.85, 1.75, "成本决策", "低用量优先评估按量服务。\n高稳定用量再核算自部署与运维。", L.ORANGE, "banknote", 16.8)
    note(s, "本版使用已有实测与当日公开价格；没有进行新的微调、g6.2xlarge 压测或原演示的引擎迁移。")

    end = keep(30)
    for sh in end.shapes:
        if not sh.has_text_frame:
            continue
        replace_text(sh, "加密支付业务台 · 使用现有账号登录", "支付流程 + 模型路由\n使用现有账号登录")
        replace_text(sh, "公开基准  benchmarkheaven.com/jev-models/api", "vLLM 项目  github.com/milan9527/StrandsDeciderVLLM")
        if sh.text.startswith("vLLM 项目"):
            for paragraph in sh.text_frame.paragraphs:
                for run in paragraph.runs:
                    run.hyperlink.address = VREPO
        replace_text(sh, "原理来源：Strands 官方博客、官方模型卡、TypeSafe System One；完整链接与测量口径见逐页讲稿。",
                     "路由入口：Demo /#routing  ·  vLLM API：d1e9udi8st2p3g.cloudfront.net/docs  ·  基准及来源见讲稿。")
    end.notes_slide.notes_text_frame.text += f"\n模型路由：{DEMO}/#routing\nvLLM API：{API}/docs\nvLLM Repo：{VREPO}\n"

    assert len(order) == len(prs.slides) == PAGE_COUNT
    ids = prs.slides._sldIdLst
    for sid in list(ids):
        ids.remove(sid)
    for sid in order:
        ids.append(sid)

    cover = prs.slides[0]
    for sh in cover.shapes:
        if not sh.has_text_frame:
            continue
        replace_text(sh, "v8 · 三模型与 JevBench · 30 页", "v9 · 适用场景 / 模型路由 / vLLM / 成本 · 52 页")
        replace_text(sh, "Strands Decider × Jev × GPT：从公开基准，到支付流程中的真实表现",
                     "Strands Decider × Jev × GPT：支付、模型路由、并发性能与部署成本")
        replace_text(sh, "公开基准 + 四个支付场景\n速度、选择、实际执行", "支付 + 模型路由实测\n速度、选择、实际执行")
        replace_text(sh, "如何优化 Decider？\n哪些任务交给哪类模型？", "质量优化 + vLLM 提速\n用真实用量比较成本")
        replace_text(sh, "模型原理 → 公开基准 → 项目实测 → 差异解释 → 优化路径  ·  2026.10.12",
                     "模型原理 → 业务决策 → 模型路由 → vLLM 性能 → 成本与选型  ·  2026.10.13")

    for i, (slide, meta) in enumerate(zip(prs.slides, manifests, strict=True), 1):
        # Preserve v8 content and embedded relationships, replacing only shared footers.
        for sh in list(slide.shapes):
            if sh.top >= Inches(7.03):
                slide.shapes._spTree.remove(sh._element)
        dark = i == 1
        color = "B8C9DB" if dark else L.MUTED
        L.line(slide, [(.62, 7.04), (12.68, 7.04)], "425769" if dark else L.LINE, .6)
        text(slide, "原理与支付 → 模型路由 → 质量优化 → vLLM 性能 → 成本与选型",
             .63, 7.15, 10.8, .21, 9, color)
        text(slide, f"{i:02} / {PAGE_COUNT}", 11.76, 7.14, .92, .23, 10, color, align=PP_ALIGN.RIGHT)
        for effect in slide._element.xpath(".//a:effectRef"):
            effect.set("idx", "0")
        for sh in slide.shapes:
            assert min(sh.left, sh.top) >= 0, (i, sh.name)
            assert sh.left + sh.width <= prs.slide_width + 12, (i, sh.name)
            assert sh.top + sh.height <= prs.slide_height + 12, (i, sh.name)
        meta["page"] = i

    prs.core_properties.title = "Strands Decider × Jev × GPT：业务决策、模型路由、vLLM 与成本"
    prs.core_properties.subject = "基于v8保留支付演示，加入路由实测、vLLM部署并发、g6.2xlarge与Jev成本"
    prs.core_properties.comments = "v9; measured performance, source screenshots, list-price cost estimates; see notes."
    target = OUT / f"{NAME}.pptx"
    prs.save(target)
    (OUT / "讲稿与来源.md").write_text(
        f"# v9 · {PAGE_COUNT} 页 · 逐页讲稿与来源\n\n"
        + "\n\n".join(f"## {i:02}. {meta['title']}\n\n{sl.notes_slide.notes_text_frame.text}"
                     for i, (sl, meta) in enumerate(zip(prs.slides, manifests, strict=True), 1)) + "\n"
    )
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "base_file": str(BASE.relative_to(ROOT)), "base_sha256": base_hash,
        "pptx_file": str(target.relative_to(ROOT)), "pptx_sha256": digest(target),
        "base_pages_preserved": 30, "new_pages": PAGE_COUNT - 30, "slides": manifests,
        "preserved_body_except_pages": [1, 29, 30],
        "new_live_model_calls": 0, "g6_2xlarge_performance_tested": False,
        "cost_basis": "public list prices applied to actual reported input-token usage; not invoice",
        "crops": crops, "routing_results_sha256": digest(routing_path / "results.json"),
        "source_files": {str(p.relative_to(OUT)): digest(p) for p in SOURCES.rglob("*") if p.is_file()},
        "cost_calculation": cost,
    }
    (OUT / "build-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    assert digest(BASE) == base_hash
    print(f"Created {target.relative_to(ROOT)}: {PAGE_COUNT} pages; v8 unchanged.")


if __name__ == "__main__":
    main()
