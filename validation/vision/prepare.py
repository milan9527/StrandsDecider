"""Create synthetic screenshot fixtures and freeze references before inference."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
FONT = "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc"
BOLD = "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Bold.ttc"
INK, MUTED, TEAL = "#173346", "#617786", "#00877c"


def text(draw, xy, value, size=23, color=INK, bold=False):
    draw.text(xy, value, font=ImageFont.truetype(BOLD if bold else FONT, size), fill=color)


def page(title, subtitle):
    image = Image.new("RGB", (448, 448), "#edf3f7")
    d = ImageDraw.Draw(image)
    d.rounded_rectangle((12, 12, 436, 436), radius=20, fill="white")
    d.rectangle((12, 12, 436, 76), fill=INK)
    text(d, (30, 26), title, 25, "white", True)
    text(d, (30, 91), subtitle, 19, MUTED)
    text(d, (30, 401), "DEMO · SYNTHETIC TEST DATA", 14, MUTED)
    return image, d


def choice(instructions, criteria):
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def main():
    images = ROOT / "images"
    images.mkdir(parents=True, exist_ok=True)
    cases = []

    def record(group, image, reference, description, questions):
        case_id = f"case-{len(cases) + 1:02}"
        path = images / f"{case_id}.png"
        image.save(path)
        cases.append({
            "id": case_id, "group": group, "image": str(path.relative_to(ROOT)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "description": description, "expected": reference,
            "request": {"state": "请根据所附截图中的可见内容回答问题。", "questions": questions},
        })

    status_options = {
        "completed": "页面明确显示付款已成功完成",
        "pending": "页面显示付款仍在处理中或等待确认",
        "failed": "页面明确显示付款失败",
        "unknown": "图片缺失、不可读，或没有足够信息",
    }
    action_options = {
        "confirm": "付款已成功，告知客户该笔付款已完成",
        "wait": "仍在处理中，等待确认，不重复付款",
        "retry": "付款明确失败，提示检查原因后重试",
        "review": "图片信息不足，要求提供清晰完整截图",
    }
    payment_questions = {
        "status": choice("截图显示的付款状态是什么？", status_options),
        "next_action": choice("仅依据截图，客服下一步应如何处理？", action_options),
        "paid": {"type": "noul", "instructions": "截图是否明确显示这笔付款已经成功完成？"},
    }
    for state, language in [
        ("completed", "en"), ("pending", "en"), ("failed", "en"), ("completed", "zh"),
    ]:
        title, detail, button, color = {
            "completed": ("Payment successful", "Confirmed: 12 / 12", "Done", "#00877c"),
            "pending": ("Payment processing", "Confirmed: 3 / 12", "View status", "#a56300"),
            "failed": ("Payment failed", "Transaction rejected", "Try again", "#bf3446"),
        }[state]
        if language == "zh":
            title, detail, button = "支付成功", "链上确认：12 / 12", "完成"
        image, d = page("MERCHANT PAY", "Order #1042  /  USDC")
        text(d, (30, 140), title, 29, color, True)
        text(d, (30, 199), "129.00 USDC", 33, bold=True)
        text(d, (30, 259), detail, 23)
        d.rounded_rectangle((30, 326, 418, 383), radius=10, fill=color)
        text(d, (50, 336), button, 23, "white", True)
        record("payment", image, {
            "status": state, "next_action": {"completed": "confirm", "pending": "wait", "failed": "retry"}[state],
            "paid": state == "completed",
        }, f"{language} payment screenshot: {state}", payment_questions)

    routing_questions = {
        "queue": choice("应将截图中的客户问题分配给哪个客服队列？", {
            "refunds": "客户申请退款、重复扣款退回",
            "payment_issues": "客户付款失败、支付无法完成",
            "account_access": "客户无法登录、账号被锁定",
            "product_information": "客户咨询产品支持范围或使用信息",
            "unknown": "图片缺失、不可读，或无法判断诉求",
        }),
    }
    conversations = [
        ("refunds", ["我被重复扣款了。", "同一订单付了两次，", "请帮我退回多付的一笔。"]),
        ("payment_issues", ["付款一直失败。", "点击支付就出现报错，", "现在无法完成付款。"]),
        ("account_access", ["我的账号被锁定了。", "密码正确也无法登录，", "请帮我恢复账户访问。"]),
        ("product_information", ["你们支持哪些付款币种？", "我想了解能否使用 USDC。"]),
    ]
    for expected, lines in conversations:
        image, d = page("客户服务", "在线会话 · 客户消息")
        d.rounded_rectangle((30, 148, 418, 325), radius=14, fill="#e7f3f1")
        for line, message in enumerate(lines):
            text(d, (44, 171 + line * 43), message, 23)
        text(d, (30, 351), "客服：等待分配", 22, MUTED)
        record("support", image, {"queue": expected}, f"Chinese customer chat: {expected}", routing_questions)

    receipt_questions = {
        "signature": {"type": "noul", "instructions": "截图的 Signature 签名框内是否存在手写签名笔迹？"},
        "reference": {"type": "noul", "instructions": "截图的 Transaction ID 一栏是否已填写交易编号？"},
        "action": choice(
            "凭证必须同时有交易编号和签名才算完整。根据图片，应采取哪个动作？",
            {"accept": "交易编号和签名都有，接收凭证",
             "request_signature": "已有交易编号，只有签名缺失，要求补签",
             "request_reference": "已有签名，只有交易编号缺失，要求补编号",
             "request_both": "交易编号和签名都缺失，要求补全两项",
             "unknown": "图片缺失或不可读，无法判断"},
        ),
    }
    for signature, reference in [(True, True), (False, True), (True, False), (False, False)]:
        image, d = page("PAYMENT RECEIPT", "Amount 129.00 USDC")
        text(d, (30, 137), "Transaction ID", 22, bold=True)
        d.rounded_rectangle((30, 178, 418, 229), radius=5, outline="#9aaebd", width=2)
        if reference:
            text(d, (43, 185), "TX-8472-ABCD", 23)
        text(d, (30, 249), "Signature", 22, bold=True)
        d.rounded_rectangle((30, 286, 418, 385), radius=5, outline="#9aaebd", width=2)
        if signature:
            # Pure visual evidence, not a text label saying "signed".
            d.line([(60, 355), (79, 309), (87, 358), (106, 330), (121, 350),
                    (145, 313), (135, 362), (160, 341), (181, 357), (194, 332),
                    (211, 350), (251, 330), (234, 361), (287, 343)], fill="#273c89", width=4)
            d.line([(67, 370), (319, 360)], fill="#273c89", width=3)
        action = {
            (True, True): "accept", (False, True): "request_signature",
            (True, False): "request_reference", (False, False): "request_both",
        }[(signature, reference)]
        record("receipt", image, {"signature": signature, "reference": reference, "action": action},
               f"Receipt with signature={signature}, transaction ID={reference}", receipt_questions)

    blank = Image.new("RGB", (448, 448), "white")
    blank.save(images / "blank.png")
    manifest = {
        "frozen_at": datetime.now(UTC).isoformat(), "model": "strands-decider-2B-hobson-v19",
        "image_source": "Synthetic UI fixtures rendered with Pillow; no customer data.",
        "case_count": len(cases), "independent_questions": sum(len(c["expected"]) for c in cases),
        "image_dimensions": [448, 448], "cases": cases,
        "plan": {"warmups": 3, "image_repetitions": 3, "reversed_choices_repetitions": 1,
                 "no_image_repetitions": 1, "blank_image_repetitions": 1,
                 "concurrency": 1, "boolean_threshold": 0.5,
                 "main_accuracy": "First image pass, unique cases/questions only",
                 "latency": "Warm image passes only; request includes all questions for one image"},
    }
    target = ROOT / "cases.json"
    if target.exists():
        raise RuntimeError("cases.json already exists; do not overwrite a frozen test after inference")
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    sheet = Image.new("RGB", (448 * 4, 478 * 3), "#d8e3eb")
    for index, case in enumerate(cases):
        x, y = index % 4 * 448, index // 4 * 478
        sheet.paste(Image.open(ROOT / case["image"]), (x, y))
        text(ImageDraw.Draw(sheet), (x + 20, y + 448), case["id"], 19)
    sheet.save(ROOT / "fixtures-overview.png")
    print(json.dumps({"cases": len(cases), "questions": manifest["independent_questions"],
                      "cases_sha256": hashlib.sha256(target.read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
