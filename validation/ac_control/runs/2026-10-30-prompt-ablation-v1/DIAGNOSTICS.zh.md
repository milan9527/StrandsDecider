# 两阶段错误定位与完整回答示例

第一步选择需要下发的 Key，第二步才选取具体值。第一步漏选的 Key 无法由第二步补回；第一步多选的 Key 仍可以在第二步选 omit。

以下门控指标只统计原规范20题、原始候选顺序。召回率分母为标准答案所需的40个 Key。

| 模型 | 门控选中Key数 | 其中应当选中 | 所需Key召回 | 全部omit的用例 | 门控Key集合完全正确 | 最终指令完全正确 |
|---|---:|---:|---:|---:|---:|---:|
| Strands Decider v19 | 0 | 0 | 0/40 | 20/20 | 0/20 | 0/20 |
| Liquid d1-2B | 35 | 32 | 32/40 | 2/20 | 10/20 | 11/20 |
| H2O Lightning 4B | 40 | 40 | 40/40 | 0/20 | 20/20 | 20/20 |

门控全 omit 也可能产生很高的换序稳定性，但不意味着正确。这是一种固定门控提示的实测，不代表所有两阶段设计都具有相同性能。

## Liquid：24℃温度题

> Set the air conditioner temperature to 24 degrees Celsius.

参考：`t_temp=24`, `t_temp_type=0`

- baseline：错误，`t_8heat=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp=24`, `t_temp_f=80`, `t_temp_type=0`
- combined：错误，`t_dr_offset=24`, `t_temp=24`, `t_temp_f=90`, `t_temp_type=0`
- two_stage：正确，`t_temp=24`, `t_temp_type=0`
  第一阶段选中：t_temp, t_temp_type

## H2O Lightning 4B：S01

> Turn on the air conditioner.

参考：`t_power=1`

- baseline：错误，`t_power=1`, `t_work_mode=2`
- criteria_only：错误，`t_power=1`, `t_work_mode=2`
- rules_only：错误，`t_power=1`, `t_work_mode=2`
- combined：错误，`t_power=1`, `t_work_mode=2`
- two_stage：正确，`t_power=1`
  第一阶段选中：t_power

## H2O Lightning 4B：M08

> Turn on up-and-down swing and set the horizontal airflow to both sides.

参考：`t_swing_direction=2`, `t_up_down=1`

- baseline：错误，`t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1`
- criteria_only：错误，`t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1`
- rules_only：正确，`t_swing_direction=2`, `t_up_down=1`
- combined：错误，`t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1`
- two_stage：正确，`t_swing_direction=2`, `t_up_down=1`
  第一阶段选中：t_up_down, t_swing_direction

## H2O Lightning 4B：N03

> Enable 8-degree frost protection; leave the operating mode unchanged.

参考：`t_8heat=1`

- baseline：正确，`t_8heat=1`
- rules_only：错误，`t_8heat=1`, `t_temp_type=0`
- combined：错误，`t_8heat=1`, `t_temp_type=0`
- two_stage：正确，`t_8heat=1`
  第一阶段选中：t_8heat

## H2O Lightning 4B：N04

> Stop indoor quiet mode, but leave outdoor quiet unchanged.

参考：`t_fan_mute=0`

- baseline：正确，`t_fan_mute=0`
- rules_only：错误，`t_fan_mute=0`, `t_indoortemp_detection=0`
- combined：错误，`t_fan_mute=0`, `t_indoortemp_detection=0`
- two_stage：错误，`t_fan_mute=0`, `t_indoortemp_detection=0`
  第一阶段选中：t_fan_mute, t_indoortemp_detection

## Strands Decider v19：S03

> Set the air conditioner temperature to 24 degrees Celsius.

参考：`t_temp=24`, `t_temp_type=0`

- baseline：错误，`t_temp=24`
- rules_only：错误，`t_temp=24`
- combined：错误，`t_temp=24`, `t_temp_f=90`, `t_temp_type=0`
- two_stage：错误，∅
  第一阶段选中：无

## 如何查看完整请求和原始回答

- [S03五组完整请求及问题改写](examples/S03.requests.zh.md)。JSON中的state包含完整30项Command Set。
- [S03三个模型五组实际输出](examples/S03.actual_outputs.json)：包括参考、实际cmdList、多余/缺失与门控Key。
- [S03原始HTTP阶段记录](examples/S03.raw_http.json)：包括每一步实际payload、原始response_text、解析response、概率及计时。历史基线记录与本轮记录用source字段区分。
- [N04 H2O反例的全部实际请求与回答](examples/N04.h2o.raw_http.json)：包括基线、三个改写组和两阶段的完整问题及候选。
- [完整对照报告](ABLATION.zh.md)、[门控诊断数据](gate_diagnostics.json)。
