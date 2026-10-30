# 空调控制：Strands Decider 实测

正式测试时间：2026-10-30T06:18:01.142185+00:00。原始候选顺序完全匹配 **4/20（20.0%）**；反转候选顺序完全匹配 **2/20（10.0%）**。

模型为已部署的 `strands-decider-2B-hobson-v19-vllm`，通过现有 HTTPS `/v1/systemone` 调用。测试仅评估控制指令选择，没有向真实空调下发指令。

本轮只向 Decider 发出测试推理请求。 AWS 核验实例为 `i-0ae7eb0abcb815af3` / `g6.xlarge` / `us-east-1d`。GPU 与共享服务状态见环境快照。

## 方法与边界

- 从 [测试规范快照](spec.md) 自动提取 30 项完整 Command Set 和 20 条英文 Query。每次请求携带同一完整能力集；标准答案仅用于离线评分。
- 每个 Key 对应一个独立 choice，候选为该 Key 的所有合法控制值及 `omit`（不下发）。一次 HTTP 请求包含 30 个问题；服务分别评估每个问题。模型每个非 omit 选择直接映射到 cmdList，程序不补电源、模式或温度单位，也不修正模型错误。
- 保留标准 Command Set 的全部映射，包括自动除霜清洁状态值 2–4；它们按规范不进入可下发候选。范围字段枚举整个合法整数区间，并保留原始 min/max；本批 Query 均为整数，没有验证小数控制。
- 原顺序为 omit 在前、其余值按规范排列；反转顺序仅反转每题候选，Query、完整能力集、问题顺序及说明不变。两组是同一批 20 条用例的重复观察，不能当作 40 条独立样本。
- 正式测试单客户端串行调用，不自动重试。预检请求独立保存在 `probe_*`，不计入准确率与正式耗时。
- `server_ms` 来自服务返回的 `latency_ms`，包含预处理、排队及这 30 个问题的处理；`client_ms` 另含 HTTPS 网络往返。两者均不是纯 GPU 计算时间。
- 合法 Key/Value 由候选空间约束；合法率高不等于语义选择正确。本规范未覆盖否定、越界、冲突指令等反例，不能据此推断生产可靠性。

## 指标

| 指标 | 原始顺序（主结果） | 反转顺序（稳定性） |
|---|---:|---:|
| 全部完全匹配 | 4/20（20.0%） | 2/20（10.0%） |
| 单指令完全匹配 | 4/10（40.0%） | 1/10（10.0%） |
| 多指令完全匹配 | 0/10（0.0%） | 1/10（10.0%） |
| Key 集合完全匹配 | 4/20（20.0%） | 2/20（10.0%） |
| Key 精确率 | 19/20（95.0%） | 21/37（56.8%） |
| Key 召回率 | 19/40（47.5%） | 21/40（52.5%） |
| 已选对 Key 中 Value 准确率 | 19/19（100.0%） | 21/21（100.0%） |
| Key/Value 对精确率 | 19/20（95.0%） | 21/37（56.8%） |
| Key/Value 对召回率 | 19/40（47.5%） | 21/40（52.5%） |
| 多余指令比例 | 1/20（5.0%） | 16/37（43.2%） |
| 缺失指令比例 | 21/40（52.5%） | 19/40（47.5%） |
| 调用/格式失败 | 0 | 0 |

完全匹配按无序 `cmdKey/cmdValue` 集合比较。Key 精确率=正确 Key 数/预测指令数；Key 召回率=正确 Key 数/参考指令数。Value 准确率仅以已匹配 Key 为分母，应与 Key 召回率一起看。多余=预测集合减参考集合，占预测指令数；缺失=参考集合减预测集合，占参考指令数。Value 错误同时形成一个多余对和一个缺失对。调用/格式失败计为该用例不匹配，并按参考指令全部缺失计分。

候选换序后输出改变：**18/20**（仅比较两次均有效的成对请求）。

## 耗时（每条 Query 的全部 30 个问题，毫秒）

| 测量 | 组别 | 平均 | P50 | P95 | 最小–最大 |
|---|---|---:|---:|---:|---:|
| 服务端 | 原始 | 2906.9 | 2904.6 | 2956.4 | 2859.4–2968.5 |
| 客户端 | 原始 | 2919.9 | 2913.3 | 2966.9 | 2873.2–2984.3 |
| 服务端 | 反转 | 2908.8 | 2904.5 | 2961.6 | 2864.4–2968.5 |
| 客户端 | 反转 | 2918.2 | 2912.0 | 2976.2 | 2872.4–2980.2 |

## 逐例结果

| 用例 | 参考 cmdList | 原始顺序实际 cmdList | 原始 | 反转 |
|---|---|---|---|---|
| S01 开机 | `t_power=1` | ∅ | 失败 | 失败 |
| S02 选择制冷模式 | `t_work_mode=2` | `t_temp_f=90`, `t_work_mode=2` | 失败 | 失败 |
| S03 设置摄氏温度 | `t_temp=24`, `t_temp_type=0` | `t_temp=24` | 失败 | 失败 |
| S04 设置华氏温度 | `t_temp_f=68`, `t_temp_type=1` | `t_temp_f=68` | 失败 | 失败 |
| S05 选择高风速 | `t_fan_speed=9` | `t_fan_speed=9` | 通过 | 失败 |
| S06 开启室内机静音 | `t_fan_mute=1` | ∅ | 失败 | 失败 |
| S07 开启室外机静音 | `t_outdoor_mute=1` | `t_outdoor_mute=1` | 通过 | 失败 |
| S08 开启空气净化 | `t_purify=1` | `t_purify=1` | 通过 | 失败 |
| S09 关闭 LED 显示屏 | `t_dimmer=0` | ∅ | 失败 | 失败 |
| S10 选择两侧水平送风 | `t_swing_direction=2` | `t_swing_direction=2` | 通过 | 通过 |
| M01 电源、模式与摄氏温度 | `t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2` | `t_temp=24`, `t_work_mode=2` | 失败 | 失败 |
| M02 制热模式、温度与风速 | `t_fan_speed=7`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1` | `t_fan_speed=7`, `t_temp=26`, `t_work_mode=1` | 失败 | 失败 |
| M03 制冷模式、高风速与节能 | `t_eco=1`, `t_fan_speed=9`, `t_work_mode=2` | `t_fan_speed=9`, `t_work_mode=2` | 失败 | 失败 |
| M04 室内与室外静音 | `t_fan_mute=1`, `t_outdoor_mute=1` | `t_outdoor_mute=1` | 失败 | 失败 |
| M05 空气净化与显示屏 | `t_dimmer=0`, `t_purify=1` | ∅ | 失败 | 失败 |
| M06 新风与健康风 | `t_fresh_air=1`, `t_health_fan=1` | ∅ | 失败 | 失败 |
| M07 室内与室外自清洁 | `t_indoor_selfclean=1`, `t_outdoor_selfclean=1` | ∅ | 失败 | 失败 |
| M08 垂直与水平风向 | `t_swing_direction=2`, `t_up_down=1` | `t_swing_direction=2` | 失败 | 通过 |
| M09 需求响应设置 | `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1` | `t_dr_offset=5` | 失败 | 失败 |
| M10 制冷模式、Super Mode 与温度 | `t_super=1`, `t_temp=22`, `t_temp_type=0`, `t_work_mode=2` | `t_temp=22`, `t_work_mode=2` | 失败 | 失败 |

## 失败详情

### S01 / original

> Turn on the air conditioner.

- 预期：`t_power=1`
- 实际：∅
- 多余：无
- 缺失：`t_power=1`

### S01 / reversed

> Turn on the air conditioner.

- 预期：`t_power=1`
- 实际：`t_swing_direction=2`
- 多余：`t_swing_direction=2`
- 缺失：`t_power=1`

### S02 / original

> Set the air conditioner to cooling mode.

- 预期：`t_work_mode=2`
- 实际：`t_temp_f=90`, `t_work_mode=2`
- 多余：`t_temp_f=90`
- 缺失：无

### S02 / reversed

> Set the air conditioner to cooling mode.

- 预期：`t_work_mode=2`
- 实际：`t_swing_direction=2`, `t_work_mode=2`
- 多余：`t_swing_direction=2`
- 缺失：无

### S03 / original

> Set the air conditioner temperature to 24 degrees Celsius.

- 预期：`t_temp=24`, `t_temp_type=0`
- 实际：`t_temp=24`
- 多余：无
- 缺失：`t_temp_type=0`

### S03 / reversed

> Set the air conditioner temperature to 24 degrees Celsius.

- 预期：`t_temp=24`, `t_temp_type=0`
- 实际：`t_swing_direction=2`, `t_temp=24`
- 多余：`t_swing_direction=2`
- 缺失：`t_temp_type=0`

### S04 / original

> Set the air conditioner temperature to 68 degrees Fahrenheit.

- 预期：`t_temp_f=68`, `t_temp_type=1`
- 实际：`t_temp_f=68`
- 多余：无
- 缺失：`t_temp_type=1`

### S04 / reversed

> Set the air conditioner temperature to 68 degrees Fahrenheit.

- 预期：`t_temp_f=68`, `t_temp_type=1`
- 实际：`t_swing_direction=2`, `t_temp_f=68`
- 多余：`t_swing_direction=2`
- 缺失：`t_temp_type=1`

### S05 / reversed

> Set the air conditioner fan speed to high.

- 预期：`t_fan_speed=9`
- 实际：`t_swing_direction=2`
- 多余：`t_swing_direction=2`
- 缺失：`t_fan_speed=9`

### S06 / original

> Turn on quiet mode for the indoor unit.

- 预期：`t_fan_mute=1`
- 实际：∅
- 多余：无
- 缺失：`t_fan_mute=1`

### S06 / reversed

> Turn on quiet mode for the indoor unit.

- 预期：`t_fan_mute=1`
- 实际：`t_swing_direction=2`
- 多余：`t_swing_direction=2`
- 缺失：`t_fan_mute=1`

### S07 / reversed

> Turn on outdoor quiet mode.

- 预期：`t_outdoor_mute=1`
- 实际：∅
- 多余：无
- 缺失：`t_outdoor_mute=1`

### S08 / reversed

> Turn on air purification.

- 预期：`t_purify=1`
- 实际：`t_purify=1`, `t_swing_direction=2`
- 多余：`t_swing_direction=2`
- 缺失：无

### S09 / original

> Turn off the air conditioner display light.

- 预期：`t_dimmer=0`
- 实际：∅
- 多余：无
- 缺失：`t_dimmer=0`

### S09 / reversed

> Turn off the air conditioner display light.

- 预期：`t_dimmer=0`
- 实际：∅
- 多余：无
- 缺失：`t_dimmer=0`

### M01 / original

> Turn on the air conditioner, switch it to cooling mode, and set the temperature to 24 degrees Celsius.

- 预期：`t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2`
- 实际：`t_temp=24`, `t_work_mode=2`
- 多余：无
- 缺失：`t_power=1`, `t_temp_type=0`

### M01 / reversed

> Turn on the air conditioner, switch it to cooling mode, and set the temperature to 24 degrees Celsius.

- 预期：`t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2`
- 实际：`t_swing_direction=2`, `t_temp=24`, `t_work_mode=2`
- 多余：`t_swing_direction=2`
- 缺失：`t_power=1`, `t_temp_type=0`

### M02 / original

> Switch the air conditioner to heating mode, set it to 26 degrees Celsius, and use medium fan speed.

- 预期：`t_fan_speed=7`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1`
- 实际：`t_fan_speed=7`, `t_temp=26`, `t_work_mode=1`
- 多余：无
- 缺失：`t_temp_type=0`

### M02 / reversed

> Switch the air conditioner to heating mode, set it to 26 degrees Celsius, and use medium fan speed.

- 预期：`t_fan_speed=7`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1`
- 实际：`t_fan_speed=7`, `t_swing_direction=2`, `t_temp=26`, `t_work_mode=1`
- 多余：`t_swing_direction=2`
- 缺失：`t_temp_type=0`

### M03 / original

> Set cooling mode, change the fan speed to high, and turn on energy saving.

- 预期：`t_eco=1`, `t_fan_speed=9`, `t_work_mode=2`
- 实际：`t_fan_speed=9`, `t_work_mode=2`
- 多余：无
- 缺失：`t_eco=1`

### M03 / reversed

> Set cooling mode, change the fan speed to high, and turn on energy saving.

- 预期：`t_eco=1`, `t_fan_speed=9`, `t_work_mode=2`
- 实际：`t_eco=1`, `t_swing_direction=2`
- 多余：`t_swing_direction=2`
- 缺失：`t_fan_speed=9`, `t_work_mode=2`

### M04 / original

> Turn on both indoor quiet mode and outdoor quiet mode.

- 预期：`t_fan_mute=1`, `t_outdoor_mute=1`
- 实际：`t_outdoor_mute=1`
- 多余：无
- 缺失：`t_fan_mute=1`

### M04 / reversed

> Turn on both indoor quiet mode and outdoor quiet mode.

- 预期：`t_fan_mute=1`, `t_outdoor_mute=1`
- 实际：`t_outdoor_mute=1`, `t_swing_direction=2`
- 多余：`t_swing_direction=2`
- 缺失：`t_fan_mute=1`

### M05 / original

> Turn on air purification and turn off the display light.

- 预期：`t_dimmer=0`, `t_purify=1`
- 实际：∅
- 多余：无
- 缺失：`t_dimmer=0`, `t_purify=1`

### M05 / reversed

> Turn on air purification and turn off the display light.

- 预期：`t_dimmer=0`, `t_purify=1`
- 实际：`t_purify=1`, `t_swing_direction=2`
- 多余：`t_swing_direction=2`
- 缺失：`t_dimmer=0`

### M06 / original

> Enable fresh air and healthy wind.

- 预期：`t_fresh_air=1`, `t_health_fan=1`
- 实际：∅
- 多余：无
- 缺失：`t_fresh_air=1`, `t_health_fan=1`

### M06 / reversed

> Enable fresh air and healthy wind.

- 预期：`t_fresh_air=1`, `t_health_fan=1`
- 实际：`t_fresh_air=1`, `t_swing_direction=2`
- 多余：`t_swing_direction=2`
- 缺失：`t_health_fan=1`

### M07 / original

> Start indoor self-clean and outdoor self-clean.

- 预期：`t_indoor_selfclean=1`, `t_outdoor_selfclean=1`
- 实际：∅
- 多余：无
- 缺失：`t_indoor_selfclean=1`, `t_outdoor_selfclean=1`

### M07 / reversed

> Start indoor self-clean and outdoor self-clean.

- 预期：`t_indoor_selfclean=1`, `t_outdoor_selfclean=1`
- 实际：`t_swing_direction=3`
- 多余：`t_swing_direction=3`
- 缺失：`t_indoor_selfclean=1`, `t_outdoor_selfclean=1`

### M08 / original

> Turn on up-and-down swing and set the horizontal airflow to both sides.

- 预期：`t_swing_direction=2`, `t_up_down=1`
- 实际：`t_swing_direction=2`
- 多余：无
- 缺失：`t_up_down=1`

### M09 / original

> Turn on demand response, set the DR temperature offset to 5 degrees, and set the DR load capacity to 60 percent.

- 预期：`t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1`
- 实际：`t_dr_offset=5`
- 多余：无
- 缺失：`t_dr_mode=60`, `t_dr_onoff=1`

### M09 / reversed

> Turn on demand response, set the DR temperature offset to 5 degrees, and set the DR load capacity to 60 percent.

- 预期：`t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1`
- 实际：`t_dr_mode=60`, `t_dr_offset=5`, `t_up_down=1`
- 多余：`t_up_down=1`
- 缺失：`t_dr_onoff=1`

### M10 / original

> Switch to cooling mode, turn on Super Mode, and set the temperature to 22 degrees Celsius.

- 预期：`t_super=1`, `t_temp=22`, `t_temp_type=0`, `t_work_mode=2`
- 实际：`t_temp=22`, `t_work_mode=2`
- 多余：无
- 缺失：`t_super=1`, `t_temp_type=0`

### M10 / reversed

> Switch to cooling mode, turn on Super Mode, and set the temperature to 22 degrees Celsius.

- 预期：`t_super=1`, `t_temp=22`, `t_temp_type=0`, `t_work_mode=2`
- 实际：`t_super=1`, `t_swing_direction=2`, `t_temp=22`, `t_work_mode=2`
- 多余：`t_swing_direction=2`
- 缺失：`t_temp_type=0`

## 可复核证据

- [冻结计划](plan.json)、[完整模型请求](requests.json)、[离线标准答案](references.json)。
- [原始响应逐条记录](formal_receipts.jsonl)、[归一化逐例评分](results.json)、[指标](summary.json)。
- [模型身份](formal_models.json)、[测试前健康](formal_health_before.json)、[测试后健康](formal_health_after.json)。
- 完整复现步骤见 [测试目录说明](../../README.zh.md)。

[EC2 实例核验](environment.json) · [GPU 与 systemd 实时快照](environment_live.json)
