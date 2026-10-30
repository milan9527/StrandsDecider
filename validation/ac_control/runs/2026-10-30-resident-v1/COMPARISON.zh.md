# 空调控制：Decider、Liquid、H2O 同输入比较

Liquid 和 H2O 使用现有 GPU 常驻服务新增实测；Strands Decider 复用同日较早完成的 40 次基线调用。每模型的主结果均为规范中的 20 条 Query，另外反转候选顺序各测 20 次。

## 完全匹配

| 模型 | 单指令 /10 | 多指令 /10 | 原始顺序 /20 | 反转顺序 /20 | 换序后改变 |
|---|---:|---:|---:|---:|---:|
| Strands Decider v19 | 4/10（40.0%） | 0/10（0.0%） | 4/20（20.0%） | 2/20（10.0%） | 18/20 |
| Liquid d1-2B | 0/10（0.0%） | 0/10（0.0%） | 0/20（0.0%） | 0/20（0.0%） | 18/20 |
| H2O Lightning 4B | 9/10（90.0%） | 9/10（90.0%） | 18/20（90.0%） | 18/20（90.0%） | 0/20 |

## 指令指标（原始候选顺序）

| 模型 | Key 精确率 | Key 召回率 | 已匹配 Key 的 Value 准确率 | 多余指令 | 缺失指令 |
|---|---:|---:|---:|---:|---:|
| Strands Decider v19 | 19/20（95.0%） | 19/40（47.5%） | 19/19（100.0%） | 1/20（5.0%） | 21/40（52.5%） |
| Liquid d1-2B | 40/145（27.6%） | 40/40（100.0%） | 40/40（100.0%） | 105/145（72.4%） | 0/40（0.0%） |
| H2O Lightning 4B | 40/42（95.2%） | 40/40（100.0%） | 40/40（100.0%） | 2/42（4.8%） | 0/40（0.0%） |

完全匹配比较无序 `cmdKey/cmdValue` 集合。Key 精确率=匹配 Key 数/预测指令数，Key 召回率=匹配 Key 数/参考指令数；Value 准确率以已匹配 Key 为分母。多余=预测集合减参考集合/预测指令数；缺失=参考集合减预测集合/参考指令数。错 Value 会同时产生一个多余对和一个缺失对。调用或格式失败留在分母。

## 耗时与调用状态

每条 Query 一次 HTTP 请求、30 个 choice。下列单位均为毫秒。

| 模型 | 顺序 | 服务端平均 | 服务端 P50 | 服务端 P95 | 客户端平均 | 调用/格式失败 |
|---|---|---:|---:|---:|---:|---:|
| Strands Decider v19 | original | 2906.9 | 2904.6 | 2956.4 | 2919.9 | 0 |
| Strands Decider v19 | reversed | 2908.8 | 2904.5 | 2961.6 | 2918.2 | 0 |
| Liquid d1-2B | original | 608.7 | 608.9 | 612.5 | 610.7 | 0 |
| Liquid d1-2B | reversed | 609.4 | 608.7 | 614.0 | 611.4 | 0 |
| H2O Lightning 4B | original | 5962.1 | 5963.1 | 6048.7 | 5963.9 | 0 |
| H2O Lightning 4B | reversed | 5966.9 | 5968.4 | 6059.6 | 5968.7 | 0 |

Decider/Liquid 的服务端计时读取顶层 `latency_ms`，H2O 读取 `usage.latency_ms`；各模型包装服务的计时边界不完全相同，均不能当作纯 GPU 计算时间。Decider 客户端包含 HTTPS 往返，Liquid/H2O 客户端位于 GPU 主机、走 loopback，因此不直接比较客户端延迟。Decider 为同日早先记录，未在本轮重新调用。

## 完整输入与运行方法

- 完整复用 Decider 基线中的 40 份请求，逐项核验包含候选顺序的 SHA-256。没有改写 Query、说明、30 项 Command Set 或候选。
- 原生每 Key 一个 choice，候选为该 Key 的全部合法控制值及 omit。数值范围覆盖所有合法整数；每条实际请求均包含 30 问。5 条温度用例的单位也必须由模型独立选择，程序不补齐。
- 业务网关限制 16 问/32 候选，本轮在 GPU 内直接调用现有 `127.0.0.1:18801`（Liquid）及 `127.0.0.1:18803`（H2O）原生服务。没有拆题、缩减候选、改服务配置或重新加载模型。
- 现有实例 `i-0ae7eb0abcb815af3` / g6.xlarge / NVIDIA L4；三模型同卡常驻。Liquid 为官方 Transformers、BF16；H2O 为官方补丁 vLLM 0.30.0、FP8。分别串行跑完 Liquid 和 H2O，不并发压测。
- 每个新模型各一次预检、40 次正式调用，不自动重试。预检与文件传输失败不计入正式推理准确率或耗时。
- 只评估指令选择，不向真实空调下发。两种候选顺序是同一批 20 例的重复观察；结果只代表本套输入及运行方式，没有覆盖越界、小数、冲突与否定等反例。

## 逐例实际输出（原始候选顺序）

✓ 表示完整集合与参考相同；✗ 表示至少有一条多余、缺失或错误指令。

| 用例 | 参考 | Decider | Liquid | H2O |
|---|---|---|---|---|
| S01 开机 | `t_power=1` | ✗ ∅ | ✗ `t_8heat=1`, `t_outdoor_selfclean=1`, `t_power=1`, `t_swing_angle=0`, `t_swing_follow=0` | ✗ `t_power=1`, `t_work_mode=2` |
| S02 选择制冷模式 | `t_work_mode=2` | ✗ `t_temp_f=90`, `t_work_mode=2` | ✗ `t_8heat=1`, `t_outdoor_selfclean=1`, `t_power=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_work_mode=2` | ✓ `t_work_mode=2` |
| S03 设置摄氏温度 | `t_temp=24`, `t_temp_type=0` | ✗ `t_temp=24` | ✗ `t_8heat=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp=24`, `t_temp_f=80`, `t_temp_type=0` | ✓ `t_temp=24`, `t_temp_type=0` |
| S04 设置华氏温度 | `t_temp_f=68`, `t_temp_type=1` | ✗ `t_temp_f=68` | ✗ `t_8heat=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp_f=68`, `t_temp_type=1` | ✓ `t_temp_f=68`, `t_temp_type=1` |
| S05 选择高风速 | `t_fan_speed=9` | ✓ `t_fan_speed=9` | ✗ `t_8heat=1`, `t_dimmer=1`, `t_fan_speed=9`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0` | ✓ `t_fan_speed=9` |
| S06 开启室内机静音 | `t_fan_mute=1` | ✗ ∅ | ✗ `t_8heat=1`, `t_fan_mute=1`, `t_outdoor_mute=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_swing_follow=0` | ✓ `t_fan_mute=1` |
| S07 开启室外机静音 | `t_outdoor_mute=1` | ✓ `t_outdoor_mute=1` | ✗ `t_8heat=1`, `t_fan_mute=1`, `t_outdoor_mute=1`, `t_swing_angle=0`, `t_swing_follow=0` | ✓ `t_outdoor_mute=1` |
| S08 开启空气净化 | `t_purify=1` | ✓ `t_purify=1` | ✗ `t_8heat=1`, `t_outdoor_selfclean=1`, `t_purify=1`, `t_swing_angle=0`, `t_swing_follow=0` | ✓ `t_purify=1` |
| S09 关闭 LED 显示屏 | `t_dimmer=0` | ✗ ∅ | ✗ `t_8heat=0`, `t_dimmer=0`, `t_dr_mode=0`, `t_fan_mute=0`, `t_outdoor_mute=0`, `t_outdoor_selfclean=1`, `t_power=0`, `t_swing_angle=0`, `t_swing_follow=0`, `t_tms=0` | ✓ `t_dimmer=0` |
| S10 选择两侧水平送风 | `t_swing_direction=2` | ✓ `t_swing_direction=2` | ✗ `t_outdoor_mute=0`, `t_outdoor_selfclean=1`, `t_swing_angle=3`, `t_swing_direction=2`, `t_swing_follow=0` | ✓ `t_swing_direction=2` |
| M01 电源、模式与摄氏温度 | `t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2` | ✗ `t_temp=24`, `t_work_mode=2` | ✗ `t_8heat=0`, `t_dr_offset=24`, `t_dr_onoff=1`, `t_outdoor_selfclean=1`, `t_power=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp=24`, `t_temp_f=80`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2` |
| M02 制热模式、温度与风速 | `t_fan_speed=7`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1` | ✗ `t_fan_speed=7`, `t_temp=26`, `t_work_mode=1` | ✗ `t_8heat=1`, `t_dimmer=1`, `t_dr_offset=26`, `t_fan_speed=7`, `t_outdoor_selfclean=1`, `t_power=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp=26`, `t_temp_f=76`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=7`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1` |
| M03 制冷模式、高风速与节能 | `t_eco=1`, `t_fan_speed=9`, `t_work_mode=2` | ✗ `t_fan_speed=9`, `t_work_mode=2` | ✗ `t_8heat=1`, `t_dimmer=1`, `t_eco=1`, `t_fan_speed=9`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_work_mode=2` | ✓ `t_eco=1`, `t_fan_speed=9`, `t_work_mode=2` |
| M04 室内与室外静音 | `t_fan_mute=1`, `t_outdoor_mute=1` | ✗ `t_outdoor_mute=1` | ✗ `t_fan_mute=1`, `t_indoor_selfclean=1`, `t_onekey_selfclean=1`, `t_outdoor_mute=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_swing_follow=0` | ✓ `t_fan_mute=1`, `t_outdoor_mute=1` |
| M05 空气净化与显示屏 | `t_dimmer=0`, `t_purify=1` | ✗ ∅ | ✗ `t_8heat=0`, `t_dimmer=0`, `t_dr_onoff=0`, `t_fan_mute=0`, `t_outdoor_mute=0`, `t_outdoor_selfclean=1`, `t_purify=1`, `t_swing_angle=0`, `t_swing_follow=0` | ✓ `t_dimmer=0`, `t_purify=1` |
| M06 新风与健康风 | `t_fresh_air=1`, `t_health_fan=1` | ✗ ∅ | ✗ `t_8heat=1`, `t_fresh_air=1`, `t_health_fan=1`, `t_onekey_selfclean=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_swing_follow=0` | ✓ `t_fresh_air=1`, `t_health_fan=1` |
| M07 室内与室外自清洁 | `t_indoor_selfclean=1`, `t_outdoor_selfclean=1` | ✗ ∅ | ✗ `t_8heat=1`, `t_indoor_selfclean=1`, `t_onekey_selfclean=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0` | ✓ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1` |
| M08 垂直与水平风向 | `t_swing_direction=2`, `t_up_down=1` | ✗ `t_swing_direction=2` | ✗ `t_left_right=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_swing_follow=0`, `t_up_down=1` | ✗ `t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1` |
| M09 需求响应设置 | `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1` | ✗ `t_dr_offset=5` | ✗ `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp_type=1` | ✓ `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1` |
| M10 制冷模式、Super Mode 与温度 | `t_super=1`, `t_temp=22`, `t_temp_type=0`, `t_work_mode=2` | ✗ `t_temp=22`, `t_work_mode=2` | ✗ `t_8heat=1`, `t_dr_offset=22`, `t_outdoor_selfclean=1`, `t_super=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp=22`, `t_temp_f=70`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_super=1`, `t_temp=22`, `t_temp_type=0`, `t_work_mode=2` |

## 新模型失败详情（两种候选顺序）

### Liquid d1-2B / S01 / original

> Turn on the air conditioner.

- 预期：`t_power=1`
- 实际：`t_8heat=1`, `t_outdoor_selfclean=1`, `t_power=1`, `t_swing_angle=0`, `t_swing_follow=0`
- 多余：`t_8heat=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0`
- 缺失：无

### Liquid d1-2B / S01 / reversed

> Turn on the air conditioner.

- 预期：`t_power=1`
- 实际：`t_8heat=1`, `t_indoor_selfclean=1`, `t_outdoor_selfclean=1`, `t_power=1`
- 多余：`t_8heat=1`, `t_indoor_selfclean=1`, `t_outdoor_selfclean=1`
- 缺失：无

### Liquid d1-2B / S02 / original

> Set the air conditioner to cooling mode.

- 预期：`t_work_mode=2`
- 实际：`t_8heat=1`, `t_outdoor_selfclean=1`, `t_power=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_work_mode=2`
- 多余：`t_8heat=1`, `t_outdoor_selfclean=1`, `t_power=1`, `t_swing_angle=0`, `t_swing_follow=0`
- 缺失：无

### Liquid d1-2B / S02 / reversed

> Set the air conditioner to cooling mode.

- 预期：`t_work_mode=2`
- 实际：`t_8heat=1`, `t_outdoor_selfclean=1`, `t_power=1`, `t_work_mode=2`
- 多余：`t_8heat=1`, `t_outdoor_selfclean=1`, `t_power=1`
- 缺失：无

### Liquid d1-2B / S03 / original

> Set the air conditioner temperature to 24 degrees Celsius.

- 预期：`t_temp=24`, `t_temp_type=0`
- 实际：`t_8heat=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp=24`, `t_temp_f=80`, `t_temp_type=0`
- 多余：`t_8heat=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp_f=80`
- 缺失：无

### Liquid d1-2B / S03 / reversed

> Set the air conditioner temperature to 24 degrees Celsius.

- 预期：`t_temp=24`, `t_temp_type=0`
- 实际：`t_8heat=1`, `t_outdoor_selfclean=1`, `t_temp=24`, `t_temp_type=0`
- 多余：`t_8heat=1`, `t_outdoor_selfclean=1`
- 缺失：无

### Liquid d1-2B / S04 / original

> Set the air conditioner temperature to 68 degrees Fahrenheit.

- 预期：`t_temp_f=68`, `t_temp_type=1`
- 实际：`t_8heat=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp_f=68`, `t_temp_type=1`
- 多余：`t_8heat=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0`
- 缺失：无

### Liquid d1-2B / S04 / reversed

> Set the air conditioner temperature to 68 degrees Fahrenheit.

- 预期：`t_temp_f=68`, `t_temp_type=1`
- 实际：`t_8heat=1`, `t_outdoor_selfclean=1`, `t_temp_f=68`, `t_temp_type=1`
- 多余：`t_8heat=1`, `t_outdoor_selfclean=1`
- 缺失：无

### Liquid d1-2B / S05 / original

> Set the air conditioner fan speed to high.

- 预期：`t_fan_speed=9`
- 实际：`t_8heat=1`, `t_dimmer=1`, `t_fan_speed=9`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0`
- 多余：`t_8heat=1`, `t_dimmer=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0`
- 缺失：无

### Liquid d1-2B / S05 / reversed

> Set the air conditioner fan speed to high.

- 预期：`t_fan_speed=9`
- 实际：`t_8heat=1`, `t_dimmer=1`, `t_fan_speed=9`, `t_indoor_selfclean=1`, `t_outdoor_selfclean=1`
- 多余：`t_8heat=1`, `t_dimmer=1`, `t_indoor_selfclean=1`, `t_outdoor_selfclean=1`
- 缺失：无

### Liquid d1-2B / S06 / original

> Turn on quiet mode for the indoor unit.

- 预期：`t_fan_mute=1`
- 实际：`t_8heat=1`, `t_fan_mute=1`, `t_outdoor_mute=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_swing_follow=0`
- 多余：`t_8heat=1`, `t_outdoor_mute=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_swing_follow=0`
- 缺失：无

### Liquid d1-2B / S06 / reversed

> Turn on quiet mode for the indoor unit.

- 预期：`t_fan_mute=1`
- 实际：`t_8heat=1`, `t_fan_mute=1`, `t_indoor_selfclean=1`, `t_outdoor_mute=1`, `t_swing_angle=0`, `t_swing_follow=0`
- 多余：`t_8heat=1`, `t_indoor_selfclean=1`, `t_outdoor_mute=1`, `t_swing_angle=0`, `t_swing_follow=0`
- 缺失：无

### Liquid d1-2B / S07 / original

> Turn on outdoor quiet mode.

- 预期：`t_outdoor_mute=1`
- 实际：`t_8heat=1`, `t_fan_mute=1`, `t_outdoor_mute=1`, `t_swing_angle=0`, `t_swing_follow=0`
- 多余：`t_8heat=1`, `t_fan_mute=1`, `t_swing_angle=0`, `t_swing_follow=0`
- 缺失：无

### Liquid d1-2B / S07 / reversed

> Turn on outdoor quiet mode.

- 预期：`t_outdoor_mute=1`
- 实际：`t_8heat=1`, `t_fan_mute=1`, `t_outdoor_mute=1`, `t_swing_angle=0`
- 多余：`t_8heat=1`, `t_fan_mute=1`, `t_swing_angle=0`
- 缺失：无

### Liquid d1-2B / S08 / original

> Turn on air purification.

- 预期：`t_purify=1`
- 实际：`t_8heat=1`, `t_outdoor_selfclean=1`, `t_purify=1`, `t_swing_angle=0`, `t_swing_follow=0`
- 多余：`t_8heat=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0`
- 缺失：无

### Liquid d1-2B / S08 / reversed

> Turn on air purification.

- 预期：`t_purify=1`
- 实际：`t_8heat=1`, `t_indoor_selfclean=1`, `t_outdoor_selfclean=1`, `t_power=1`, `t_purify=1`, `t_swing_angle=0`
- 多余：`t_8heat=1`, `t_indoor_selfclean=1`, `t_outdoor_selfclean=1`, `t_power=1`, `t_swing_angle=0`
- 缺失：无

### Liquid d1-2B / S09 / original

> Turn off the air conditioner display light.

- 预期：`t_dimmer=0`
- 实际：`t_8heat=0`, `t_dimmer=0`, `t_dr_mode=0`, `t_fan_mute=0`, `t_outdoor_mute=0`, `t_outdoor_selfclean=1`, `t_power=0`, `t_swing_angle=0`, `t_swing_follow=0`, `t_tms=0`
- 多余：`t_8heat=0`, `t_dr_mode=0`, `t_fan_mute=0`, `t_outdoor_mute=0`, `t_outdoor_selfclean=1`, `t_power=0`, `t_swing_angle=0`, `t_swing_follow=0`, `t_tms=0`
- 缺失：无

### Liquid d1-2B / S09 / reversed

> Turn off the air conditioner display light.

- 预期：`t_dimmer=0`
- 实际：`t_8heat=0`, `t_dimmer=0`, `t_dr_onoff=0`, `t_power=0`, `t_swing_follow=0`
- 多余：`t_8heat=0`, `t_dr_onoff=0`, `t_power=0`, `t_swing_follow=0`
- 缺失：无

### Liquid d1-2B / S10 / original

> Set the horizontal airflow to both sides.

- 预期：`t_swing_direction=2`
- 实际：`t_outdoor_mute=0`, `t_outdoor_selfclean=1`, `t_swing_angle=3`, `t_swing_direction=2`, `t_swing_follow=0`
- 多余：`t_outdoor_mute=0`, `t_outdoor_selfclean=1`, `t_swing_angle=3`, `t_swing_follow=0`
- 缺失：无

### Liquid d1-2B / S10 / reversed

> Set the horizontal airflow to both sides.

- 预期：`t_swing_direction=2`
- 实际：`t_8heat=1`, `t_outdoor_selfclean=1`, `t_swing_direction=2`
- 多余：`t_8heat=1`, `t_outdoor_selfclean=1`
- 缺失：无

### Liquid d1-2B / M01 / original

> Turn on the air conditioner, switch it to cooling mode, and set the temperature to 24 degrees Celsius.

- 预期：`t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2`
- 实际：`t_8heat=0`, `t_dr_offset=24`, `t_dr_onoff=1`, `t_outdoor_selfclean=1`, `t_power=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp=24`, `t_temp_f=80`, `t_temp_type=0`, `t_work_mode=2`
- 多余：`t_8heat=0`, `t_dr_offset=24`, `t_dr_onoff=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp_f=80`
- 缺失：无

### Liquid d1-2B / M01 / reversed

> Turn on the air conditioner, switch it to cooling mode, and set the temperature to 24 degrees Celsius.

- 预期：`t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2`
- 实际：`t_8heat=0`, `t_dr_onoff=1`, `t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2`
- 多余：`t_8heat=0`, `t_dr_onoff=1`
- 缺失：无

### Liquid d1-2B / M02 / original

> Switch the air conditioner to heating mode, set it to 26 degrees Celsius, and use medium fan speed.

- 预期：`t_fan_speed=7`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1`
- 实际：`t_8heat=1`, `t_dimmer=1`, `t_dr_offset=26`, `t_fan_speed=7`, `t_outdoor_selfclean=1`, `t_power=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp=26`, `t_temp_f=76`, `t_temp_type=0`, `t_work_mode=1`
- 多余：`t_8heat=1`, `t_dimmer=1`, `t_dr_offset=26`, `t_outdoor_selfclean=1`, `t_power=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp_f=76`
- 缺失：无

### Liquid d1-2B / M02 / reversed

> Switch the air conditioner to heating mode, set it to 26 degrees Celsius, and use medium fan speed.

- 预期：`t_fan_speed=7`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1`
- 实际：`t_8heat=1`, `t_dimmer=1`, `t_dr_onoff=1`, `t_fan_speed=7`, `t_outdoor_selfclean=1`, `t_power=1`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1`
- 多余：`t_8heat=1`, `t_dimmer=1`, `t_dr_onoff=1`, `t_outdoor_selfclean=1`, `t_power=1`
- 缺失：无

### Liquid d1-2B / M03 / original

> Set cooling mode, change the fan speed to high, and turn on energy saving.

- 预期：`t_eco=1`, `t_fan_speed=9`, `t_work_mode=2`
- 实际：`t_8heat=1`, `t_dimmer=1`, `t_eco=1`, `t_fan_speed=9`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_work_mode=2`
- 多余：`t_8heat=1`, `t_dimmer=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0`
- 缺失：无

### Liquid d1-2B / M03 / reversed

> Set cooling mode, change the fan speed to high, and turn on energy saving.

- 预期：`t_eco=1`, `t_fan_speed=9`, `t_work_mode=2`
- 实际：`t_8heat=1`, `t_dimmer=1`, `t_eco=1`, `t_fan_speed=9`, `t_indoor_selfclean=1`, `t_outdoor_selfclean=1`, `t_work_mode=2`
- 多余：`t_8heat=1`, `t_dimmer=1`, `t_indoor_selfclean=1`, `t_outdoor_selfclean=1`
- 缺失：无

### Liquid d1-2B / M04 / original

> Turn on both indoor quiet mode and outdoor quiet mode.

- 预期：`t_fan_mute=1`, `t_outdoor_mute=1`
- 实际：`t_fan_mute=1`, `t_indoor_selfclean=1`, `t_onekey_selfclean=1`, `t_outdoor_mute=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_swing_follow=0`
- 多余：`t_indoor_selfclean=1`, `t_onekey_selfclean=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_swing_follow=0`
- 缺失：无

### Liquid d1-2B / M04 / reversed

> Turn on both indoor quiet mode and outdoor quiet mode.

- 预期：`t_fan_mute=1`, `t_outdoor_mute=1`
- 实际：`t_8heat=1`, `t_fan_mute=1`, `t_indoor_selfclean=1`, `t_onekey_selfclean=1`, `t_outdoor_mute=1`
- 多余：`t_8heat=1`, `t_indoor_selfclean=1`, `t_onekey_selfclean=1`
- 缺失：无

### Liquid d1-2B / M05 / original

> Turn on air purification and turn off the display light.

- 预期：`t_dimmer=0`, `t_purify=1`
- 实际：`t_8heat=0`, `t_dimmer=0`, `t_dr_onoff=0`, `t_fan_mute=0`, `t_outdoor_mute=0`, `t_outdoor_selfclean=1`, `t_purify=1`, `t_swing_angle=0`, `t_swing_follow=0`
- 多余：`t_8heat=0`, `t_dr_onoff=0`, `t_fan_mute=0`, `t_outdoor_mute=0`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0`
- 缺失：无

### Liquid d1-2B / M05 / reversed

> Turn on air purification and turn off the display light.

- 预期：`t_dimmer=0`, `t_purify=1`
- 实际：`t_8heat=1`, `t_dimmer=0`, `t_dr_onoff=0`, `t_fan_mute=0`, `t_indoor_selfclean=1`, `t_outdoor_mute=0`, `t_outdoor_selfclean=1`, `t_power=1`, `t_purify=1`, `t_swing_angle=0`, `t_swing_follow=0`
- 多余：`t_8heat=1`, `t_dr_onoff=0`, `t_fan_mute=0`, `t_indoor_selfclean=1`, `t_outdoor_mute=0`, `t_outdoor_selfclean=1`, `t_power=1`, `t_swing_angle=0`, `t_swing_follow=0`
- 缺失：无

### Liquid d1-2B / M06 / original

> Enable fresh air and healthy wind.

- 预期：`t_fresh_air=1`, `t_health_fan=1`
- 实际：`t_8heat=1`, `t_fresh_air=1`, `t_health_fan=1`, `t_onekey_selfclean=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_swing_follow=0`
- 多余：`t_8heat=1`, `t_onekey_selfclean=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_swing_follow=0`
- 缺失：无

### Liquid d1-2B / M06 / reversed

> Enable fresh air and healthy wind.

- 预期：`t_fresh_air=1`, `t_health_fan=1`
- 实际：`t_8heat=1`, `t_fresh_air=1`, `t_health_fan=1`, `t_onekey_selfclean=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_swing_follow=0`
- 多余：`t_8heat=1`, `t_onekey_selfclean=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_swing_follow=0`
- 缺失：无

### Liquid d1-2B / M07 / original

> Start indoor self-clean and outdoor self-clean.

- 预期：`t_indoor_selfclean=1`, `t_outdoor_selfclean=1`
- 实际：`t_8heat=1`, `t_indoor_selfclean=1`, `t_onekey_selfclean=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0`
- 多余：`t_8heat=1`, `t_onekey_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0`
- 缺失：无

### Liquid d1-2B / M07 / reversed

> Start indoor self-clean and outdoor self-clean.

- 预期：`t_indoor_selfclean=1`, `t_outdoor_selfclean=1`
- 实际：`t_8heat=1`, `t_indoor_selfclean=1`, `t_onekey_selfclean=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0`
- 多余：`t_8heat=1`, `t_onekey_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0`
- 缺失：无

### Liquid d1-2B / M08 / original

> Turn on up-and-down swing and set the horizontal airflow to both sides.

- 预期：`t_swing_direction=2`, `t_up_down=1`
- 实际：`t_left_right=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_swing_follow=0`, `t_up_down=1`
- 多余：`t_left_right=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0`
- 缺失：无

### Liquid d1-2B / M08 / reversed

> Turn on up-and-down swing and set the horizontal airflow to both sides.

- 预期：`t_swing_direction=2`, `t_up_down=1`
- 实际：`t_8heat=1`, `t_left_right=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1`
- 多余：`t_8heat=1`, `t_left_right=1`, `t_swing_angle=0`
- 缺失：无

### Liquid d1-2B / M09 / original

> Turn on demand response, set the DR temperature offset to 5 degrees, and set the DR load capacity to 60 percent.

- 预期：`t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1`
- 实际：`t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp_type=1`
- 多余：`t_swing_angle=0`, `t_swing_follow=0`, `t_temp_type=1`
- 缺失：无

### Liquid d1-2B / M09 / reversed

> Turn on demand response, set the DR temperature offset to 5 degrees, and set the DR load capacity to 60 percent.

- 预期：`t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1`
- 实际：`t_8heat=1`, `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1`
- 多余：`t_8heat=1`
- 缺失：无

### Liquid d1-2B / M10 / original

> Switch to cooling mode, turn on Super Mode, and set the temperature to 22 degrees Celsius.

- 预期：`t_super=1`, `t_temp=22`, `t_temp_type=0`, `t_work_mode=2`
- 实际：`t_8heat=1`, `t_dr_offset=22`, `t_outdoor_selfclean=1`, `t_super=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp=22`, `t_temp_f=70`, `t_temp_type=0`, `t_work_mode=2`
- 多余：`t_8heat=1`, `t_dr_offset=22`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp_f=70`
- 缺失：无

### Liquid d1-2B / M10 / reversed

> Switch to cooling mode, turn on Super Mode, and set the temperature to 22 degrees Celsius.

- 预期：`t_super=1`, `t_temp=22`, `t_temp_type=0`, `t_work_mode=2`
- 实际：`t_8heat=1`, `t_dr_offset=22`, `t_outdoor_selfclean=1`, `t_super=1`, `t_temp=22`, `t_temp_type=0`, `t_work_mode=2`
- 多余：`t_8heat=1`, `t_dr_offset=22`, `t_outdoor_selfclean=1`
- 缺失：无

### H2O Lightning 4B / S01 / original

> Turn on the air conditioner.

- 预期：`t_power=1`
- 实际：`t_power=1`, `t_work_mode=2`
- 多余：`t_work_mode=2`
- 缺失：无

### H2O Lightning 4B / S01 / reversed

> Turn on the air conditioner.

- 预期：`t_power=1`
- 实际：`t_power=1`, `t_work_mode=2`
- 多余：`t_work_mode=2`
- 缺失：无

### H2O Lightning 4B / M08 / original

> Turn on up-and-down swing and set the horizontal airflow to both sides.

- 预期：`t_swing_direction=2`, `t_up_down=1`
- 实际：`t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1`
- 多余：`t_swing_angle=0`
- 缺失：无

### H2O Lightning 4B / M08 / reversed

> Turn on up-and-down swing and set the horizontal airflow to both sides.

- 预期：`t_swing_direction=2`, `t_up_down=1`
- 实际：`t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1`
- 多余：`t_swing_angle=0`
- 缺失：无

## 证据与复现

- [共同请求](../2026-10-30-v1/requests.json)、[共同标准答案](../2026-10-30-v1/references.json)、[Decider 基线报告](../2026-10-30-v1/REPORT.zh.md)。
- [比较计划](comparison_plan.json)、[指标](comparison_summary.json)、[逐条评分](comparison_results.json)。
- [Liquid 原始返回](liquid/formal_receipts.jsonl)、[H2O 原始返回](h2o/formal_receipts.jsonl)。
- [运行前环境](formal_before_environment.json)、[运行后环境](formal_after_environment.json)。
- [Liquid 健康](liquid/formal_health_after.json)、[H2O 健康](h2o/formal_health_after.json)。
- [测试代码与复现说明](../../README.zh.md)。
