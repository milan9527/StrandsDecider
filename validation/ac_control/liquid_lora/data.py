"""Generate labeled AC requests from intents; no model-generated reference labels."""
import hashlib
import json
import random
import sys
from pathlib import Path

from infra import HERE, ROOT, save, stamp

sys.path.insert(0, str(HERE.parent))
from prepare import read_spec, payload
from optimized_all_models_protocol import portable_request

# Names describe only the selected feature, not implied changes to other features.
NAMES = {
    "t_power": ("main appliance power", "空调整机电源"),
    "t_fan_mute": ("indoor quiet operation", "室内机静音"),
    "t_super": ("Super mode", "强力模式"),
    "t_up_down": ("continuous vertical oscillation", "上下连续摆风"),
    "t_indoortemp_detection": ("Comfort Auto", "舒适自动功能"),
    "t_left_right": ("the basic left-right swing switch", "左右摆风开关"),
    "t_eco": ("energy saving", "节能功能"),
    "t_purify": ("air purification", "空气净化"),
    "t_8heat": ("8-degree frost protection", "8度防冻"),
    "t_dimmer": ("the display light", "显示屏灯光"),
    "t_indoor_selfclean": ("indoor-unit self-cleaning", "室内机自清洁"),
    "t_outdoor_selfclean": ("outdoor-unit self-cleaning", "室外机自清洁"),
    "t_onekey_selfclean": ("combined one-key self-cleaning", "一键内外机自清洁"),
    "t_fresh_air": ("fresh-air ventilation", "新风功能"),
    "t_tms": ("AI Smart control", "AI智能控制"),
    "t_health_fan": ("healthy wind", "健康风"),
    "t_outdoor_mute": ("outdoor-unit quiet operation", "室外机静音"),
    "t_dr_onoff": ("demand response", "需求响应"),
    "t_auto_defrost_clean": ("automatic defrost cleaning", "自动除霜清洁"),
}
ENUMS = {
    "t_work_mode": [("fan-only mode", "送风模式"), ("heating mode", "制热模式"),
                    ("cooling mode", "制冷模式"), ("drying mode", "除湿模式"),
                    ("automatic operating mode", "自动运行模式")],
    "t_fan_speed": [("automatic fan speed", "自动风速"), ("low fan speed", "低风速"),
                    ("medium-low fan speed", "中低风速"), ("medium fan speed", "中风速"),
                    ("medium-high fan speed", "中高风速"), ("high fan speed", "高风速")],
    "t_sleep": [("sleep off", "睡眠模式关闭"), ("normal sleep", "普通睡眠"),
                ("elder sleep", "老人睡眠"), ("youth sleep", "青年睡眠"),
                ("child sleep", "儿童睡眠")],
    "t_swing_angle": [("the vertical airflow option Up and down swing", "垂直风向的上下摆风选项"),
                      ("automatic vertical airflow position", "自动垂直风向"),
                      *[(f"vertical airflow position {i}", f"垂直风向位置{i}") for i in range(1, 7)]],
    "t_swing_direction": [("straight horizontal airflow", "水平直吹"),
                          ("horizontal airflow all right", "水平风向全右"),
                          ("horizontal airflow to both sides", "水平风向两侧"),
                          ("the horizontal airflow option Left and Right Swing", "水平风向的左右摆风选项"),
                          ("horizontal airflow all left", "水平风向全左"),
                          ("horizontal airflow stop", "水平风向停止")],
    "t_swing_follow": [("AI Wind off", "AI风关闭"), ("AI Wind towards people", "AI风向人吹"),
                       ("AI Wind away from people", "AI风避人吹")],
    "t_temp_type": [("Celsius display units", "摄氏显示单位"),
                    ("Fahrenheit display units", "华氏显示单位")],
}


def intents(capabilities):
    result = []
    for command in capabilities["commandSet"]:
        key = command["key"]
        values = list(command.get("userControllableValues", command.get("options", {})))
        if command["type"] == "range":
            values = [str(v) for v in range(command["min"], command["max"] + 1)]
        for i, value in enumerate(values):
            labels = {key: value}
            if key in NAMES:
                en, zh = NAMES[key]
                phrase = (f"{en} {'on' if value == '1' else 'off'}",
                          f"{'开启' if value == '1' else '关闭'}{zh}")
            elif key in ENUMS:
                phrase = ENUMS[key][i]
            elif key in ("t_temp", "t_temp_f"):
                en, zh, unit = ("Celsius", "摄氏", "0") if key == "t_temp" else ("Fahrenheit", "华氏", "1")
                phrase = (f"a target temperature of {value} degrees {en}", f"目标温度{value}{zh}度")
                labels["t_temp_type"] = unit
            elif key == "t_dr_offset":
                phrase = (f"a demand-response temperature offset of {value} degrees", f"需求响应温度偏移{value}度")
            elif key == "t_dr_mode":
                phrase = (f"a demand-response load capacity of {value} percent", f"需求响应负载容量{value}%")
            else:
                raise ValueError(key)
            result.append({"key": key, "value": value, "labels": labels, "phrase": phrase})
    return result


def render(chosen, unchanged, split, language, variant):
    parts = [a["phrase"][language] for a in chosen]
    if language == 0:
        joined = " and ".join(parts)
        patterns = {
            "train": ["Set {x}.", "Please configure {x}.", "I want {x}.", "Apply these settings: {x}."],
            "dev": ["My requested adjustment is {x}.", "For this request, make it {x}."],
            "test": ["The settings I need now are {x}.", "Could you arrange for {x}?"],
        }
        text = patterns[split][variant % len(patterns[split])].format(x=joined) if parts else {
            "train": "Do not change any air-conditioner settings.",
            "dev": "All air-conditioner settings should stay as they are.",
            "test": "Keep the entire air conditioner configuration exactly as it currently is.",
        }[split]
        if unchanged:
            text += f" Leave {unchanged[0]} unchanged."
    else:
        joined = "，同时".join(parts)
        patterns = {
            "train": ["请设置：{x}。", "我要{x}。", "调整为{x}。", "本次执行：{x}。"],
            "dev": ["本次需要的调整是{x}。", "请完成这些设置：{x}。"],
            "test": ["帮我把以下要求落实：{x}。", "现在需要{x}，请执行。"],
        }
        text = patterns[split][variant % len(patterns[split])].format(x=joined) if parts else {
            "train": "不要改变空调的任何设置。",
            "dev": "所有空调设置维持原样。",
            "test": "空调的全部配置请一律保持当前状态。",
        }[split]
        if unchanged:
            text += f"{unchanged[1]}保持不变。"
    return text


def make_data():
    assert not (ROOT / "plan.json").exists()
    caps, spec = read_spec()
    base = portable_request(payload("placeholder", caps), "baseline")
    keys = list(base["questions"])
    pool = intents(caps)
    rng = random.Random(11012026)
    # Combination family and language share the same split, before rendering.
    records = {"train": [], "dev": [], "test": []}
    used = set()
    wanted = {"train": 1024, "dev": 96, "test": 192}
    attempts = 0
    while any(len(records[k]) < n for k, n in wanted.items()):
        attempts += 1
        assert attempts < 100000
        count = rng.choices([0, 1, 2, 3, 4], [2, 33, 35, 20, 10])[0]
        chosen, labels = [], {}
        for action in rng.sample(pool, min(len(pool), 20)):
            if len(chosen) == count:
                break
            if set(action["labels"]) & set(labels):
                continue
            chosen.append(action)
            labels.update(action["labels"])
        if len(chosen) != count:
            continue
        # Explicitly unchanged feature is part of the semantic family.
        possible = [k for k in NAMES if k not in labels]
        unchanged_key = rng.choice(possible) if possible and rng.random() < 0.45 else None
        family = json.dumps([sorted(labels.items()), unchanged_key], separators=(",", ":"))
        if family in used:
            continue
        h = int(hashlib.sha256(family.encode()).hexdigest()[:8], 16) % 100
        split = "train" if h < 75 else "dev" if h < 85 else "test"
        if len(records[split]) >= wanted[split]:
            continue
        used.add(family)
        language = len(records[split]) % 2
        query = render(chosen, NAMES.get(unchanged_key), split, language, attempts)
        records[split].append({
            "id": f"{split}-{len(records[split]):04d}", "query": query,
            "labels": {k: labels.get(k, "omit") for k in keys},
            "language": ["en", "zh"][language], "family": family,
            "unchanged_key": unchanged_key, "split": split,
        })
    # Preserve frozen historical payloads exactly, with evaluation labels separate.
    old = HERE.parent / "runs/2026-10-31-all-models-input-optimization-v1/profiles/baseline"
    ROOT.mkdir(parents=True, exist_ok=True)
    save(ROOT / "template.json", base)
    for split, rows in records.items():
        save(ROOT / f"{split}.json", rows)
    (ROOT / "historical-cases.json").write_bytes((old / "cases.json").read_bytes())
    (ROOT / "historical-references.json").write_bytes((old / "references.json").read_bytes())
    save(ROOT / "test-inputs.json", [{k: row[k] for k in ("id", "query", "language")}
                                     for row in records["test"]])
    save(ROOT / "plan.json", {
        "created_at": stamp(), "model": "LiquidAI/d1-2B",
        "revision": "cfe5760ff5d5998f91d9ac56bd4b2dbd96996d41",
        "counts": wanted, "seed": 11012026,
        "data": "Deterministic synthetic intents with programmatic ground truth; no teacher model.",
        "separation": "Disjoint exact semantic families and request templates; shared vocabulary and generator. "
                      "Not an external blind test. Historical AC cases excluded from training.",
        "training": {"rank": 16, "alpha": 32, "dropout": 0.05, "lr": 5e-5,
                     "epochs": 1, "accumulation": 16, "checkpoints_after_examples": [256, 512, 1024],
                     "targets": "text attention q_proj,v_proj only; original head and embeddings frozen",
                     "loss": "0.5 mean CE on active fields + 0.5 mean CE on omit fields, per whole task",
                     "selection": "Highest dev exact-task accuracy, then fewest extra+missing commands, then earlier checkpoint"},
        "validation": "Dev labels used for checkpoint selection. Held-out and historical reference labels stay local.",
        "evaluation": "Untuned vs selected LoRA, 192 new queries and 78 historical queries, original/reversed options. "
                      "Original 20 spec queries x3, full30 and serial30 HTTP calls; single-step from actual serial calls. "
                      "Fresh reload and merged-weight check before timing.",
        "adoption": "Held-out exact accuracy must improve, active-field accuracy and historical spec exact accuracy "
                    "must not decline; zero interface errors; mean and p95 full-task latency within 10% of baseline.",
        "ec2": "Existing us-east-1d L4; keep running; no production deployment.",
        "readme_changes": False, "github_push": False,
    })
    # Audit label legality, temperature companions, duplicates and split identities.
    all_queries = set()
    historical_queries = {r["query"].casefold().strip() for r in json.loads((old / "references.json").read_text())}
    for split, rows in records.items():
        for row in rows:
            assert set(row["labels"]) == set(keys)
            assert row["query"].casefold().strip() not in historical_queries
            assert row["query"] not in all_queries, row["query"]
            all_queries.add(row["query"])
            for k, v in row["labels"].items():
                assert v in base["questions"][k]["criteria"]
            if row["labels"]["t_temp"] != "omit":
                assert row["labels"]["t_temp_type"] == "0"
            if row["labels"]["t_temp_f"] != "omit":
                assert row["labels"]["t_temp_type"] == "1"
    save(ROOT / "data-audit.json", {
        "passed": True, "queries": len(all_queries), "families": len(used),
        "counts": wanted,
        "sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in ROOT.glob("*.json")},
    })
    print(ROOT)


if __name__ == "__main__":
    make_data()
