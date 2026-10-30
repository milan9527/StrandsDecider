# Liquid 准确率优化：本轮结果

**结论：保留原两阶段建议，不把新候选作为替代方案。** 原规范 11/20→16/20，既有诊断 5/10→6/10；但提前冻结的 24 条新问题均为 12/24，候选未满足“原始顺序必须提高、换序不能下降”的采用规则。留出验证平均完整决策 0.734→1.117 秒，约慢 52.2%。

2026-10-30，LiquidAI/d1-2B、BF16、既有 g6.xlarge/L4；四个常驻服务前后状态不变。测试只调用模型，不控制实际设备。代码与解释见 [优化说明](../../../../docs/LIQUID_AC_OPTIMIZATION.md)。

## 开发集：先比较再选型

全部 30 个已知案例各测两种候选顺序，五个方案共 300 条观察；整条最终控制指令完全匹配才通过。温度组合是新动作协议，原始模型选择与动作展开分别记录，不与原始逐 Key 协议混称同一种原生准确率。

| 方案 | 规范原序 /20 | 规范换序 /20 | 诊断原序 /10 | 诊断换序 /10 | 规范原序多余 / 缺失指令 |
|---|---:|---:|---:|---:|---:|
| 原始基线 | 0 | 0 | 0 | 0 | 105 / 0 |
| 原两阶段 | 11 | 11 | 5 | 5 | 2 / 8 |
| 语义门控 | 12 | 14 | 6 | 5 | 3 / 5 |
| 语义门控＋温度组合 | 16 | 16 | 6 | 5 | 1 / 3 |
| 组合＋六个示例 | 14 | 16 | 6 | 5 | 2 / 5 |

温度组合开发集原序合计 22/30，原两阶段 16/30；换序分别 21/30 与 16/30。附加示例在规范原序只达到 14/20，没有超过无示例的组合方案，因此未入选。开发集原序相对原两阶段修复 7 条、退步 1 条（N03），并非每题都不退步。

## 留出新问题：选型后才推理

24 条新表达／组合，原序和换序各一遍，共 144 条观察。问题、参考与规则于 11:16:37 UTC 冻结；开发集 11:22:16 完成，11:24:21 固定候选，11:24:25 才开始验证，11:26:33 完成。验证结果未用于换候选或修改提示词。这是按已知错误类别编写的同领域留出集，不是外部盲测。

| 方案 | 原序 /24 | 换序 /24 | 原序多余指令 | 原序缺失指令 | 换序后输出改变的案例 /24 |
|---|---:|---:|---:|---:|---:|
| 原始基线 | 0 | 0 | 164 | 1 | 24 |
| 原两阶段 | 12 | 12 | 8 | 9 | 11 |
| 语义门控＋温度组合 | 12 | 12 | 4 | 10 | 3 |

候选修复 L02、L04、L16、L24，也把原先正确的 L09、L10、L17、L18 答错，净正确数不变。L09（AI Smart）、L10（关闭防冻）、L18（室内清洁）在门控中全部选 omit；L17 漏放行竖直位置，误放行室外静音。候选少发了多余指令，但漏发更多；选项顺序更稳定也没有提高本批正确率。

## 每条完整决策的耗时

单位 ms；取值阶段耗时摊到该组全部请求，未执行取值的任务按 0 计，所以门控＋取值＝完整决策。P95 使用既有评分器的最近秩定义。客户端往返包含本机 HTTP，不等于纯 GPU 计算。

| 数据 / 原序 | 方案 | 门控均值 | 取值摊销均值 | 完整均值 | 完整 P95 | 该组所有决策 HTTP 总时间（秒） |
|---|---|---:|---:|---:|---:|---:|
| 规范20 | 原始基线 | 0.0 | 617.5 | 617.5 | 628.0 | 12.351 |
| 规范20 | 原两阶段 | 604.5 | 126.5 | 731.0 | 787.5 | 14.620 |
| 规范20 | 语义门控＋温度组合 | 989.4 | 143.3 | 1132.7 | 1210.6 | 22.654 |
| 诊断10 | 原始基线 | 0.0 | 624.7 | 624.7 | 629.6 | 6.247 |
| 诊断10 | 原两阶段 | 612.2 | 148.8 | 761.0 | 869.4 | 7.610 |
| 诊断10 | 语义门控＋温度组合 | 1005.2 | 130.9 | 1136.1 | 1269.1 | 11.361 |
| 新问题24 | 原始基线 | 0.0 | 618.6 | 618.6 | 623.2 | 14.847 |
| 新问题24 | 原两阶段 | 603.9 | 130.0 | 733.9 | 808.3 | 17.613 |
| 新问题24 | 语义门控＋温度组合 | 990.8 | 126.4 | 1117.2 | 1197.3 | 26.812 |

新问题取值阶段实际执行次数：原两阶段 22/24，组合方案 19/24；只统计已执行取值时，其均值分别为 141.8 / 159.7 ms。主要新增时间在语义门控。这里的完整决策为 1–2 次 HTTP 调用，不是 30 个 Key 分别串行调用。原始基线只有取值一次调用。

`client_ms` 为每条实际 HTTP 耗时之和；`wall_ms` 从第一份请求构造完成后开始，另含阶段间处理。SSM、S3、预热、初次提示构建和离线分析不计入上述均值。开发和验证每阶段每方案预热一次；方案次序按案例轮换，所有模型调用严格串行。

## 全部原序问题与实际选择

“∅”代表空指令列表。完整选项、门控选择、模型原始响应、动作映射与换序结果保存在两个阶段 receipts.jsonl 中；本表按冻结参考比较最终 commands，未事后修复。

### 开发集

| ID | 用户问题 | 参考指令 | 原两阶段 | 温度组合 |
|---|---|---|---|---|
| S01 | Turn on the air conditioner. | `t_power=1` | 正确：`t_power=1` | 正确：`t_power=1` |
| S02 | Set the air conditioner to cooling mode. | `t_work_mode=2` | 错误：`∅` | 正确：`t_work_mode=2` |
| S03 | Set the air conditioner temperature to 24 degrees Celsius. | `t_temp=24, t_temp_type=0` | 正确：`t_temp=24, t_temp_type=0` | 正确：`t_temp=24, t_temp_type=0` |
| S04 | Set the air conditioner temperature to 68 degrees Fahrenheit. | `t_temp_f=68, t_temp_type=1` | 错误：`t_temp_f=68` | 正确：`t_temp_f=68, t_temp_type=1` |
| S05 | Set the air conditioner fan speed to high. | `t_fan_speed=9` | 正确：`t_fan_speed=9` | 正确：`t_fan_speed=9` |
| S06 | Turn on quiet mode for the indoor unit. | `t_fan_mute=1` | 正确：`t_fan_mute=1` | 正确：`t_fan_mute=1` |
| S07 | Turn on outdoor quiet mode. | `t_outdoor_mute=1` | 错误：`t_fan_mute=1, t_outdoor_mute=1` | 正确：`t_outdoor_mute=1` |
| S08 | Turn on air purification. | `t_purify=1` | 正确：`t_purify=1` | 正确：`t_purify=1` |
| S09 | Turn off the air conditioner display light. | `t_dimmer=0` | 错误：`∅` | 错误：`∅` |
| S10 | Set the horizontal airflow to both sides. | `t_swing_direction=2` | 正确：`t_swing_direction=2` | 正确：`t_swing_direction=2` |
| M01 | Turn on the air conditioner, switch it to cooling mode, and set the temperature to 24 degrees Celsius. | `t_power=1, t_work_mode=2, t_temp=24, t_temp_type=0` | 正确：`t_power=1, t_work_mode=2, t_temp=24, t_temp_type=0` | 正确：`t_power=1, t_work_mode=2, t_temp=24, t_temp_type=0` |
| M02 | Switch the air conditioner to heating mode, set it to 26 degrees Celsius, and use medium fan speed. | `t_work_mode=1, t_temp=26, t_temp_type=0, t_fan_speed=7` | 正确：`t_work_mode=1, t_temp=26, t_temp_type=0, t_fan_speed=7` | 正确：`t_work_mode=1, t_temp=26, t_temp_type=0, t_fan_speed=7` |
| M03 | Set cooling mode, change the fan speed to high, and turn on energy saving. | `t_work_mode=2, t_fan_speed=9, t_eco=1` | 错误：`t_fan_speed=9, t_eco=1` | 错误：`t_fan_speed=9, t_eco=1` |
| M04 | Turn on both indoor quiet mode and outdoor quiet mode. | `t_fan_mute=1, t_outdoor_mute=1` | 正确：`t_fan_mute=1, t_outdoor_mute=1` | 正确：`t_fan_mute=1, t_outdoor_mute=1` |
| M05 | Turn on air purification and turn off the display light. | `t_purify=1, t_dimmer=0` | 错误：`t_purify=1` | 错误：`t_purify=1` |
| M06 | Enable fresh air and healthy wind. | `t_fresh_air=1, t_health_fan=1` | 正确：`t_fresh_air=1, t_health_fan=1` | 正确：`t_fresh_air=1, t_health_fan=1` |
| M07 | Start indoor self-clean and outdoor self-clean. | `t_indoor_selfclean=1, t_outdoor_selfclean=1` | 正确：`t_indoor_selfclean=1, t_outdoor_selfclean=1` | 正确：`t_indoor_selfclean=1, t_outdoor_selfclean=1` |
| M08 | Turn on up-and-down swing and set the horizontal airflow to both sides. | `t_up_down=1, t_swing_direction=2` | 错误：`t_up_down=1, t_left_right=1, t_swing_direction=2` | 错误：`t_up_down=1, t_left_right=1, t_swing_direction=2` |
| M09 | Turn on demand response, set the DR temperature offset to 5 degrees, and set the DR load capacity to 60 percent. | `t_dr_onoff=1, t_dr_offset=5, t_dr_mode=60` | 错误：`t_dr_offset=5, t_dr_mode=60` | 正确：`t_dr_onoff=1, t_dr_offset=5, t_dr_mode=60` |
| M10 | Switch to cooling mode, turn on Super Mode, and set the temperature to 22 degrees Celsius. | `t_work_mode=2, t_super=1, t_temp=22, t_temp_type=0` | 错误：`t_temp=22, t_super=1` | 正确：`t_work_mode=2, t_temp=22, t_temp_type=0, t_super=1` |
| N01 | Please power on the AC without changing its operating mode. | `t_power=1` | 正确：`t_power=1` | 正确：`t_power=1` |
| N02 | Enable Comfort Auto; leave the operating mode unchanged. | `t_indoortemp_detection=1` | 正确：`t_indoortemp_detection=1` | 正确：`t_indoortemp_detection=1` |
| N03 | Enable 8-degree frost protection; leave the operating mode unchanged. | `t_8heat=1` | 正确：`t_8heat=1` | 错误：`∅` |
| N04 | Stop indoor quiet mode, but leave outdoor quiet unchanged. | `t_fan_mute=0` | 正确：`t_fan_mute=0` | 正确：`t_fan_mute=0` |
| N05 | Use heating at 25 degrees Celsius with low fan speed. | `t_work_mode=1, t_temp=25, t_temp_type=0, t_fan_speed=5` | 错误：`t_work_mode=1, t_temp=25, t_temp_type=0, t_fan_speed=5, t_8heat=1` | 错误：`t_temp=25, t_temp_type=0, t_fan_speed=5` |
| N06 | Use cooling at 72 degrees Fahrenheit with medium-high fan speed. | `t_work_mode=2, t_temp_f=72, t_temp_type=1, t_fan_speed=8` | 错误：`t_temp_f=72, t_fan_speed=8` | 错误：`t_fan_speed=8` |
| N07 | Switch off the display light and switch on air purification; leave the main power setting unchanged. | `t_dimmer=0, t_purify=1` | 错误：`t_purify=1` | 错误：`t_purify=1` |
| N08 | Enable demand response with a 7-degree temperature offset and 45 percent load capacity. | `t_dr_onoff=1, t_dr_offset=7, t_dr_mode=45` | 错误：`t_dr_offset=7, t_dr_mode=45` | 正确：`t_dr_onoff=1, t_dr_offset=7, t_dr_mode=45` |
| N09 | Enable vertical oscillation and point horizontal airflow straight ahead. | `t_up_down=1, t_swing_direction=0` | 错误：`t_up_down=1, t_swing_angle=0, t_swing_direction=0` | 正确：`t_up_down=1, t_swing_direction=0` |
| N10 | Enable fresh air while keeping healthy wind unchanged. | `t_fresh_air=1` | 正确：`t_fresh_air=1` | 正确：`t_fresh_air=1` |
### 留出验证

| ID | 用户问题 | 参考指令 | 原两阶段 | 温度组合 |
|---|---|---|---|---|
| L01 | Shut down the AC, leaving its mode and all feature settings alone. | `t_power=0` | 正确：`t_power=0` | 正确：`t_power=0` |
| L02 | Select cooling as the operating mode. Make no other changes. | `t_work_mode=2` | 错误：`∅` | 正确：`t_work_mode=2` |
| L03 | I'd like a target of 22 degrees Celsius. | `t_temp=22, t_temp_type=0` | 正确：`t_temp=22, t_temp_type=0` | 正确：`t_temp=22, t_temp_type=0` |
| L04 | Make the setpoint 75 degrees Fahrenheit. | `t_temp_f=75, t_temp_type=1` | 错误：`t_temp=31, t_temp_f=75, t_temp_type=1` | 正确：`t_temp_f=75, t_temp_type=1` |
| L05 | Quiet down the outdoor unit; keep indoor quiet at its current setting. | `t_outdoor_mute=1` | 错误：`t_fan_mute=0, t_outdoor_mute=0` | 错误：`t_outdoor_mute=0` |
| L06 | Darken the display panel without touching the main power. | `t_dimmer=0` | 错误：`t_dimmer=1` | 错误：`∅` |
| L07 | Deactivate energy-saving mode while keeping the operating mode as it is. | `t_eco=0` | 正确：`t_eco=0` | 正确：`t_eco=0` |
| L08 | Start fresh-air ventilation and disable healthy wind. | `t_fresh_air=1, t_health_fan=0` | 错误：`t_fresh_air=1` | 错误：`t_swing_follow=2, t_fresh_air=1, t_health_fan=0` |
| L09 | Turn AI Smart on; preserve the current AI Wind setting. | `t_tms=1` | 正确：`t_tms=1` | 错误：`∅` |
| L10 | Stop the 8-degree frost-protection function without changing the main mode. | `t_8heat=0` | 正确：`t_8heat=0` | 错误：`∅` |
| L11 | Enable automatic defrost cleaning. | `t_auto_defrost_clean=1` | 正确：`t_auto_defrost_clean=1` | 正确：`t_auto_defrost_clean=1` |
| L12 | Set demand-response load capacity to 63 percent; leave its offset unchanged. | `t_dr_mode=63` | 正确：`t_dr_mode=63` | 正确：`t_dr_mode=63` |
| L13 | Heat to 29 degrees Celsius using medium-low fan speed. | `t_work_mode=1, t_temp=29, t_temp_type=0, t_fan_speed=6` | 错误：`t_work_mode=1, t_temp=29, t_fan_speed=6` | 错误：`t_temp=29, t_temp_type=0, t_fan_speed=6` |
| L14 | Cool to 67 degrees Fahrenheit and use medium fan speed. | `t_work_mode=2, t_temp_f=67, t_temp_type=1, t_fan_speed=7` | 错误：`t_temp_f=67, t_fan_speed=7` | 错误：`t_temp_f=67, t_temp_type=1, t_fan_speed=7` |
| L15 | Switch off both the air conditioner and its display light. | `t_power=0, t_dimmer=0` | 错误：`t_power=0` | 错误：`t_power=0` |
| L16 | Stop vertical oscillation and direct the horizontal airflow all left. | `t_up_down=0, t_swing_direction=4` | 错误：`t_swing_direction=4` | 正确：`t_up_down=0, t_swing_direction=4` |
| L17 | Put vertical airflow at Position 4 and enable indoor quiet. | `t_swing_angle=5, t_fan_mute=1` | 正确：`t_fan_mute=1, t_swing_angle=5` | 错误：`t_fan_mute=1, t_outdoor_mute=1` |
| L18 | Start cleaning the indoor unit only, leaving outdoor cleaning unchanged. | `t_indoor_selfclean=1` | 正确：`t_indoor_selfclean=1` | 错误：`∅` |
| L19 | Choose the elder sleep profile and turn the panel light off. | `t_sleep=2, t_dimmer=0` | 错误：`t_power=0, t_sleep=2, t_dimmer=0` | 错误：`t_sleep=2` |
| L20 | Turn demand response on, set its offset to 4 degrees and its capacity to 37 percent. | `t_dr_onoff=1, t_dr_offset=4, t_dr_mode=37` | 正确：`t_dr_onoff=1, t_dr_offset=4, t_dr_mode=37` | 正确：`t_dr_onoff=1, t_dr_offset=4, t_dr_mode=37` |
| L21 | Start the up-and-down oscillation and send horizontal air to both sides. | `t_up_down=1, t_swing_direction=2` | 错误：`t_up_down=1, t_left_right=1, t_swing_angle=0, t_swing_direction=2` | 错误：`t_up_down=1, t_left_right=1, t_swing_direction=2` |
| L22 | Activate purification while preserving the fresh-air setting. | `t_purify=1` | 正确：`t_purify=1` | 正确：`t_purify=1` |
| L23 | Keep every setting exactly as it is. | `∅` | 正确：`∅` | 正确：`∅` |
| L24 | Set the target temperature to 35 degrees Celsius. | `∅` | 错误：`t_temp=32` | 正确：`∅` |

## 证据与审计

444 条正式观察，747 次正式推理 HTTP 调用，另 14 次预热，共 761 次推理调用；全部有效，无重叠、无自动重试。共 54 个独立业务问题；方案和候选顺序重复不增加独立题数。10 项协议单元测试通过；离线审计核验冻结输入／参考／源码、每阶段实际请求、原始响应、候选映射、选型时序、服务状态与全部计时。

- [冻结计划](plan.json)、[选型](selection.json)、[最终推荐](recommendation.json)、[审计](audit.json)。
- [全部评分与分阶段耗时](accuracy_summary.json)。
- [开发原始调用](development/receipts.jsonl)、[验证原始调用](validation/receipts.jsonl)。
- [开发输入](development_cases.json)、[验证输入](validation_cases.json)、[本机离线参考](references.json)。
- [S04 完整原请求](examples/S04-request.json)、[实际第二阶段完整选项](examples/S04-value-request.json)、[实际正确回答](examples/S04-temperature_bundle-response.json)。
- [N03 实际退步回答](examples/N03-temperature_bundle-response.json)。
- [冻结运行源码](sources/)、[离线分析源码](analysis_sources/)。

未修改模型服务或默认应用流程。新客户端可显式运行组合方案用于研究；当前推荐保持 two_stage。没有向 GitHub 提交或推送。
