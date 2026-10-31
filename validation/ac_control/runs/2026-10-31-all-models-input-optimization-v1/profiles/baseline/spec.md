# 空调控制指令选择测试说明

## 1. 测试目标与输入约定

本文档用于评估模型能否根据英文自然语言 Query，从完整的空调 Command Set 中选出正确的控制 Key 和 Value。

每条测试用例的模型输入包含：

1. 自然语言 `query`。
2. 第2节定义的完整 `commandSet`。

第3节中的预期答案是离线评测使用的标准答案，**不得**放入模型推理输入。

模型必须遵循以下约束：

- 只能选择输入 Command Set 中存在的 Key。
- 枚举指令只能使用给定的 Value，范围指令只能使用有效范围内的数值。
- 返回用户明确要求的全部可兼容设置。
- 不得返回用户未要求的设置。
- 不得自行创造或近似替换不支持的 Key 或 Value。
- 设置摄氏温度时，必须同时输出 `t_temp=<temperature>` 和 `t_temp_type="0"`。
- 设置华氏温度时，必须同时输出 `t_temp_f=<temperature>` 和 `t_temp_type="1"`。

建议的模型输出格式：

```json
{
  "cmdList": [
    {
      "cmdName": "Mode",
      "cmdKey": "t_work_mode",
      "cmdValue": "2"
    }
  ]
}
```

> 下方 Command Set 是 GeneralAgent 空调控制能力的完整超集。生产环境中，具体设备会根据静态能力过滤出子集。本次测试中，每条用例都应使用同一份完整能力集，以验证模型能否在所有可能指令中做出正确区分。

## 2. 完整空调 Command Set

### 2.1 Key 与 Value 映射

| 序号 | 指令名称 | `cmdKey` | 类型 | 可用 Value/范围 | 说明与选择要点 |
|---:|---|---|---|---|---|
| 1 | Power | `t_power` | 枚举 | `0` = Off; `1` = On | 空调主电源。不得用它关闭某个独立功能。 |
| 2 | Mode | `t_work_mode` | 枚举 | `0` = Fan; `1` = Heat; `2` = Cool; `3` = Dry; `4` = Auto | 主工作模式。Auto mode 与 Comfort Auto 是不同功能。 |
| 3 | Temperature (Celsius) | `t_temp` | 范围 | `16`–`32` °C | 摄氏设定温度，必须同时输出 `t_temp_type="0"`。 |
| 4 | Temperature (Fahrenheit) | `t_temp_f` | 范围 | `61`–`90` °F | 华氏设定温度，必须同时输出 `t_temp_type="1"`。GeneralAgent 后续会将该虚拟字段归一化为真实下发字段。 |
| 5 | Temperature Unit | `t_temp_type` | 枚举 | `0` = Celsius; `1` = Fahrenheit | 温度设置的伴随字段。 |
| 6 | Fan Speed | `t_fan_speed` | 枚举 | `0` = Auto; `5` = Low; `6` = Medium Low; `7` = Medium; `8` = Medium High; `9` = High | 风速选择。Turbo/Super 不是风速 Value。 |
| 7 | Quiet | `t_fan_mute` | 枚举 | `0` = Off; `1` = On | 室内机静音，与 Outdoor Quiet 不同。 |
| 8 | Super Mode | `t_super` | 枚举 | `0` = Off; `1` = On | Turbo/强力/快速制冷或制热功能，与风速不同。 |
| 9 | Up and Down Swing | `t_up_down` | 枚举 | `0` = Off; `1` = On | 开关连续上下摆风。固定垂直位置使用 `t_swing_angle`。 |
| 10 | Comfort Auto | `t_indoortemp_detection` | 枚举 | `0` = Off; `1` = On | 基于室内温度检测的舒适自动功能，与 `t_work_mode="4"` 不同。 |
| 11 | Left and Right Swing | `t_left_right` | 枚举 | `0` = Off; `1` = On | 基础左右摆风开关。具体水平风向使用 `t_swing_direction`。 |
| 12 | Airflow | `t_swing_angle` | 枚举 | `0` = Up/down swing; `1` = Auto; `2` = Position 1; `3` = Position 2; `4` = Position 3; `5` = Position 4; `6` = Position 5; `7` = Position 6 | 垂直风向位置。应返回选项 Key，不是显示名称中的位置序号。 |
| 13 | Horizontal Airflow | `t_swing_direction` | 枚举 | `0` = Straight; `1` = All Right; `2` = Both sides; `3` = Left and Right Swing; `4` = All Left; `5` = Stop | 水平风向。Splayed/Both sides airflow 对应 Value `2`。 |
| 14 | Energy Saving | `t_eco` | 枚举 | `0` = Off; `1` = On | 节能/Eco 功能，不是工作模式 Value。 |
| 15 | Air Purification | `t_purify` | 枚举 | `0` = Off; `1` = On | 空气净化功能，与 LED 显示屏/Dimmer 不同。 |
| 16 | AI Wind | `t_swing_follow` | 枚举 | `0` = Off; `1` = Blow Towards; `2` = Do Not Blow | 人感风向，与 AI Smart/TMS 不同。 |
| 17 | 8° Heat | `t_8heat` | 枚举 | `0` = Off; `1` = On | 8℃防冻制热功能，与 Heat 工作模式不同。 |
| 18 | Sleep Mode | `t_sleep` | 枚举 | `0` = Off; `1` = Normal Sleep; `2` = Elder Sleep; `3` = Youth Sleep; `4` = Child Sleep | 睡眠档位选择。 |
| 19 | Dimmer | `t_dimmer` | 枚举 | `0` = Off; `1` = On | LED 显示屏/面板灯，与空气净化不同。 |
| 20 | Indoor Self-Clean | `t_indoor_selfclean` | 枚举 | `0` = Off; `1` = On | 仅清洁室内机。 |
| 21 | Outdoor Self-Clean | `t_outdoor_selfclean` | 枚举 | `0` = Off; `1` = On | 仅清洁室外机。 |
| 22 | One-Key Self-Clean | `t_onekey_selfclean` | 枚举 | `0` = Off; `1` = On | 室内外组合一键自清洁。 |
| 23 | Fresh Air | `t_fresh_air` | 枚举 | `0` = Off; `1` = On | 新风/通风功能，与 Healthy Wind 不同。 |
| 24 | AI Smart Control | `t_tms` | 枚举 | `0` = Off; `1` = On | 通用 AI Smart/TMS 功能，与 AI Wind 不同。 |
| 25 | Healthy Wind | `t_health_fan` | 枚举 | `0` = Off; `1` = On | 健康风功能，与 Fresh Air 不同。 |
| 26 | Outdoor Quiet | `t_outdoor_mute` | 枚举 | `0` = Off; `1` = On | 室外机静音，与室内 Quiet 不同。 |
| 27 | DR On/Off | `t_dr_onoff` | 枚举 | `0` = Off; `1` = On | 需求响应（Demand Response）总开关。 |
| 28 | DR Offset Temperature | `t_dr_offset` | 范围 | `0`–`31` ° | 需求响应温度偏移值。 |
| 29 | DR Load Capacity | `t_dr_mode` | 范围 | `0`–`100` % | 需求响应负载/容量值。 |
| 30 | Auto-Defrost Clean | `t_auto_defrost_clean` | 枚举 | `0` = Off; `1` = Enabled but not executing; `2` = Enabled and started; `3` = In progress; `4` = Finished | 用户控制时 GeneralAgent 只下发 `0` 或 `1`。Value `2`–`4` 是运行状态，不得作为用户主动控制值。 |

### 2.2 标准 Command Set 输入

供应商可以将上表转换为 Decider 所需的选择问题格式，但语义输入必须保留完整映射。紧凑的标准表示如下：

```json
{
  "deviceTypeCode": "009",
  "commandSet": [
    {"name":"Power","key":"t_power","type":"enum","options":{"0":"Off","1":"On"}},
    {"name":"Mode","key":"t_work_mode","type":"enum","options":{"0":"Fan","1":"Heat","2":"Cool","3":"Dry","4":"Auto"}},
    {"name":"Temperature (Celsius)","key":"t_temp","type":"range","min":16,"max":32,"unit":"°C"},
    {"name":"Temperature (Fahrenheit)","key":"t_temp_f","type":"range","min":61,"max":90,"unit":"°F"},
    {"name":"Temperature Unit","key":"t_temp_type","type":"enum","options":{"0":"Celsius","1":"Fahrenheit"}},
    {"name":"Fan Speed","key":"t_fan_speed","type":"enum","options":{"0":"Auto","5":"Low","6":"Medium Low","7":"Medium","8":"Medium High","9":"High"}},
    {"name":"Quiet","key":"t_fan_mute","type":"enum","options":{"0":"Off","1":"On"}},
    {"name":"Super Mode","key":"t_super","type":"enum","options":{"0":"Off","1":"On"}},
    {"name":"Up and Down Swing","key":"t_up_down","type":"enum","options":{"0":"Off","1":"On"}},
    {"name":"Comfort Auto","key":"t_indoortemp_detection","type":"enum","options":{"0":"Off","1":"On"}},
    {"name":"Left and Right Swing","key":"t_left_right","type":"enum","options":{"0":"Off","1":"On"}},
    {"name":"Airflow","key":"t_swing_angle","type":"enum","options":{"0":"Up and down swing","1":"Auto","2":"Position 1","3":"Position 2","4":"Position 3","5":"Position 4","6":"Position 5","7":"Position 6"}},
    {"name":"Horizontal Airflow","key":"t_swing_direction","type":"enum","options":{"0":"Straight","1":"All Right","2":"Both sides","3":"Left and Right Swing","4":"All Left","5":"Stop"}},
    {"name":"Energy Saving","key":"t_eco","type":"enum","options":{"0":"Off","1":"On"}},
    {"name":"Air Purification","key":"t_purify","type":"enum","options":{"0":"Off","1":"On"}},
    {"name":"AI Wind","key":"t_swing_follow","type":"enum","options":{"0":"Off","1":"Blow Towards","2":"Do Not Blow"}},
    {"name":"8° Heat","key":"t_8heat","type":"enum","options":{"0":"Off","1":"On"}},
    {"name":"Sleep Mode","key":"t_sleep","type":"enum","options":{"0":"Off","1":"Normal Sleep","2":"Elder Sleep","3":"Youth Sleep","4":"Child Sleep"}},
    {"name":"Dimmer","key":"t_dimmer","type":"enum","options":{"0":"Off","1":"On"}},
    {"name":"Indoor Self-Clean","key":"t_indoor_selfclean","type":"enum","options":{"0":"Off","1":"On"}},
    {"name":"Outdoor Self-Clean","key":"t_outdoor_selfclean","type":"enum","options":{"0":"Off","1":"On"}},
    {"name":"One-Key Self-Clean","key":"t_onekey_selfclean","type":"enum","options":{"0":"Off","1":"On"}},
    {"name":"Fresh Air","key":"t_fresh_air","type":"enum","options":{"0":"Off","1":"On"}},
    {"name":"AI Smart Control","key":"t_tms","type":"enum","options":{"0":"Off","1":"On"}},
    {"name":"Healthy Wind","key":"t_health_fan","type":"enum","options":{"0":"Off","1":"On"}},
    {"name":"Outdoor Quiet","key":"t_outdoor_mute","type":"enum","options":{"0":"Off","1":"On"}},
    {"name":"DR On/Off","key":"t_dr_onoff","type":"enum","options":{"0":"Off","1":"On"}},
    {"name":"DR Offset Temperature","key":"t_dr_offset","type":"range","min":0,"max":31,"unit":"°"},
    {"name":"DR Load Capacity","key":"t_dr_mode","type":"range","min":0,"max":100,"unit":"%"},
    {"name":"Auto-Defrost Clean","key":"t_auto_defrost_clean","type":"enum","options":{"0":"Off","1":"Enabled but not executing","2":"Enabled and started","3":"In progress","4":"Finished"},"userControllableValues":["0","1"]}
  ]
}
```

## 3. 测试用例与标准答案

对于下方每条用例，实际模型输入为：

```text
query + 第2节中的完整 Command Set
```

`Expected cmdList` 仅用于推理完成后的结果评估。指令顺序不应影响正确性，评测时应比较归一化后的 `cmdKey/cmdValue` 集合。

### 3.1 单指令用例（10条）

#### S01 — 开机

**Query**

```text
Turn on the air conditioner.
```

**标准 cmdList**

```json
[{"cmdName":"Power","cmdKey":"t_power","cmdValue":"1"}]
```

#### S02 — 选择制冷模式

**Query**

```text
Set the air conditioner to cooling mode.
```

**标准 cmdList**

```json
[{"cmdName":"Mode","cmdKey":"t_work_mode","cmdValue":"2"}]
```

#### S03 — 设置摄氏温度

**Query**

```text
Set the air conditioner temperature to 24 degrees Celsius.
```

**标准 cmdList**

```json
[
  {"cmdName":"Temperature (Celsius)","cmdKey":"t_temp","cmdValue":"24"},
  {"cmdName":"Temperature Unit","cmdKey":"t_temp_type","cmdValue":"0"}
]
```

#### S04 — 设置华氏温度

**Query**

```text
Set the air conditioner temperature to 68 degrees Fahrenheit.
```

**标准 cmdList**

```json
[
  {"cmdName":"Temperature (Fahrenheit)","cmdKey":"t_temp_f","cmdValue":"68"},
  {"cmdName":"Temperature Unit","cmdKey":"t_temp_type","cmdValue":"1"}
]
```

#### S05 — 选择高风速

**Query**

```text
Set the air conditioner fan speed to high.
```

**标准 cmdList**

```json
[{"cmdName":"Fan Speed","cmdKey":"t_fan_speed","cmdValue":"9"}]
```

#### S06 — 开启室内机静音

**Query**

```text
Turn on quiet mode for the indoor unit.
```

**标准 cmdList**

```json
[{"cmdName":"Quiet","cmdKey":"t_fan_mute","cmdValue":"1"}]
```

#### S07 — 开启室外机静音

**Query**

```text
Turn on outdoor quiet mode.
```

**标准 cmdList**

```json
[{"cmdName":"Outdoor Quiet","cmdKey":"t_outdoor_mute","cmdValue":"1"}]
```

#### S08 — 开启空气净化

**Query**

```text
Turn on air purification.
```

**标准 cmdList**

```json
[{"cmdName":"Air Purification","cmdKey":"t_purify","cmdValue":"1"}]
```

#### S09 — 关闭 LED 显示屏

**Query**

```text
Turn off the air conditioner display light.
```

**标准 cmdList**

```json
[{"cmdName":"Dimmer","cmdKey":"t_dimmer","cmdValue":"0"}]
```

#### S10 — 选择两侧水平送风

**Query**

```text
Set the horizontal airflow to both sides.
```

**标准 cmdList**

```json
[{"cmdName":"Horizontal Airflow","cmdKey":"t_swing_direction","cmdValue":"2"}]
```

### 3.2 可兼容多指令用例（10条）

#### M01 — 电源、模式与摄氏温度

**Query**

```text
Turn on the air conditioner, switch it to cooling mode, and set the temperature to 24 degrees Celsius.
```

**标准 cmdList**

```json
[
  {"cmdName":"Power","cmdKey":"t_power","cmdValue":"1"},
  {"cmdName":"Mode","cmdKey":"t_work_mode","cmdValue":"2"},
  {"cmdName":"Temperature (Celsius)","cmdKey":"t_temp","cmdValue":"24"},
  {"cmdName":"Temperature Unit","cmdKey":"t_temp_type","cmdValue":"0"}
]
```

#### M02 — 制热模式、温度与风速

**Query**

```text
Switch the air conditioner to heating mode, set it to 26 degrees Celsius, and use medium fan speed.
```

**标准 cmdList**

```json
[
  {"cmdName":"Mode","cmdKey":"t_work_mode","cmdValue":"1"},
  {"cmdName":"Temperature (Celsius)","cmdKey":"t_temp","cmdValue":"26"},
  {"cmdName":"Temperature Unit","cmdKey":"t_temp_type","cmdValue":"0"},
  {"cmdName":"Fan Speed","cmdKey":"t_fan_speed","cmdValue":"7"}
]
```

#### M03 — 制冷模式、高风速与节能

**Query**

```text
Set cooling mode, change the fan speed to high, and turn on energy saving.
```

**标准 cmdList**

```json
[
  {"cmdName":"Mode","cmdKey":"t_work_mode","cmdValue":"2"},
  {"cmdName":"Fan Speed","cmdKey":"t_fan_speed","cmdValue":"9"},
  {"cmdName":"Energy Saving","cmdKey":"t_eco","cmdValue":"1"}
]
```

#### M04 — 室内与室外静音

**Query**

```text
Turn on both indoor quiet mode and outdoor quiet mode.
```

**标准 cmdList**

```json
[
  {"cmdName":"Quiet","cmdKey":"t_fan_mute","cmdValue":"1"},
  {"cmdName":"Outdoor Quiet","cmdKey":"t_outdoor_mute","cmdValue":"1"}
]
```

#### M05 — 空气净化与显示屏

**Query**

```text
Turn on air purification and turn off the display light.
```

**标准 cmdList**

```json
[
  {"cmdName":"Air Purification","cmdKey":"t_purify","cmdValue":"1"},
  {"cmdName":"Dimmer","cmdKey":"t_dimmer","cmdValue":"0"}
]
```

#### M06 — 新风与健康风

**Query**

```text
Enable fresh air and healthy wind.
```

**标准 cmdList**

```json
[
  {"cmdName":"Fresh Air","cmdKey":"t_fresh_air","cmdValue":"1"},
  {"cmdName":"Healthy Wind","cmdKey":"t_health_fan","cmdValue":"1"}
]
```

#### M07 — 室内与室外自清洁

**Query**

```text
Start indoor self-clean and outdoor self-clean.
```

**标准 cmdList**

```json
[
  {"cmdName":"Indoor Self-Clean","cmdKey":"t_indoor_selfclean","cmdValue":"1"},
  {"cmdName":"Outdoor Self-Clean","cmdKey":"t_outdoor_selfclean","cmdValue":"1"}
]
```

#### M08 — 垂直与水平风向

**Query**

```text
Turn on up-and-down swing and set the horizontal airflow to both sides.
```

**标准 cmdList**

```json
[
  {"cmdName":"Up and Down Swing","cmdKey":"t_up_down","cmdValue":"1"},
  {"cmdName":"Horizontal Airflow","cmdKey":"t_swing_direction","cmdValue":"2"}
]
```

#### M09 — 需求响应设置

**Query**

```text
Turn on demand response, set the DR temperature offset to 5 degrees, and set the DR load capacity to 60 percent.
```

**标准 cmdList**

```json
[
  {"cmdName":"DR On/Off","cmdKey":"t_dr_onoff","cmdValue":"1"},
  {"cmdName":"DR Offset Temperature","cmdKey":"t_dr_offset","cmdValue":"5"},
  {"cmdName":"DR Load Capacity","cmdKey":"t_dr_mode","cmdValue":"60"}
]
```

#### M10 — 制冷模式、Super Mode 与温度

**Query**

```text
Switch to cooling mode, turn on Super Mode, and set the temperature to 22 degrees Celsius.
```

**标准 cmdList**

```json
[
  {"cmdName":"Mode","cmdKey":"t_work_mode","cmdValue":"2"},
  {"cmdName":"Super Mode","cmdKey":"t_super","cmdValue":"1"},
  {"cmdName":"Temperature (Celsius)","cmdKey":"t_temp","cmdValue":"22"},
  {"cmdName":"Temperature Unit","cmdKey":"t_temp_type","cmdValue":"0"}
]
```

## 4. 评测规则

建议汇总的指标：

- 单指令完全匹配准确率。
- 多指令完全匹配准确率。
- Key 选择准确率。
- Value 选择准确率。
- 多余指令比例。
- 缺失指令比例。
- 推理耗时。
