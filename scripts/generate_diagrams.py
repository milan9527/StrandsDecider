"""Generate SVG diagrams, with an optional local draw.io export, using only stdlib."""

import argparse
import base64
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
    "purple": ("#faf5ff", "#ba9cdb", "#8056b3"),
    "orange": ("#fff5e7", "#ddb775", "#855116"),
    "gray": ("#f2f5f8", "#c5cfda", MUTED),
}


def aws_icon(name, prefix, x, y, size):
    """Inline an official SVG with unique IDs; preserve its paths and colors."""
    icon = ET.parse(OUT / "aws-icons" / f"{name}.svg").getroot()
    ids = {
        element.attrib["id"]: f"{prefix}-{index}"
        for index, element in enumerate(icon.iter())
        if "id" in element.attrib
    }
    for element in icon.iter():
        element.tag = element.tag.removeprefix("{http://www.w3.org/2000/svg}")
        for key, value in list(element.attrib.items()):
            if key == "id":
                element.set(key, ids[value])
                continue
            for old, new in ids.items():
                value = value.replace(f"url(#{old})", f"url(#{new})")
                if key.endswith("href") and value == f"#{old}":
                    value = f"#{new}"
            element.set(key, value)
    icon.attrib.update(x=str(x), y=str(y), width=str(size), height=str(size))
    icon.set("aria-hidden", "true")
    return icon


def icon_layout(node):
    size = 32 if node["group"] else 56
    width = len(node["icons"]) * (size + 12) - 12
    x = node["x"] + 12 if node["group"] or node["side"] else node["x"] + (node["w"] - width) / 2
    y = node["y"] + (node["h"] - size) / 2 if node["side"] else node["y"] + 10
    return x, y, size, width


class Page:
    def __init__(self, name, slug, subtitle, width=1600, height=1150, aws_style=False):
        self.name, self.slug = name, slug
        self.width, self.height = width, height
        self.aws_style = aws_style
        self.nodes, self.edges = [], []
        self.box("title", 40, 24, width - 80, 48, name, size=30, text=True)
        self.box("subtitle", 40, 80, width - 80, 38, subtitle, size=16, text=True)

    def box(
        self,
        key,
        x,
        y,
        w,
        h,
        label,
        palette="neutral",
        size=18,
        text=False,
        group=False,
        icons=(),
        side=False,
        boundary=None,
    ):
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
                icons=icons,
                side=side,
                boundary=boundary,
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
            if self.aws_style:
                style += "rounded=0;fontColor=#232f3e;fillColor=none;strokeColor=none;"
                if node["group"]:
                    color = node["boundary"] or "#879196"
                    fill = "#f2faf8" if node["id"] == "subnet" else "#ffffff"
                    dashed = int(node["id"] == "region")
                    style += f"fillColor={fill};strokeColor={color};dashed={dashed};"
                if node["icons"]:
                    _, _, _, icon_width = icon_layout(node)
                    if node["group"] or node["side"]:
                        style += f"align=left;spacingLeft={icon_width + 14};"
                    else:
                        style += "verticalAlign=top;spacingTop=66;"
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
            if node["icons"]:
                x, y, size, _ = icon_layout(node)
                for i, name in enumerate(node["icons"]):
                    image = base64.b64encode(
                        (OUT / "aws-icons" / f"{name}.svg").read_bytes()
                    ).decode("ascii")
                    image_cell = ET.SubElement(
                        root,
                        "mxCell",
                        id=f"{node['id']}-icon-{i}",
                        style=(
                            "shape=image;imageAspect=1;aspect=fixed;"
                            f"image=data:image/svg+xml,{image};"
                        ),
                        vertex="1",
                        parent="1",
                    )
                    ET.SubElement(
                        image_cell,
                        "mxGeometry",
                        {
                            "x": str(x + i * (size + 12)),
                            "y": str(y),
                            "width": str(size),
                            "height": str(size),
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
        ET.SubElement(svg, "desc").text = "Generated from scripts/generate_diagrams.py"
        defs = ET.SubElement(svg, "defs")
        for color in dict.fromkeys([MUTED, TEAL, BLUE, ORANGE, *(e["color"] for e in self.edges)]):
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
            if self.aws_style:
                font = "#232f3e"
                fill = "#ffffff"
                stroke = node["boundary"] or "#879196"
                if node["id"] == "subnet":
                    fill = "#f2faf8"
            if not node["text"] and (not self.aws_style or node["group"]):
                attrs = dict(
                    x=str(node["x"]),
                    y=str(node["y"]),
                    width=str(node["w"]),
                    height=str(node["h"]),
                    rx="0" if self.aws_style else "12",
                    fill=fill,
                    stroke=stroke,
                )
                if self.aws_style:
                    attrs["stroke-width"] = "1.5"
                if node["group"] and (not self.aws_style or node["id"] == "region"):
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
            if node["icons"]:
                icon_x, icon_y, icon_size, icon_width = icon_layout(node)
                for i, name in enumerate(node["icons"]):
                    svg.append(
                        aws_icon(
                            name,
                            f"{node['id']}-icon-{i}",
                            icon_x + i * (icon_size + 12),
                            icon_y,
                            icon_size,
                        )
                    )
                if node["group"] or node["side"]:
                    left = True
                    x = icon_x + icon_width + 14
                    if node["group"]:
                        y = node["y"] + 33
                else:
                    y = node["y"] + icon_size + 34
            for i, line in enumerate(lines):
                attrs = {
                    "x": str(x),
                    "y": str(y + i * line_height),
                    "font-family": f"'{FONT}', 'Microsoft YaHei', sans-serif",
                    "font-size": str(node["size"]),
                    "fill": font,
                    "text-anchor": "start" if left else "middle",
                }
                if i == 0 and (not self.aws_style or not node["text"] or node["id"] == "title"):
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
        "Strands Decider 演示 · 私有 S3 + CloudFront OAC · ECS Fargate · EC2 / Jev / Bedrock 三模型同时对比",
        width=1800,
        height=1620,
        aws_style=True,
    )
    p.box(
        "aws", 360, 140, 1380, 1370, "AWS Cloud", group=True, icons=("cloud",), boundary="#232f3e"
    )
    p.box(
        "region",
        400,
        400,
        1300,
        1070,
        "AWS Region · us-east-1",
        group=True,
        icons=("region",),
        boundary="#00a4a6",
    )
    p.box(
        "vpc",
        440,
        480,
        740,
        620,
        "应用 VPC · 无 Internet 默认路由",
        group=True,
        icons=("vpc",),
        boundary="#8c4fff",
    )
    p.box(
        "subnet",
        465,
        550,
        680,
        500,
        "私有子网组 · 2 个 AZ",
        group=True,
        icons=("subnet",),
        boundary="#00a4a6",
    )
    p.box(
        "browser",
        55,
        215,
        265,
        170,
        "浏览器 / 中文演示界面\n用户名登录 · 五步结果\n客服会话 · 模拟交易 · 对比",
        size=17,
        icons=("client",),
    )
    p.box(
        "cf",
        440,
        220,
        340,
        150,
        "Amazon CloudFront\n全球边缘网络 · HTTPS 入口",
        icons=("cloudfront",),
    )
    p.box(
        "s3",
        1260,
        460,
        350,
        165,
        "Amazon S3 · 静态前端\nBlock Public Access 全部开启\n仅允许 CloudFront OAC 读取",
        size=17,
        icons=("s3",),
    )
    p.box(
        "alb",
        495,
        605,
        265,
        145,
        "Application Load Balancer\n内网 ALB · /api/*",
        size=17,
        icons=("alb",),
    )
    p.box(
        "api",
        490,
        815,
        280,
        200,
        "Amazon ECS / AWS Fargate\nFastAPI · 无公网 IP\n认证 · 构造输入 · 计时\n固定对比 / 反馈闭环 · 执行保护",
        size=17,
        icons=("ecs", "fargate"),
    )
    p.box(
        "sm",
        825,
        605,
        300,
        190,
        "Amazon ECS / Amazon EC2\nDecider v19 · g6.xlarge / L4\nOn-Demand · GPU 持续运行\n私网 HTTP · 权重预置于镜像",
        size=17,
        icons=("ecs", "ec2"),
    )
    p.box(
        "br",
        1260,
        870,
        350,
        180,
        "Amazon Bedrock\nus.openai.gpt-6.1-sol\nConverse · reasoning effort: low\n美国跨区域推理配置",
        size=17,
        icons=("bedrock",),
    )
    p.box(
        "jev_bridge",
        1260,
        660,
        350,
        180,
        "AWS Lambda · Jev 转发\n仅 IAM 调用 · 固定 HTTPS 地址\nSecrets Manager 保存密钥\n托管网络出口，无 Function URL",
        size=16,
        icons=("lambda",),
    )
    p.box(
        "jev",
        45,
        880,
        280,
        155,
        "Typesafe Jev API\nAWS 账户外部托管服务\nSystem One · jev-latest\n返回实际模型版本与概率",
        size=17,
    )
    p.box(
        "timer",
        445,
        1160,
        300,
        145,
        "Amazon EventBridge\n定时规则 · 每分钟触发",
        size=17,
        icons=("eventbridge",),
    )
    p.box(
        "lambda",
        800,
        1150,
        300,
        175,
        "AWS Lambda · GPU 控制器\n手动启动 / 停止 EC2\n禁用闲置停机 · 固定 g6.xlarge",
        size=17,
        icons=("lambda",),
    )
    p.box(
        "ddb",
        1270,
        1150,
        340,
        175,
        "Amazon DynamoDB\n账号 / 会话 / 登录限流\nGPU 状态 / 推理租约",
        size=17,
        icons=("dynamodb",),
    )
    p.box(
        "retain",
        450,
        1360,
        640,
        80,
        "ECR 模型镜像 · 80GB 加密 EBS / 模型缓存\n手动停止保留磁盘；GPU 常驻运行，按小时计费",
        size=16,
        icons=("ecr",),
        side=True,
    )
    p.box(
        "fallback",
        1120,
        1360,
        535,
        80,
        "旧 EC2 已停止 · 80GB EBS 保留\n回退资源，不参与当前推理",
        size=16,
        icons=("ec2", "ebs"),
        side=True,
    )
    p.edge("browser", "cf", [(320, 285), (440, 285)], "HTTPS", at=(380, 262))
    p.edge(
        "cf", "s3", [(780, 275), (1435, 275), (1435, 460)], "静态资源 · OAC 签名", at=(1120, 254)
    )
    p.edge(
        "cf",
        "alb",
        [(610, 370), (610, 380), (810, 380), (810, 580), (770, 580), (770, 675), (760, 675)],
        "VPC Origin · /api/*",
        at=(950, 450),
    )
    p.edge("alb", "api", [(625, 750), (625, 815)])
    p.edge(
        "api",
        "sm",
        [(770, 850), (800, 850), (800, 710), (825, 710)],
        "私网调用 Decider",
        color=TEAL,
        at=(990, 845),
    )
    p.edge(
        "api",
        "br",
        [(770, 910), (1260, 910)],
        "调用 GPT-6.1 Sol",
        color=BLUE,
        at=(1050, 885),
    )
    p.edge(
        "api",
        "jev_bridge",
        [(770, 865), (1200, 865), (1200, 745), (1260, 745)],
        color="#8056b3",
    )
    p.edge(
        "jev_bridge",
        "jev",
        [(1260, 775), (1220, 775), (1220, 455), (380, 455), (380, 960), (325, 960)],
        "HTTPS · Jev API",
        color="#8056b3",
        at=(190, 850),
    )
    p.edge(
        "api",
        "ddb",
        [(770, 975), (930, 975), (930, 1120), (1440, 1120), (1440, 1150)],
        "账号 / 会话 / GPU 状态",
        at=(1060, 1090),
    )
    p.edge("timer", "lambda", [(745, 1240), (800, 1240)], color=ORANGE, dashed=True)
    p.edge(
        "lambda",
        "ddb",
        [(1100, 1250), (1270, 1250)],
        "状态 / 租约",
        color=ORANGE,
        dashed=True,
        at=(1185, 1278),
    )
    p.edge(
        "lambda",
        "sm",
        [(1100, 1190), (1180, 1190), (1180, 815), (975, 815), (975, 795)],
        "启停 EC2 · 保留磁盘",
        color=ORANGE,
        dashed=True,
        at=(1040, 1130),
    )
    p.box(
        "legend",
        45,
        1525,
        1700,
        35,
        "实线：请求 / 访问方向（响应省略）   绿色：Decider   蓝色：Bedrock   紫色：Jev   橙色虚线：GPU 生命周期",
        size=16,
        text=True,
    )
    p.box(
        "note",
        45,
        1565,
        1700,
        35,
        "Bedrock 推理可路由至其他美国区域。图示省略私有网络端点、辅助部署依赖及回退资源网络；订单与账本在浏览器内存中模拟。",
        size=16,
        text=True,
    )
    return p


def comparison():
    p = Page(
        "02  Strands Decider vs Jev vs GPT：同一输入，三条决策路径",
        "model-comparison",
        "固定／优化流程每步并发调用三个模型；闭环各自读取执行反馈，后续输入可能不同。",
        height=1330,
    )
    p.box(
        "input",
        340,
        140,
        920,
        95,
        "应用准备相同输入（候选项由开发者提供）\n业务事实 state + 问题 instructions + 候选项 criteria → 相同 input_hash",
    )
    columns = [
        (
            "d",
            55,
            "Strands Decider · EC2 GPU",
            "teal",
            TEAL,
            "System One choice 请求\n业务事实 + 问题 + 候选条件",
            "私网 HTTP → ECS on EC2\nDecider v19 / L4 GPU\n官方 System One 推理服务",
            "choice + probabilities + confidence\n校验候选 ID、分布与响应字段",
            "每步耗时与成功决策累计时间\nGPU 按运行时间计费",
        ),
        (
            "j",
            565,
            "Jev · Typesafe 托管 API",
            "purple",
            "#8056b3",
            "相同 System One choice 请求\n业务事实 + 问题 + 候选条件",
            "ECS → IAM Lambda → Jev HTTPS\n服务端密钥 / jev-latest\n保留实际返回的模型版本",
            "choice + probabilities + confidence\n保留 token，不混同概率校准尺度",
            "后端耗时含 Lambda 与 HTTPS 往返\n未报告纯推理时间则保留为空",
        ),
        (
            "g",
            1075,
            "GPT-6.1 Sol · Bedrock",
            "blue",
            BLUE,
            "Converse 请求使用相同业务输入\n要求仅返回候选 ID JSON",
            "Bedrock Converse → GPT-6.1 Sol\nreasoning effort = low\n生成文本形式的决策 JSON",
            "解析 JSON，校验 choice 属于候选\n记录 token，不伪造候选概率",
            "每步耗时与成功决策累计时间\n未核实单价，不估算美元成本",
        ),
    ]
    for key, x, title, palette, color, request, infer, result, metric in columns:
        mid = x + 235
        p.box(key, x, 285, 470, 655, title, palette, group=True)
        for suffix, y, height, label in [
            ("request", 350, 85, request),
            ("infer", 490, 110, infer),
            ("result", 655, 100, result),
            ("metric", 815, 85, metric),
        ]:
            p.box(key + suffix, x + 40, y, 390, height, label, palette, size=16)
        p.edge(
            "input", key + "request", [(800, 235), (800, 260), (mid, 260), (mid, 350)], color=color
        )
        for start, end, top, bottom in [
            ("request", "infer", 435, 490),
            ("infer", "result", 600, 655),
            ("result", "metric", 755, 815),
        ]:
            p.edge(key + start, key + end, [(mid, top), (mid, bottom)], color=color)
        p.edge(
            key + "metric",
            "execution",
            [(mid, 900), (mid, 970), (800, 970), (800, 995)],
            color=color,
        )
    p.box(
        "execution",
        320,
        995,
        960,
        125,
        "相同执行保护 · 三个模型各有独立沙盒状态\n参考差异仅提示，继续流程；资金／结案条件不足时挂起或跟进\n原始模型选择、实际动作及保护调整分别保留",
        "orange",
    )
    p.box(
        "outcome",
        320,
        1170,
        960,
        100,
        "三列结果：逐轮输入输出 + 每步耗时 + 实际执行 + 最终订单／工单／模拟账本\n一个模型失败，其他模型仍可完成；失败不计作零耗时成功\n相对 Decider 的耗时倍数只使用对应模型同输入且成功的步骤",
        size=17,
    )
    p.edge("execution", "outcome", [(800, 1120), (800, 1170)], color=ORANGE)
    return p


def workflow():
    p = Page(
        "03  加密支付：固定输入模式的五步流程",
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
        "冻结本轮证据版本\n客户诉求 + 到账金额 + 确认数 + 地址验证 + 人工审批 + 风险标记 + 结算状态\n三模型收到同一版本；每一步并发调用三模型，五步决策按顺序进行",
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
        "获得三套五步建议",
        at=(800, 280),
    )
    p.box(
        "plans",
        200,
        505,
        1200,
        90,
        "分别按序执行三套方案 · Decider、Jev 与 GPT 各自拥有独立模拟订单、工单、账本\n执行到每步时重新检查实际状态；原始模型选择与实际动作分别保存",
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
        "5/5 步已处理 ≠ 业务已完成\n完成需同时确认：目标订单状态 + 对应模拟账本 + 工单结案\n客服模板依据实际结果；挂起不显示为已付款或已退款",
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


def closed_loop():
    p = Page(
        "04  自主闭环：根据实际执行结果继续判断",
        "closed-loop",
        "三侧从同一初始证据开始，分别维护工作流。每轮展示输入、选择、实际动作与反馈；同轮编号不代表相同输入。",
        height=1480,
    )
    p.box(
        "initial",
        390,
        145,
        820,
        95,
        "同一初始场景 / 客户诉求\n相同候选、执行保护、预算与模拟事件规则",
        "gray",
        size=20,
    )
    for key, x, title, palette, color in (
        ("d", 55, "Strands Decider · EC2 GPU", "teal", TEAL),
        ("j", 565, "Jev · Typesafe API", "purple", "#8056b3"),
        ("g", 1075, "GPT-6.1 Sol · Bedrock", "blue", BLUE),
    ):
        p.box(key, x, 305, 470, 880, title, palette, group=True)
        mid = x + 235
        p.box(
            key + "model",
            x + 50,
            380,
            370,
            120,
            "输入当前事实 + 实际执行状态 + 最近反馈\n模型选择下一步候选动作\n保存原始 choice、耗时与请求快照",
            palette,
            size=16,
        )
        p.box(
            key + "apply",
            x + 50,
            565,
            370,
            110,
            "独立沙盒执行器\n核验资金与结案条件，执行或挂起\n保留原始建议 / 实际动作 / 保护调整",
            palette,
            size=16,
        )
        p.box(
            key + "feedback",
            x + 50,
            740,
            370,
            110,
            "读取实际结果\n订单 / 工单 / 模拟账本 / 回复\n写入下一轮 execution_feedback",
            palette,
            size=16,
        )
        p.box(
            key + "route",
            x + 50,
            925,
            370,
            180,
            "成功且未结案 → 下一业务步骤\n外部证据不足 → 等待事件，再核验\n无效动作 → 携带失败反馈重判\n连续两次无进展 → 转人工\n订单 + 账本 + 结案均确认 → 完成",
            palette,
            size=16,
        )
        p.edge(
            "initial", key + "model", [(800, 240), (800, 275), (mid, 275), (mid, 380)], color=color
        )
        p.edge(key + "model", key + "apply", [(mid, 500), (mid, 565)], color=color)
        p.edge(key + "apply", key + "feedback", [(mid, 675), (mid, 740)], color=color)
        p.edge(key + "feedback", key + "route", [(mid, 850), (mid, 925)], color=color)
        p.edge(
            key + "route",
            key + "model",
            [(x + 50, 1000), (x + 20, 1000), (x + 20, 435), (x + 50, 435)],
            color=color,
            dashed=True,
        )
    p.box(
        "budget",
        100,
        1230,
        1400,
        100,
        "最多 20 次决策 / 32 次 tick；浏览器连续运行约 5 分钟后暂停，可继续\n自动模拟确认、补款、地址验证、审批、结算；风险需手动解除\n模拟事件 ≠ 模型执行交易；客服回复来自模板；无真实资金操作",
        "orange",
        size=19,
    )
    p.box(
        "limits",
        100,
        1370,
        1400,
        70,
        "运行与最近 80 轮记录存于浏览器内存，刷新即清除；当前运行内避免重复资金步骤。\n生产环境还需持久化工作流、权限校验、条件写与数据库级幂等。",
        "gray",
        size=17,
    )
    return p


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--drawio", action="store_true", help="Also export an ignored local draw.io file"
    )
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    pages = [architecture(), comparison(), workflow(), closed_loop()]
    for page in pages:
        svg = page.svg()
        ET.indent(svg)
        ET.ElementTree(svg).write(OUT / f"{page.slug}.svg", encoding="utf-8", xml_declaration=True)
    if args.drawio:
        document = ET.Element(
            "mxfile",
            host="app.diagrams.net",
            type="device",
            version="24.7.17",
            pages=str(len(pages)),
        )
        for page in pages:
            document.append(page.xml())
        ET.indent(document)
        ET.ElementTree(document).write(
            OUT / "strands-decider-demo.drawio", encoding="utf-8", xml_declaration=True
        )
    print(f"Generated {len(pages)} SVG diagrams in {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
