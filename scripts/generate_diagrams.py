"""Generate editable draw.io pages and matching SVG previews using only stdlib."""

from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "diagrams"
FONT = "Noto Sans CJK SC"
INK = "#1c3045"
MUTED = "#52677c"
TEAL = "#0f766e"
BLUE = "#3159ac"
ORANGE = "#b86c14"
PALETTES = {
    "neutral": ("#ffffff", "#b9c8d5", INK),
    "teal": ("#e9f6f2", "#72b5a5", "#155e55"),
    "blue": ("#edf2ff", "#9aaedf", BLUE),
    "orange": ("#fff5e7", "#ddb775", "#855116"),
    "gray": ("#f2f5f8", "#c5cfda", MUTED),
}


class Page:
    def __init__(self, name, slug, subtitle, width=1600, height=1150):
        self.name, self.slug = name, slug
        self.width, self.height = width, height
        self.nodes, self.edges = [], []
        self.box("title", 40, 24, width - 80, 48, name, size=30, text=True)
        self.box("subtitle", 40, 80, width - 80, 38, subtitle, size=16, text=True)

    def box(self, key, x, y, w, h, label, palette="neutral", size=18, text=False, group=False):
        self.nodes.append(
            dict(
                id=key,
                x=x,
                y=y,
                w=w,
                h=h,
                label=label,
                palette=palette,
                size=size,
                text=text,
                group=group,
            )
        )
        return key

    def edge(self, source, target, points, label="", color=MUTED, dashed=False, at=None):
        self.edges.append(
            dict(
                source=source,
                target=target,
                points=points,
                label=label,
                color=color,
                dashed=dashed,
                at=at,
            )
        )

    def xml(self):
        diagram = ET.Element("diagram", {"id": self.slug, "name": self.name})
        model = ET.SubElement(
            diagram,
            "mxGraphModel",
            dict(
                dx=str(self.width),
                dy=str(self.height),
                grid="1",
                gridSize="10",
                guides="1",
                tooltips="1",
                connect="1",
                arrows="1",
                fold="1",
                page="1",
                pageScale="1",
                pageWidth=str(self.width),
                pageHeight=str(self.height),
                math="0",
                shadow="0",
            ),
        )
        root = ET.SubElement(model, "root")
        ET.SubElement(root, "mxCell", id="0")
        ET.SubElement(root, "mxCell", id="1", parent="0")
        lookup = {n["id"]: n for n in self.nodes}
        assert len(lookup) == len(self.nodes)
        for node in self.nodes:
            fill, stroke, font = PALETTES[node["palette"]]
            style = (
                f"rounded=1;arcSize=12;whiteSpace=wrap;html=0;fontFamily={FONT};"
                f"fontSize={node['size']};fontColor={font};strokeWidth=1.5;"
                f"fillColor={fill};strokeColor={stroke};spacing=12;"
            )
            if node["text"]:
                style += "fillColor=none;strokeColor=none;align=left;fontStyle=1;"
            if node["group"]:
                style += "verticalAlign=top;align=left;fontStyle=1;dashed=1;spacingTop=14;"
            cell = ET.SubElement(
                root,
                "mxCell",
                id=node["id"],
                value=node["label"],
                style=style,
                vertex="1",
                parent="1",
            )
            ET.SubElement(
                cell,
                "mxGeometry",
                {
                    "x": str(node["x"]),
                    "y": str(node["y"]),
                    "width": str(node["w"]),
                    "height": str(node["h"]),
                    "as": "geometry",
                },
            )
        for i, edge in enumerate(self.edges):
            a, b = lookup[edge["source"]], lookup[edge["target"]]
            start, end = edge["points"][0], edge["points"][-1]
            style = (
                f"edgeStyle=none;rounded=0;html=0;endArrow=block;endFill=1;"
                f"strokeWidth=2;strokeColor={edge['color']};fontColor={edge['color']};"
                f"fontFamily={FONT};fontSize=14;labelBackgroundColor=#ffffff;"
                f"exitX={(start[0] - a['x']) / a['w']};exitY={(start[1] - a['y']) / a['h']};"
                f"entryX={(end[0] - b['x']) / b['w']};entryY={(end[1] - b['y']) / b['h']};"
                "exitPerimeter=0;entryPerimeter=0;"
            )
            if edge["dashed"]:
                style += "dashed=1;dashPattern=6 4;"
            cell = ET.SubElement(
                root,
                "mxCell",
                id=f"edge-{i}",
                value="",
                style=style,
                edge="1",
                parent="1",
                source=edge["source"],
                target=edge["target"],
            )
            geo = ET.SubElement(cell, "mxGeometry", {"relative": "1", "as": "geometry"})
            if len(edge["points"]) > 2:
                array = ET.SubElement(geo, "Array", {"as": "points"})
                for x, y in edge["points"][1:-1]:
                    ET.SubElement(array, "mxPoint", x=str(x), y=str(y))
            if edge["label"]:
                x, y = edge["at"]
                label = ET.SubElement(
                    root,
                    "mxCell",
                    id=f"edge-label-{i}",
                    value=edge["label"],
                    style=f"text;html=0;strokeColor=none;fillColor=#ffffff;align=center;verticalAlign=middle;fontFamily={FONT};fontSize=14;fontColor={edge['color']};",
                    vertex="1",
                    parent="1",
                )
                ET.SubElement(
                    label,
                    "mxGeometry",
                    {
                        "x": str(x - 120),
                        "y": str(y - 13),
                        "width": "240",
                        "height": "26",
                        "as": "geometry",
                    },
                )
        return diagram

    def svg(self):
        svg = ET.Element(
            "svg",
            xmlns="http://www.w3.org/2000/svg",
            width=str(self.width),
            height=str(self.height),
            viewBox=f"0 0 {self.width} {self.height}",
            role="img",
        )
        ET.SubElement(svg, "title").text = self.name
        ET.SubElement(svg, "desc").text = "Editable source: strands-decider-demo.drawio"
        defs = ET.SubElement(svg, "defs")
        for color in (MUTED, TEAL, BLUE, ORANGE):
            marker = ET.SubElement(
                defs,
                "marker",
                id="arrow" + color[1:],
                markerWidth="10",
                markerHeight="10",
                refX="9",
                refY="5",
                orient="auto",
                markerUnits="userSpaceOnUse",
            )
            ET.SubElement(marker, "path", d="M 0 0 L 10 5 L 0 10 Z", fill=color)
        ET.SubElement(svg, "rect", width="100%", height="100%", fill="#ffffff")
        for node in self.nodes:
            fill, stroke, font = PALETTES[node["palette"]]
            if not node["text"]:
                attrs = dict(
                    x=str(node["x"]),
                    y=str(node["y"]),
                    width=str(node["w"]),
                    height=str(node["h"]),
                    rx="12",
                    fill=fill,
                    stroke=stroke,
                )
                if node["group"]:
                    attrs["stroke-dasharray"] = "7 5"
                ET.SubElement(svg, "rect", attrs)
            lines = node["label"].split("\n")
            line_height = node["size"] * 1.5
            left = node["text"] or node["group"]
            x = node["x"] + 16 if left else node["x"] + node["w"] / 2
            y = (
                node["y"] + 30
                if node["group"]
                else node["y"]
                + (node["h"] - (len(lines) - 1) * line_height) / 2
                + node["size"] * 0.35
            )
            for i, line in enumerate(lines):
                attrs = {
                    "x": str(x),
                    "y": str(y + i * line_height),
                    "font-family": f"'{FONT}', 'Microsoft YaHei', sans-serif",
                    "font-size": str(node["size"]),
                    "fill": font,
                    "text-anchor": "start" if left else "middle",
                }
                if i == 0:
                    attrs["font-weight"] = "700"
                ET.SubElement(svg, "text", attrs).text = line
        for edge in self.edges:
            attrs = {
                "points": " ".join(f"{x},{y}" for x, y in edge["points"]),
                "fill": "none",
                "stroke": edge["color"],
                "stroke-width": "2",
                "stroke-linejoin": "round",
                "marker-end": f"url(#arrow{edge['color'][1:]})",
            }
            if edge["dashed"]:
                attrs["stroke-dasharray"] = "7 5"
            ET.SubElement(svg, "polyline", attrs)
            if edge["label"]:
                x, y = edge["at"]
                ET.SubElement(
                    svg,
                    "rect",
                    x=str(x - 120),
                    y=str(y - 13),
                    width="240",
                    height="26",
                    fill="#ffffff",
                )
                ET.SubElement(
                    svg,
                    "text",
                    {
                        "x": str(x),
                        "y": str(y + 5),
                        "font-family": f"'{FONT}', sans-serif",
                        "font-size": "14",
                        "fill": edge["color"],
                        "text-anchor": "middle",
                    },
                ).text = edge["label"]
        return svg


def architecture():
    p = Page(
        "01  AWS 部署架构",
        "architecture",
        "区域：us-east-1 ｜ 前后端分离 ｜ 自建账号登录 ｜ SageMaker Decider + Bedrock GPT-6.1 Sol",
        height=1240,
    )
    p.box("aws", 40, 300, 1520, 880, "AWS · us-east-1 部署与调用入口", "gray", group=True)
    p.box("vpc", 70, 360, 1460, 480, "应用 VPC", group=True)
    p.box("vpc-note", 445, 365, 620, 35, "无 Internet 默认路由 · ECS 无公网 IP", size=17, text=True)
    p.box("browser", 60, 150, 290, 105, "浏览器 / 中文演示界面\n登录 · 逐步结果 · 对比与导出")
    p.box("cf", 470, 150, 360, 105, "Amazon CloudFront（全球）\nHTTPS · 单一访问入口", "orange")
    p.box(
        "s3",
        1040,
        150,
        480,
        105,
        "S3 静态站点（us-east-1）\nBlock Public Access 全开 · OAC 签名访问",
        "orange",
    )
    p.box("alb", 105, 435, 260, 105, "内网 ALB\n/api/* 路由")
    p.box(
        "api",
        455,
        405,
        500,
        165,
        "ECS Fargate / FastAPI\n认证 · 同一输入构造 · 模型调用与计时\n参考差异提示 · 资金/结案保护 · 模拟执行",
        "teal",
    )
    p.box("smvpce", 1090, 405, 360, 85, "SageMaker Runtime\n私有 Interface Endpoint", "teal")
    p.box("brvpce", 1090, 535, 360, 85, "Bedrock Runtime\n私有 Interface Endpoint", "blue")
    p.box("ddbvpce", 465, 690, 480, 75, "DynamoDB Gateway Endpoint\n认证 / GPU 状态访问", "gray")
    p.box(
        "sm",
        1010,
        880,
        470,
        115,
        "SageMaker 实时推理 Endpoint\nDecider v19 · ml.g6.xlarge · L4 / CUDA\n网络隔离 · 权重预置于镜像",
        "teal",
    )
    p.box(
        "br",
        1010,
        1035,
        470,
        100,
        "Amazon Bedrock 托管模型\nus.openai.gpt-6.1-sol · reasoning low\n美国跨区域推理配置",
        "blue",
        size=17,
    )
    p.box(
        "ddb", 470, 900, 430, 95, "DynamoDB\n账号 / 会话 / 限流 + GPU 状态 / 租约", "gray", size=17
    )
    p.box(
        "lambda",
        90,
        1035,
        340,
        105,
        "GPU 控制 Lambda\n按状态创建 / 删除固定 Endpoint\n闲置 30 分钟自动删除",
        "orange",
        size=17,
    )
    p.box("timer", 90, 880, 340, 85, "EventBridge 定时规则\n每分钟触发控制器", "orange")
    p.box(
        "retain",
        485,
        1035,
        415,
        105,
        "保留配置与回退资源\nECR 镜像 / Model / EndpointConfig\n旧 EC2 已停止，80GB EBS 保留",
        "gray",
        size=17,
    )
    p.edge("browser", "cf", [(350, 202), (470, 202)])
    p.edge("cf", "s3", [(830, 202), (1040, 202)], "静态资源 · OAC", at=(935, 186))
    p.edge(
        "cf",
        "alb",
        [(530, 255), (530, 340), (235, 340), (235, 435)],
        "VPC Origin · /api/*",
        at=(410, 340),
    )
    p.edge("alb", "api", [(365, 487), (455, 487)])
    p.edge("api", "smvpce", [(955, 447), (1090, 447)], color=TEAL)
    p.edge("api", "brvpce", [(955, 530), (1020, 530), (1020, 577), (1090, 577)], color=BLUE)
    p.edge("api", "ddbvpce", [(705, 570), (705, 690)], "账号认证 / GPU 请求与租约", at=(705, 632))
    p.edge("ddbvpce", "ddb", [(705, 765), (705, 900)])
    p.edge(
        "smvpce",
        "sm",
        [(1450, 447), (1500, 447), (1500, 865), (1245, 865), (1245, 880)],
        color=TEAL,
    )
    p.edge("brvpce", "br", [(1090, 577), (980, 577), (980, 1085), (1010, 1085)], color=BLUE)
    p.edge("timer", "lambda", [(260, 965), (260, 1035)], color=ORANGE, dashed=True)
    p.edge(
        "lambda",
        "ddb",
        [(430, 1060), (450, 1060), (450, 947), (470, 947)],
        color=ORANGE,
        dashed=True,
    )
    p.edge(
        "lambda",
        "sm",
        [(430, 1120), (455, 1120), (455, 1170), (1535, 1170), (1535, 937), (1480, 937)],
        color=ORANGE,
        dashed=True,
    )
    p.box(
        "legend",
        45,
        1188,
        1510,
        40,
        "实线：请求/访问方向（响应省略）   虚线：GPU 控制路径   业务订单/账本仅在浏览器内存中模拟；不接钱包、不广播链上交易。",
        size=15,
        text=True,
    )
    return p


def comparison():
    p = Page(
        "02  Decider vs 普通大模型：本演示的实际调用流程",
        "model-comparison",
        "比较相同的有限候选决策任务；普通大模型本可自由生成文本，本演示将其输出约束为同样的候选 ID。",
        height=1330,
    )
    p.box(
        "input",
        340,
        140,
        920,
        95,
        "应用准备输入（候选项由开发者提供）\n同一业务事实 state + 问题 instructions + 候选项 criteria → 相同 input_hash",
        "neutral",
    )
    p.box("left", 60, 285, 710, 655, "A  Strands Decider · 专用决策模型", "teal", group=True)
    p.box(
        "right", 830, 285, 710, 655, "B  普通生成式大模型 · Bedrock GPT-6.1 Sol", "blue", group=True
    )
    p.box(
        "drequest",
        130,
        350,
        570,
        85,
        "应用构造 choice 请求\n给定业务事实与候选动作，要求选一项",
        "teal",
    )
    p.box(
        "grequest",
        900,
        350,
        570,
        85,
        "应用构造 Converse 请求\n相同业务 payload + 仅输出候选 ID JSON 的要求",
        "blue",
    )
    p.box(
        "dinfer",
        130,
        490,
        570,
        110,
        "SageMaker InvokeEndpoint → Decider v19\n官方 System One 模型服务 / L4 GPU\nGPU 租约与串行推理；独立测量每步",
        "teal",
    )
    p.box(
        "ginfer",
        900,
        490,
        570,
        110,
        "Bedrock Converse → GPT-6.1 Sol\nreasoning effort = low / maxTokens = 1024\n生成文本形式的决策 JSON",
        "blue",
    )
    p.box(
        "dresult",
        130,
        655,
        570,
        100,
        "读取结构化模型响应\nchoice + probabilities + confidence\n验证候选 ID、分布与响应字段",
        "teal",
    )
    p.box(
        "gresult",
        900,
        655,
        570,
        100,
        "解析生成的 JSON 并验证\n仅允许 choice，且必须属于候选列表\n记录输入/输出 tokens，不伪造概率",
        "blue",
    )
    p.box(
        "dmetric", 130, 815, 570, 85, "保留原始选择与概率\n记录每步耗时；GPU 按运行时间计费", "teal"
    )
    p.box(
        "gmetric",
        900,
        815,
        570,
        85,
        "保留原始选择与 token 使用量\n记录每步耗时；未核实单价，不估算美元成本",
        "blue",
        size=17,
    )
    p.edge("input", "drequest", [(570, 235), (570, 260), (415, 260), (415, 350)], color=TEAL)
    p.edge("input", "grequest", [(1030, 235), (1030, 260), (1185, 260), (1185, 350)], color=BLUE)
    for prefix, x, color in [("d", 415, TEAL), ("g", 1185, BLUE)]:
        p.edge(prefix + "request", prefix + "infer", [(x, 435), (x, 490)], color=color)
        p.edge(prefix + "infer", prefix + "result", [(x, 600), (x, 655)], color=color)
        p.edge(prefix + "result", prefix + "metric", [(x, 755), (x, 815)], color=color)
    p.box(
        "execution",
        320,
        995,
        960,
        125,
        "相同的应用执行策略 · 两侧各有独立沙盒状态\n参考选择不同 → 仅提示，继续流程\n资金/结案条件不足 → 挂起或持续跟进，记录保护调整并继续",
        "orange",
    )
    p.edge("dmetric", "execution", [(415, 900), (415, 970), (570, 970), (570, 995)], color=TEAL)
    p.edge("gmetric", "execution", [(1185, 900), (1185, 970), (1030, 970), (1030, 995)], color=BLUE)
    p.box(
        "outcome",
        320,
        1170,
        960,
        100,
        "最终结果：五步执行记录 + 订单/工单状态 + 模拟账本 + 模板客服回复\n对比：同输入动作、参考一致、保护调整、每步/合计时间\n真实请求失败明确显示；不会用规则回放替代模型输出",
        "neutral",
        size=17,
    )
    p.edge("execution", "outcome", [(800, 1120), (800, 1170)], color=ORANGE)
    p.box(
        "note",
        55,
        1280,
        1490,
        35,
        "范围：客服文字理解与动作选择；不比较自由长文本生成、不调用真实交易工具。后端保护调整不会计作模型正确输出。",
        size=15,
        text=True,
    )
    return p


def workflow():
    p = Page(
        "03  加密支付：五步完整流程与结果",
        "payment-workflow",
        "四个场景：USDC 未到账 / USDT 少付 / 稳定币退款 / 商户结算 ｜ 全部为模拟业务数据",
        height=1120,
    )
    p.box(
        "evidence",
        70,
        145,
        1460,
        95,
        "冻结本轮证据版本\n客户诉求 + 到账金额 + 确认数 + 地址验证 + 人工审批 + 风险标记 + 结算状态\n两模型收到同一版本；每一步并发调用两模型，五步决策按顺序进行",
        "gray",
        size=18,
    )
    stages = [
        ("intake", "01 客服受理", "选择客服队列\n支付 / 退款 / 商户"),
        ("verify", "02 交易核验", "读取金额与确认\n或结算进度"),
        ("approve", "03 风控审批", "选择通过 / 复核\n验证地址 / 等待审批"),
        ("execute", "04 业务处置", "入账 / 退款 / 对账\n或挂起 / 升级"),
        ("close", "05 回复结案", "选择结案或跟进\n供后续选择回复模板"),
    ]
    for i, (key, title, body) in enumerate(stages):
        x = 70 + i * 300
        p.box(key, x, 315, 260, 125, f"{title}\n{body}", "teal", size=18)
        if i:
            p.edge(stages[i - 1][0], key, [(x - 40, 377), (x, 377)], color=TEAL)
    p.edge(
        "evidence",
        "intake",
        [(800, 240), (800, 280), (200, 280), (200, 315)],
        "获得两套五步建议",
        at=(800, 280),
    )
    p.box(
        "plans",
        200,
        505,
        1200,
        90,
        "分别按序执行两套方案 · Decider 与 GPT 各自拥有独立模拟订单、工单、账本\n执行到每步时重新检查实际状态；原始模型选择与实际动作分别保存",
        "neutral",
        size=19,
    )
    p.edge("close", "plans", [(1400, 440), (1400, 470), (800, 470), (800, 505)])
    p.box(
        "advisory",
        80,
        675,
        420,
        130,
        "参考差异：允许继续\n例如普通支付选择「等待人工审批」\n保留原始模型动作；不再卡在 2/5\n后续资金可挂起，客服流程继续",
        "teal",
        size=17,
    )
    p.box(
        "guard",
        590,
        675,
        420,
        130,
        "资金 / 结案保护：调整后继续\n少付入账、未审批退款 → 挂起\n实际业务未完成却要求结案 → 跟进\n记录 requested_action 与实际 action",
        "orange",
        size=17,
    )
    p.box(
        "failure",
        1100,
        675,
        420,
        130,
        "调用失败：明确显示未完成\n模型 / 网络 / 响应校验失败不伪造结果\n执行请求失败可重试剩余步骤\n非法、乱序、重复动作仍被拒绝",
        "gray",
        size=17,
    )
    p.edge("plans", "advisory", [(450, 595), (450, 635), (290, 635), (290, 675)], color=TEAL)
    p.edge("plans", "guard", [(800, 595), (800, 675)], color=ORANGE)
    p.edge("plans", "failure", [(1150, 595), (1150, 635), (1310, 635), (1310, 675)], dashed=True)
    p.box(
        "final",
        160,
        865,
        1280,
        100,
        "5/5 步完成 ≠ 资金业务已完成\n订单：待处理 / 已收款 / 模拟退款 / 已对账     工单：持续跟进 / 已结案\n客服回复依据实际执行状态；挂起不显示为已付款或已退款",
        "neutral",
        size=20,
    )
    p.edge("advisory", "final", [(290, 805), (290, 835), (530, 835), (530, 865)], color=TEAL)
    p.edge("guard", "final", [(800, 805), (800, 865)], color=ORANGE)
    p.box(
        "events",
        80,
        1010,
        1440,
        75,
        "继续演示：模拟确认数达标 / 补足差额 / 验证地址 / 审批通过 / 结算到账 → 清除旧结果，重新开始\n「客服会话 → 推进模拟交易」点击事件后，显示系统通知与前后数值（如 3/12 → 12/12），保留历史回复；再重新运行。",
        "gray",
        size=17,
    )
    return p


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pages = [architecture(), comparison(), workflow()]
    document = ET.Element(
        "mxfile", host="app.diagrams.net", type="device", version="24.7.17", pages=str(len(pages))
    )
    for page in pages:
        document.append(page.xml())
        svg = page.svg()
        ET.indent(svg)
        ET.ElementTree(svg).write(OUT / f"{page.slug}.svg", encoding="utf-8", xml_declaration=True)
    ET.indent(document)
    ET.ElementTree(document).write(
        OUT / "strands-decider-demo.drawio", encoding="utf-8", xml_declaration=True
    )
    print(f"Generated {len(pages)} editable pages and SVG previews in {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
