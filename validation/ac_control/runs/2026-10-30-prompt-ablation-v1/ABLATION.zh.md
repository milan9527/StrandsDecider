# 空调控制：三个模型的提示词与两阶段对照实验

主指标为原规范20条 Query 的整条指令集合完全匹配；任何多余、缺失或错值均失败。三个模型共五组，原规范各测原始与反转候选顺序。另测10条新表达/否定保持设置的诊断用例，单独统计。

基线复用同日已有的每模型40次原始调用，新增10条诊断用例实测。其余组全部新增实测。所有 Query、完整30项能力集、合法候选范围和离线标准答案固定。提示词及诊断集在本轮推理前冻结，运行中不按结果调参。

## 原规范完全匹配

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---:|---:|---:|---:|---:|
| Strands Decider v19 | 4/20（20.0%） | 1/20（5.0%） | 3/20（15.0%） | 1/20（5.0%） | 0/20（0.0%） |
| Liquid d1-2B | 0/20（0.0%） | 1/20（5.0%） | 6/20（30.0%） | 4/20（20.0%） | 11/20（55.0%） |
| H2O Lightning 4B | 18/20（90.0%） | 18/20（90.0%） | 19/20（95.0%） | 18/20（90.0%） | 20/20（100.0%） |

仅改选项条件：将“Set Mode to Cool”等动作式描述改为“用户请求制冷”等意图匹配条件。仅改规则与问题：区分用户 Query 与能力目录，明确温度单位伴随字段、垂直摆风表示和独立功能。两项合并：同时采用上述改写。两阶段：第一步对30个 Key 选择 apply/omit，第二步只对模型选择的 Key 选择 Value，第二步仍有 omit。两个阶段都保留完整能力集。

## 反转候选与稳定性

| 模型 | 组别 | 原始顺序 | 反转顺序 | 换序后输出改变 | 原始多余对 | 原始缺失对 |
|---|---|---:|---:|---:|---:|---:|
| Strands Decider v19 | 原始基线 | 4/20（20.0%） | 2/20（10.0%） | 18/20 | 1 | 21 |
| Strands Decider v19 | 仅改选项条件 | 1/20（5.0%） | 0/20（0.0%） | 20/20 | 38 | 12 |
| Strands Decider v19 | 仅改规则与问题 | 3/20（15.0%） | 3/20（15.0%） | 8/20 | 1 | 32 |
| Strands Decider v19 | 两项合并 | 1/20（5.0%） | 0/20（0.0%） | 20/20 | 44 | 15 |
| Strands Decider v19 | 两阶段 | 0/20（0.0%） | 0/20（0.0%） | 0/20 | 0 | 40 |
| Liquid d1-2B | 原始基线 | 0/20（0.0%） | 0/20（0.0%） | 18/20 | 105 | 0 |
| Liquid d1-2B | 仅改选项条件 | 1/20（5.0%） | 2/20（10.0%） | 17/20 | 65 | 1 |
| Liquid d1-2B | 仅改规则与问题 | 6/20（30.0%） | 3/20（15.0%） | 14/20 | 25 | 2 |
| Liquid d1-2B | 两项合并 | 4/20（20.0%） | 5/20（25.0%） | 11/20 | 36 | 1 |
| Liquid d1-2B | 两阶段 | 11/20（55.0%） | 11/20（55.0%） | 5/20 | 2 | 8 |
| H2O Lightning 4B | 原始基线 | 18/20（90.0%） | 18/20（90.0%） | 0/20 | 2 | 0 |
| H2O Lightning 4B | 仅改选项条件 | 18/20（90.0%） | 18/20（90.0%） | 0/20 | 2 | 0 |
| H2O Lightning 4B | 仅改规则与问题 | 19/20（95.0%） | 19/20（95.0%） | 0/20 | 1 | 0 |
| H2O Lightning 4B | 两项合并 | 18/20（90.0%） | 18/20（90.0%） | 0/20 | 2 | 0 |
| H2O Lightning 4B | 两阶段 | 20/20（100.0%） | 20/20（100.0%） | 0/20 | 0 | 0 |

## 新表达及反例（另计10条）

这10条根据此前已见错误设计，在新调用前冻结，是诊断集，不是独立盲测集。覆盖“保持另一个设置不变”、相邻功能区别，以及新温度/负载数值；未覆盖冲突指令与越界数值。

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---:|---:|---:|---:|---:|
| Strands Decider v19 | 0/10（0.0%） | 0/10（0.0%） | 0/10（0.0%） | 0/10（0.0%） | 0/10（0.0%） |
| Liquid d1-2B | 0/10（0.0%） | 1/10（10.0%） | 1/10（10.0%） | 4/10（40.0%） | 5/10（50.0%） |
| H2O Lightning 4B | 10/10（100.0%） | 9/10（90.0%） | 7/10（70.0%） | 8/10（80.0%） | 9/10（90.0%） |

## 耗时、调用与单位补全

耗时为原规范原始顺序下每条 Query 的服务端总耗时，两阶段累加实际发生的两次调用。统计边界依各模型服务实现，不能当作纯GPU时间。基线 Decider 客户端走HTTPS，本轮走GPU loopback，因此不比较客户端延迟。

| 模型 | 组别 | 平均服务端 ms | P95 ms | HTTP调用 /20例 | 原始完全匹配 | 工程单位补全后 | 调用/格式失败 |
|---|---|---:|---:|---:|---:|---:|---:|
| Strands Decider v19 | 原始基线 | 2906.9 | 2956.4 | 20 | 4/20 | 7/20 | 0 |
| Strands Decider v19 | 仅改选项条件 | 3075.0 | 3129.8 | 20 | 1/20 | 1/20 | 0 |
| Strands Decider v19 | 仅改规则与问题 | 3355.3 | 3406.9 | 20 | 3/20 | 5/20 | 0 |
| Strands Decider v19 | 两项合并 | 3474.0 | 3514.4 | 20 | 1/20 | 1/20 | 0 |
| Strands Decider v19 | 两阶段 | 3189.5 | 3237.8 | 20 | 0/20 | 0/20 | 0 |
| Liquid d1-2B | 原始基线 | 608.7 | 612.5 | 20 | 0/20 | 0/20 | 0 |
| Liquid d1-2B | 仅改选项条件 | 826.6 | 831.3 | 20 | 1/20 | 1/20 | 0 |
| Liquid d1-2B | 仅改规则与问题 | 722.9 | 726.0 | 20 | 6/20 | 6/20 | 0 |
| Liquid d1-2B | 两项合并 | 905.2 | 908.9 | 20 | 4/20 | 4/20 | 0 |
| Liquid d1-2B | 两阶段 | 741.1 | 791.5 | 38 | 11/20 | 12/20 | 0 |
| H2O Lightning 4B | 原始基线 | 5962.1 | 6048.7 | 20 | 18/20 | 18/20 | 0 |
| H2O Lightning 4B | 仅改选项条件 | 6318.1 | 6393.3 | 20 | 18/20 | 18/20 | 0 |
| H2O Lightning 4B | 仅改规则与问题 | 6989.7 | 7030.6 | 20 | 19/20 | 19/20 | 0 |
| H2O Lightning 4B | 两项合并 | 7254.6 | 7289.7 | 20 | 18/20 | 18/20 | 0 |
| H2O Lightning 4B | 两阶段 | 7099.7 | 7612.2 | 40 | 20/20 | 20/20 | 0 |

工程单位补全是离线附加指标：仅当模型输出恰好一种温度字段且缺少单位时补充对应单位。不覆盖已有单位、不解决双温标冲突、不删除多余指令；不计入模型原始准确率。

正式新增HTTP调用：725；观察数：750（含120条历史基线）。没有自动重试，没有向真实空调下发指令。预检单独留存，不参与成绩。

## 相对基线的修复与退步

| 模型 | 组别 | 修复用例 | 退步用例 |
|---|---|---|---|
| Strands Decider v19 | 仅改选项条件 | 无 | S05, S07, S08 |
| Strands Decider v19 | 仅改规则与问题 | 无 | S07 |
| Strands Decider v19 | 两项合并 | S04 | S05, S07, S08, S10 |
| Strands Decider v19 | 两阶段 | 无 | S05, S07, S08, S10 |
| Liquid d1-2B | 仅改选项条件 | S10 | 无 |
| Liquid d1-2B | 仅改规则与问题 | S02, S06, S08, S10, M03, M04 | 无 |
| Liquid d1-2B | 两项合并 | S01, S02, S06, S08 | 无 |
| Liquid d1-2B | 两阶段 | S01, S03, S05, S06, S08, S10, M01, M02, M04, M06, M07 | 无 |
| H2O Lightning 4B | 仅改选项条件 | 无 | 无 |
| H2O Lightning 4B | 仅改规则与问题 | M08 | 无 |
| H2O Lightning 4B | 两项合并 | 无 | 无 |
| H2O Lightning 4B | 两阶段 | S01, M08 | 无 |

## 全部问题、参考与实际回答（原始顺序）

### S01 开机

> Turn on the air conditioner.

参考：`t_power=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ ∅ | ✗ `t_fresh_air=1`, `t_outdoor_selfclean=1`, `t_sleep=1`, `t_temp_f=90`, `t_work_mode=2` | ✗ ∅ | ✗ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1`, `t_temp_f=90` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_outdoor_selfclean=1`, `t_power=1`, `t_swing_angle=0`, `t_swing_follow=0` | ✗ `t_8heat=1`, `t_power=1`, `t_temp_f=90` | ✗ `t_8heat=1`, `t_power=1` | ✓ `t_power=1` | ✓ `t_power=1` |
| H2O Lightning 4B | ✗ `t_power=1`, `t_work_mode=2` | ✗ `t_power=1`, `t_work_mode=2` | ✗ `t_power=1`, `t_work_mode=2` | ✗ `t_power=1`, `t_work_mode=2` | ✓ `t_power=1` |

### S02 选择制冷模式

> Set the air conditioner to cooling mode.

参考：`t_work_mode=2`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ `t_temp_f=90`, `t_work_mode=2` | ✗ `t_dr_mode=100`, `t_outdoor_selfclean=1`, `t_sleep=1`, `t_temp_f=90`, `t_work_mode=2` | ✗ `t_temp_f=90` | ✗ `t_outdoor_selfclean=1`, `t_temp_f=90`, `t_temp_type=0`, `t_work_mode=2` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_outdoor_selfclean=1`, `t_power=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_work_mode=2` | ✗ `t_temp_f=90`, `t_work_mode=2` | ✓ `t_work_mode=2` | ✓ `t_work_mode=2` | ✗ ∅ |
| H2O Lightning 4B | ✓ `t_work_mode=2` | ✓ `t_work_mode=2` | ✓ `t_work_mode=2` | ✓ `t_work_mode=2` | ✓ `t_work_mode=2` |

### S03 设置摄氏温度

> Set the air conditioner temperature to 24 degrees Celsius.

参考：`t_temp=24`, `t_temp_type=0`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ `t_temp=24` | ✗ `t_dr_offset=24`, `t_temp=24`, `t_work_mode=2` | ✗ `t_temp=24` | ✗ `t_temp=24`, `t_temp_f=90`, `t_temp_type=0` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp=24`, `t_temp_f=80`, `t_temp_type=0` | ✗ `t_8heat=1`, `t_swing_angle=0`, `t_temp=24`, `t_temp_f=90`, `t_temp_type=0` | ✗ `t_8heat=1`, `t_temp=24`, `t_temp_f=80`, `t_temp_type=0` | ✗ `t_dr_offset=24`, `t_temp=24`, `t_temp_f=90`, `t_temp_type=0` | ✓ `t_temp=24`, `t_temp_type=0` |
| H2O Lightning 4B | ✓ `t_temp=24`, `t_temp_type=0` | ✓ `t_temp=24`, `t_temp_type=0` | ✓ `t_temp=24`, `t_temp_type=0` | ✓ `t_temp=24`, `t_temp_type=0` | ✓ `t_temp=24`, `t_temp_type=0` |

### S04 设置华氏温度

> Set the air conditioner temperature to 68 degrees Fahrenheit.

参考：`t_temp_f=68`, `t_temp_type=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ `t_temp_f=68` | ✗ `t_temp_f=68`, `t_work_mode=2` | ✗ `t_temp_f=68` | ✓ `t_temp_f=68`, `t_temp_type=1` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp_f=68`, `t_temp_type=1` | ✗ `t_8heat=1`, `t_swing_angle=0`, `t_temp_f=68`, `t_temp_type=1` | ✗ `t_8heat=1`, `t_temp=28`, `t_temp_f=68`, `t_temp_type=1` | ✗ `t_temp=30`, `t_temp_f=68`, `t_temp_type=1` | ✗ `t_temp_f=68` |
| H2O Lightning 4B | ✓ `t_temp_f=68`, `t_temp_type=1` | ✓ `t_temp_f=68`, `t_temp_type=1` | ✓ `t_temp_f=68`, `t_temp_type=1` | ✓ `t_temp_f=68`, `t_temp_type=1` | ✓ `t_temp_f=68`, `t_temp_type=1` |

### S05 选择高风速

> Set the air conditioner fan speed to high.

参考：`t_fan_speed=9`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✓ `t_fan_speed=9` | ✗ `t_fan_speed=9`, `t_outdoor_selfclean=1`, `t_work_mode=0` | ✓ `t_fan_speed=9` | ✗ `t_fan_speed=9`, `t_indoor_selfclean=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_temp_f=90`, `t_temp_type=0` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_dimmer=1`, `t_fan_speed=9`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0` | ✗ `t_dimmer=1`, `t_fan_speed=9`, `t_swing_angle=0`, `t_temp_f=90` | ✗ `t_dimmer=1`, `t_fan_speed=9` | ✗ `t_dimmer=1`, `t_fan_speed=9`, `t_temp_f=90`, `t_work_mode=0` | ✓ `t_fan_speed=9` |
| H2O Lightning 4B | ✓ `t_fan_speed=9` | ✓ `t_fan_speed=9` | ✓ `t_fan_speed=9` | ✓ `t_fan_speed=9` | ✓ `t_fan_speed=9` |

### S06 开启室内机静音

> Turn on quiet mode for the indoor unit.

参考：`t_fan_mute=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ ∅ | ✗ `t_indoor_selfclean=1`, `t_sleep=1` | ✗ ∅ | ✗ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1`, `t_temp_f=90` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_fan_mute=1`, `t_outdoor_mute=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_swing_follow=0` | ✗ `t_8heat=1`, `t_fan_mute=1`, `t_outdoor_mute=1`, `t_swing_angle=0`, `t_swing_direction=2` | ✓ `t_fan_mute=1` | ✓ `t_fan_mute=1` | ✓ `t_fan_mute=1` |
| H2O Lightning 4B | ✓ `t_fan_mute=1` | ✓ `t_fan_mute=1` | ✓ `t_fan_mute=1` | ✓ `t_fan_mute=1` | ✓ `t_fan_mute=1` |

### S07 开启室外机静音

> Turn on outdoor quiet mode.

参考：`t_outdoor_mute=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✓ `t_outdoor_mute=1` | ✗ `t_fan_mute=1`, `t_outdoor_mute=1`, `t_outdoor_selfclean=1` | ✗ ∅ | ✗ `t_outdoor_mute=1`, `t_outdoor_selfclean=1`, `t_temp_f=90` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_fan_mute=1`, `t_outdoor_mute=1`, `t_swing_angle=0`, `t_swing_follow=0` | ✗ `t_8heat=1`, `t_fan_mute=1`, `t_outdoor_mute=1`, `t_swing_angle=0`, `t_swing_direction=2` | ✗ `t_fan_mute=1`, `t_outdoor_mute=1` | ✗ `t_fan_mute=1`, `t_outdoor_mute=1` | ✗ `t_fan_mute=1`, `t_outdoor_mute=1` |
| H2O Lightning 4B | ✓ `t_outdoor_mute=1` | ✓ `t_outdoor_mute=1` | ✓ `t_outdoor_mute=1` | ✓ `t_outdoor_mute=1` | ✓ `t_outdoor_mute=1` |

### S08 开启空气净化

> Turn on air purification.

参考：`t_purify=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✓ `t_purify=1` | ✗ `t_fresh_air=1`, `t_indoor_selfclean=1`, `t_onekey_selfclean=1`, `t_outdoor_selfclean=1`, `t_purify=1` | ✓ `t_purify=1` | ✗ `t_indoor_selfclean=1`, `t_onekey_selfclean=1`, `t_outdoor_selfclean=1`, `t_purify=1`, `t_temp_f=90` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_outdoor_selfclean=1`, `t_purify=1`, `t_swing_angle=0`, `t_swing_follow=0` | ✗ `t_8heat=1`, `t_power=1`, `t_purify=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_temp_f=90` | ✓ `t_purify=1` | ✓ `t_purify=1` | ✓ `t_purify=1` |
| H2O Lightning 4B | ✓ `t_purify=1` | ✓ `t_purify=1` | ✓ `t_purify=1` | ✓ `t_purify=1` | ✓ `t_purify=1` |

### S09 关闭 LED 显示屏

> Turn off the air conditioner display light.

参考：`t_dimmer=0`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ ∅ | ✗ `t_power=0` | ✗ ∅ | ✗ `t_temp_f=90` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=0`, `t_dimmer=0`, `t_dr_mode=0`, `t_fan_mute=0`, `t_outdoor_mute=0`, `t_outdoor_selfclean=1`, `t_power=0`, `t_swing_angle=0`, `t_swing_follow=0`, `t_tms=0` | ✗ `t_dr_onoff=0`, `t_power=0`, `t_swing_direction=2` | ✗ `t_8heat=0`, `t_swing_follow=0` | ✗ ∅ | ✗ ∅ |
| H2O Lightning 4B | ✓ `t_dimmer=0` | ✓ `t_dimmer=0` | ✓ `t_dimmer=0` | ✓ `t_dimmer=0` | ✓ `t_dimmer=0` |

### S10 选择两侧水平送风

> Set the horizontal airflow to both sides.

参考：`t_swing_direction=2`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✓ `t_swing_direction=2` | ✓ `t_swing_direction=2` | ✓ `t_swing_direction=2` | ✗ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_temp_f=90` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_outdoor_mute=0`, `t_outdoor_selfclean=1`, `t_swing_angle=3`, `t_swing_direction=2`, `t_swing_follow=0` | ✓ `t_swing_direction=2` | ✓ `t_swing_direction=2` | ✗ `t_left_right=1`, `t_swing_direction=2` | ✓ `t_swing_direction=2` |
| H2O Lightning 4B | ✓ `t_swing_direction=2` | ✓ `t_swing_direction=2` | ✓ `t_swing_direction=2` | ✓ `t_swing_direction=2` | ✓ `t_swing_direction=2` |

### M01 电源、模式与摄氏温度

> Turn on the air conditioner, switch it to cooling mode, and set the temperature to 24 degrees Celsius.

参考：`t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ `t_temp=24`, `t_work_mode=2` | ✗ `t_dr_offset=24`, `t_temp=24`, `t_work_mode=2` | ✗ ∅ | ✗ `t_temp=24`, `t_temp_f=90`, `t_temp_type=0`, `t_work_mode=2` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=0`, `t_dr_offset=24`, `t_dr_onoff=1`, `t_outdoor_selfclean=1`, `t_power=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp=24`, `t_temp_f=80`, `t_temp_type=0`, `t_work_mode=2` | ✗ `t_dr_onoff=1`, `t_power=1`, `t_swing_angle=0`, `t_temp=24`, `t_temp_f=90`, `t_temp_type=0`, `t_work_mode=2` | ✗ `t_8heat=1`, `t_power=1`, `t_temp=24`, `t_temp_f=80`, `t_temp_type=0`, `t_work_mode=2` | ✗ `t_8heat=1`, `t_dr_offset=24`, `t_dr_onoff=1`, `t_power=1`, `t_temp=24`, `t_temp_f=90`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2` |
| H2O Lightning 4B | ✓ `t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2` |

### M02 制热模式、温度与风速

> Switch the air conditioner to heating mode, set it to 26 degrees Celsius, and use medium fan speed.

参考：`t_fan_speed=7`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ `t_fan_speed=7`, `t_temp=26`, `t_work_mode=1` | ✗ `t_dr_offset=26`, `t_temp=26`, `t_work_mode=1` | ✗ `t_temp=26` | ✗ `t_temp=26`, `t_temp_f=90`, `t_temp_type=0`, `t_work_mode=1` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_dimmer=1`, `t_dr_offset=26`, `t_fan_speed=7`, `t_outdoor_selfclean=1`, `t_power=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp=26`, `t_temp_f=76`, `t_temp_type=0`, `t_work_mode=1` | ✗ `t_8heat=1`, `t_dimmer=1`, `t_dr_offset=26`, `t_dr_onoff=1`, `t_fan_speed=7`, `t_power=1`, `t_swing_angle=0`, `t_temp=26`, `t_temp_f=90`, `t_temp_type=0`, `t_work_mode=1` | ✗ `t_8heat=1`, `t_dr_offset=30`, `t_fan_speed=7`, `t_temp=26`, `t_temp_f=70`, `t_temp_type=0`, `t_work_mode=1` | ✗ `t_8heat=1`, `t_dimmer=1`, `t_dr_mode=26`, `t_dr_offset=26`, `t_dr_onoff=1`, `t_fan_speed=7`, `t_temp=26`, `t_temp_f=90`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=7`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1` |
| H2O Lightning 4B | ✓ `t_fan_speed=7`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=7`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=7`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=7`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=7`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1` |

### M03 制冷模式、高风速与节能

> Set cooling mode, change the fan speed to high, and turn on energy saving.

参考：`t_eco=1`, `t_fan_speed=9`, `t_work_mode=2`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ `t_fan_speed=9`, `t_work_mode=2` | ✗ `t_eco=1`, `t_fan_speed=9`, `t_outdoor_selfclean=1`, `t_work_mode=2` | ✗ ∅ | ✗ `t_outdoor_selfclean=1`, `t_temp_f=90` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_dimmer=1`, `t_eco=1`, `t_fan_speed=9`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_work_mode=2` | ✗ `t_dimmer=1`, `t_eco=1`, `t_fan_speed=9`, `t_swing_angle=0`, `t_temp_f=90`, `t_work_mode=2` | ✓ `t_eco=1`, `t_fan_speed=9`, `t_work_mode=2` | ✗ `t_dimmer=1`, `t_eco=1`, `t_fan_mute=1`, `t_fan_speed=9`, `t_super=1`, `t_work_mode=2` | ✗ `t_eco=1`, `t_fan_speed=9` |
| H2O Lightning 4B | ✓ `t_eco=1`, `t_fan_speed=9`, `t_work_mode=2` | ✓ `t_eco=1`, `t_fan_speed=9`, `t_work_mode=2` | ✓ `t_eco=1`, `t_fan_speed=9`, `t_work_mode=2` | ✓ `t_eco=1`, `t_fan_speed=9`, `t_work_mode=2` | ✓ `t_eco=1`, `t_fan_speed=9`, `t_work_mode=2` |

### M04 室内与室外静音

> Turn on both indoor quiet mode and outdoor quiet mode.

参考：`t_fan_mute=1`, `t_outdoor_mute=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ `t_outdoor_mute=1` | ✗ `t_fan_mute=1`, `t_outdoor_mute=1`, `t_outdoor_selfclean=1`, `t_swing_direction=2` | ✗ ∅ | ✗ `t_indoor_selfclean=1`, `t_outdoor_mute=1`, `t_outdoor_selfclean=1`, `t_temp_f=90` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_fan_mute=1`, `t_indoor_selfclean=1`, `t_onekey_selfclean=1`, `t_outdoor_mute=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_swing_follow=0` | ✗ `t_fan_mute=1`, `t_outdoor_mute=1`, `t_swing_angle=0`, `t_swing_direction=2` | ✓ `t_fan_mute=1`, `t_outdoor_mute=1` | ✗ `t_fan_mute=1`, `t_outdoor_mute=1`, `t_outdoor_selfclean=1` | ✓ `t_fan_mute=1`, `t_outdoor_mute=1` |
| H2O Lightning 4B | ✓ `t_fan_mute=1`, `t_outdoor_mute=1` | ✓ `t_fan_mute=1`, `t_outdoor_mute=1` | ✓ `t_fan_mute=1`, `t_outdoor_mute=1` | ✓ `t_fan_mute=1`, `t_outdoor_mute=1` | ✓ `t_fan_mute=1`, `t_outdoor_mute=1` |

### M05 空气净化与显示屏

> Turn on air purification and turn off the display light.

参考：`t_dimmer=0`, `t_purify=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ ∅ | ✗ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1`, `t_purify=1` | ✗ ∅ | ✗ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1`, `t_purify=1`, `t_temp_f=90` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=0`, `t_dimmer=0`, `t_dr_onoff=0`, `t_fan_mute=0`, `t_outdoor_mute=0`, `t_outdoor_selfclean=1`, `t_purify=1`, `t_swing_angle=0`, `t_swing_follow=0` | ✗ `t_dimmer=0`, `t_dr_onoff=0`, `t_fan_mute=0`, `t_outdoor_mute=0`, `t_power=1`, `t_purify=1`, `t_swing_angle=0` | ✗ `t_fan_mute=0`, `t_outdoor_mute=0`, `t_purify=1`, `t_swing_follow=0` | ✗ `t_dimmer=0`, `t_dr_onoff=0`, `t_fan_mute=0`, `t_purify=1` | ✗ `t_purify=1` |
| H2O Lightning 4B | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` |

### M06 新风与健康风

> Enable fresh air and healthy wind.

参考：`t_fresh_air=1`, `t_health_fan=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ ∅ | ✗ `t_fresh_air=1`, `t_health_fan=1`, `t_indoor_selfclean=1`, `t_onekey_selfclean=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0` | ✗ ∅ | ✗ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_temp_f=90` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_fresh_air=1`, `t_health_fan=1`, `t_onekey_selfclean=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_swing_follow=0` | ✗ `t_8heat=1`, `t_fresh_air=1`, `t_health_fan=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_temp_f=90` | ✗ `t_8heat=1`, `t_fresh_air=1`, `t_health_fan=1`, `t_swing_follow=2` | ✗ `t_fresh_air=1`, `t_health_fan=1`, `t_temp_f=90` | ✓ `t_fresh_air=1`, `t_health_fan=1` |
| H2O Lightning 4B | ✓ `t_fresh_air=1`, `t_health_fan=1` | ✓ `t_fresh_air=1`, `t_health_fan=1` | ✓ `t_fresh_air=1`, `t_health_fan=1` | ✓ `t_fresh_air=1`, `t_health_fan=1` | ✓ `t_fresh_air=1`, `t_health_fan=1` |

### M07 室内与室外自清洁

> Start indoor self-clean and outdoor self-clean.

参考：`t_indoor_selfclean=1`, `t_outdoor_selfclean=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ ∅ | ✗ `t_indoor_selfclean=1`, `t_onekey_selfclean=1`, `t_outdoor_selfclean=1` | ✗ ∅ | ✗ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1`, `t_temp_f=90` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_indoor_selfclean=1`, `t_onekey_selfclean=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0` | ✗ `t_8heat=1`, `t_indoor_selfclean=1`, `t_onekey_selfclean=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_direction=2` | ✗ `t_8heat=1`, `t_indoor_selfclean=1`, `t_outdoor_selfclean=1` | ✗ `t_indoor_selfclean=1`, `t_onekey_selfclean=1`, `t_outdoor_selfclean=1` | ✓ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1` |
| H2O Lightning 4B | ✓ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1` | ✓ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1` | ✓ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1` | ✓ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1` | ✓ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1` |

### M08 垂直与水平风向

> Turn on up-and-down swing and set the horizontal airflow to both sides.

参考：`t_swing_direction=2`, `t_up_down=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ `t_swing_direction=2` | ✗ `t_left_right=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1` | ✗ `t_swing_direction=2` | ✗ `t_swing_angle=0`, `t_swing_direction=2` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_left_right=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_swing_follow=0`, `t_up_down=1` | ✗ `t_left_right=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1` | ✗ `t_left_right=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1` | ✗ `t_left_right=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1` | ✗ `t_left_right=1`, `t_swing_direction=2`, `t_up_down=1` |
| H2O Lightning 4B | ✗ `t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1` | ✗ `t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1` | ✓ `t_swing_direction=2`, `t_up_down=1` | ✗ `t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1` | ✓ `t_swing_direction=2`, `t_up_down=1` |

### M09 需求响应设置

> Turn on demand response, set the DR temperature offset to 5 degrees, and set the DR load capacity to 60 percent.

参考：`t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ `t_dr_offset=5` | ✗ `t_dr_mode=60`, `t_dr_offset=5` | ✗ ∅ | ✗ `t_dr_mode=60`, `t_dr_offset=5`, `t_temp_type=0` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp_type=1` | ✗ `t_8heat=1`, `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_temp_f=90` | ✗ `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1`, `t_temp_f=70` | ✗ `t_8heat=1`, `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1`, `t_temp=31`, `t_temp_f=90` | ✗ `t_dr_mode=60`, `t_dr_offset=5` |
| H2O Lightning 4B | ✓ `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1` | ✓ `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1` | ✓ `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1` | ✓ `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1` | ✓ `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1` |

### M10 制冷模式、Super Mode 与温度

> Switch to cooling mode, turn on Super Mode, and set the temperature to 22 degrees Celsius.

参考：`t_super=1`, `t_temp=22`, `t_temp_type=0`, `t_work_mode=2`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ `t_temp=22`, `t_work_mode=2` | ✗ `t_dr_offset=22`, `t_super=1`, `t_temp=22`, `t_work_mode=2` | ✗ `t_temp=22` | ✗ `t_temp=22`, `t_temp_f=90`, `t_temp_type=0`, `t_work_mode=2` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_dr_offset=22`, `t_outdoor_selfclean=1`, `t_super=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp=22`, `t_temp_f=70`, `t_temp_type=0`, `t_work_mode=2` | ✗ `t_8heat=1`, `t_dr_offset=22`, `t_super=1`, `t_swing_angle=0`, `t_temp=22`, `t_temp_f=90`, `t_temp_type=0`, `t_work_mode=2` | ✗ `t_8heat=1`, `t_super=1`, `t_temp=22`, `t_temp_f=70`, `t_temp_type=0`, `t_work_mode=2` | ✗ `t_8heat=1`, `t_dr_mode=22`, `t_dr_offset=22`, `t_dr_onoff=1`, `t_super=1`, `t_temp=22`, `t_temp_f=90`, `t_temp_type=0`, `t_work_mode=2` | ✗ `t_super=1`, `t_temp=22` |
| H2O Lightning 4B | ✓ `t_super=1`, `t_temp=22`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_super=1`, `t_temp=22`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_super=1`, `t_temp=22`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_super=1`, `t_temp=22`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_super=1`, `t_temp=22`, `t_temp_type=0`, `t_work_mode=2` |

### N01 仅开机，保持模式

> Please power on the AC without changing its operating mode.

参考：`t_power=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ ∅ | ✗ ∅ | ✗ ∅ | ✗ ∅ | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_dimmer=0`, `t_outdoor_selfclean=1`, `t_power=1`, `t_swing_angle=0`, `t_swing_follow=0` | ✗ `t_8heat=1`, `t_power=1`, `t_swing_angle=0`, `t_temp_f=90` | ✓ `t_power=1` | ✓ `t_power=1` | ✓ `t_power=1` |
| H2O Lightning 4B | ✓ `t_power=1` | ✓ `t_power=1` | ✓ `t_power=1` | ✓ `t_power=1` | ✓ `t_power=1` |

### N02 舒适自动与主模式区分

> Enable Comfort Auto; leave the operating mode unchanged.

参考：`t_indoortemp_detection=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ ∅ | ✗ ∅ | ✗ ∅ | ✗ ∅ | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_indoortemp_detection=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0` | ✗ `t_indoortemp_detection=1`, `t_temp_f=90` | ✗ `t_indoortemp_detection=1`, `t_tms=1` | ✓ `t_indoortemp_detection=1` | ✓ `t_indoortemp_detection=1` |
| H2O Lightning 4B | ✓ `t_indoortemp_detection=1` | ✓ `t_indoortemp_detection=1` | ✓ `t_indoortemp_detection=1` | ✓ `t_indoortemp_detection=1` | ✓ `t_indoortemp_detection=1` |

### N03 防冻制热与主模式区分

> Enable 8-degree frost protection; leave the operating mode unchanged.

参考：`t_8heat=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ ∅ | ✗ ∅ | ✗ ∅ | ✗ `t_temp_f=90` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_outdoor_mute=0`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp_type=1`, `t_tms=0` | ✗ `t_8heat=1`, `t_swing_angle=0`, `t_temp_f=90`, `t_temp_type=1` | ✗ `t_8heat=1`, `t_temp_f=90`, `t_temp_type=1` | ✗ `t_8heat=1`, `t_temp_f=90`, `t_temp_type=1` | ✓ `t_8heat=1` |
| H2O Lightning 4B | ✓ `t_8heat=1` | ✓ `t_8heat=1` | ✗ `t_8heat=1`, `t_temp_type=0` | ✗ `t_8heat=1`, `t_temp_type=0` | ✓ `t_8heat=1` |

### N04 关闭室内静音，保持室外设置

> Stop indoor quiet mode, but leave outdoor quiet unchanged.

参考：`t_fan_mute=0`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ ∅ | ✗ ∅ | ✗ ∅ | ✗ ∅ | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=0`, `t_fan_mute=0`, `t_swing_angle=0`, `t_swing_follow=0` | ✓ `t_fan_mute=0` | ✗ `t_fan_mute=0`, `t_swing_follow=0` | ✓ `t_fan_mute=0` | ✓ `t_fan_mute=0` |
| H2O Lightning 4B | ✓ `t_fan_mute=0` | ✓ `t_fan_mute=0` | ✗ `t_fan_mute=0`, `t_indoortemp_detection=0` | ✗ `t_fan_mute=0`, `t_indoortemp_detection=0` | ✗ `t_fan_mute=0`, `t_indoortemp_detection=0` |

### N05 新表达摄氏温度组合

> Use heating at 25 degrees Celsius with low fan speed.

参考：`t_fan_speed=5`, `t_temp=25`, `t_temp_type=0`, `t_work_mode=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ `t_temp=25` | ✗ `t_dr_offset=25`, `t_fan_speed=5`, `t_temp=25`, `t_work_mode=1` | ✗ `t_temp=25` | ✗ `t_temp=25`, `t_temp_f=90`, `t_temp_type=0` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_dimmer=1`, `t_dr_mode=25`, `t_dr_offset=25`, `t_fan_speed=5`, `t_outdoor_mute=0`, `t_outdoor_selfclean=1`, `t_power=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp=25`, `t_temp_f=77`, `t_temp_type=0`, `t_work_mode=1` | ✗ `t_8heat=1`, `t_dimmer=1`, `t_dr_offset=25`, `t_fan_speed=5`, `t_power=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_temp=25`, `t_temp_f=90`, `t_temp_type=0`, `t_work_mode=1` | ✗ `t_8heat=1`, `t_dr_offset=25`, `t_fan_speed=5`, `t_temp=25`, `t_temp_f=75`, `t_temp_type=0`, `t_work_mode=1` | ✗ `t_8heat=1`, `t_dimmer=1`, `t_dr_mode=25`, `t_dr_offset=25`, `t_fan_speed=5`, `t_temp=25`, `t_temp_f=90`, `t_temp_type=0`, `t_work_mode=1` | ✗ `t_8heat=1`, `t_fan_speed=5`, `t_temp=25`, `t_temp_type=0`, `t_work_mode=1` |
| H2O Lightning 4B | ✓ `t_fan_speed=5`, `t_temp=25`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=5`, `t_temp=25`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=5`, `t_temp=25`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=5`, `t_temp=25`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=5`, `t_temp=25`, `t_temp_type=0`, `t_work_mode=1` |

### N06 新表达华氏温度组合

> Use cooling at 72 degrees Fahrenheit with medium-high fan speed.

参考：`t_fan_speed=8`, `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ `t_fan_speed=8`, `t_temp_f=72`, `t_work_mode=2` | ✗ `t_fan_speed=8`, `t_temp_f=72`, `t_work_mode=2` | ✗ `t_temp_f=72` | ✗ `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_dimmer=1`, `t_dr_mode=72`, `t_fan_speed=8`, `t_outdoor_mute=0`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_swing_follow=0`, `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2` | ✗ `t_8heat=1`, `t_fan_speed=8`, `t_swing_angle=0`, `t_swing_direction=2`, `t_temp=30`, `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2` | ✗ `t_8heat=1`, `t_fan_speed=8`, `t_temp=25`, `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2` | ✗ `t_8heat=1`, `t_fan_speed=8`, `t_temp=31`, `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2` | ✗ `t_fan_speed=8`, `t_temp_f=72` |
| H2O Lightning 4B | ✓ `t_fan_speed=8`, `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2` | ✓ `t_fan_speed=8`, `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2` | ✓ `t_fan_speed=8`, `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2` | ✓ `t_fan_speed=8`, `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2` | ✓ `t_fan_speed=8`, `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2` |

### N07 灯光净化，保持电源

> Switch off the display light and switch on air purification; leave the main power setting unchanged.

参考：`t_dimmer=0`, `t_purify=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ ∅ | ✗ ∅ | ✗ ∅ | ✗ ∅ | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=0`, `t_dimmer=0`, `t_fresh_air=1`, `t_outdoor_mute=0`, `t_outdoor_selfclean=1`, `t_purify=1`, `t_swing_angle=0`, `t_swing_follow=0` | ✗ `t_fresh_air=1`, `t_outdoor_selfclean=1`, `t_purify=1`, `t_swing_angle=0` | ✗ `t_purify=1` | ✗ `t_purify=1` | ✗ `t_purify=1` |
| H2O Lightning 4B | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` |

### N08 新数值需求响应

> Enable demand response with a 7-degree temperature offset and 45 percent load capacity.

参考：`t_dr_mode=45`, `t_dr_offset=7`, `t_dr_onoff=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ ∅ | ✗ `t_8heat=1`, `t_dr_mode=45`, `t_dr_offset=7`, `t_temp=16` | ✗ ∅ | ✗ `t_dr_mode=45`, `t_dr_offset=31`, `t_temp_f=90`, `t_temp_type=0` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_dr_mode=45`, `t_dr_offset=7`, `t_dr_onoff=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_swing_follow=0`, `t_temp=27`, `t_temp_f=77`, `t_temp_type=1` | ✗ `t_8heat=1`, `t_dr_mode=45`, `t_dr_offset=7`, `t_dr_onoff=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_temp=31`, `t_temp_f=90`, `t_temp_type=1` | ✗ `t_8heat=1`, `t_dr_mode=45`, `t_dr_offset=7`, `t_dr_onoff=1`, `t_temp=27`, `t_temp_f=70`, `t_temp_type=1` | ✗ `t_8heat=1`, `t_dr_mode=45`, `t_dr_offset=7`, `t_dr_onoff=1`, `t_temp=31`, `t_temp_f=90`, `t_temp_type=1` | ✗ `t_dr_mode=45`, `t_dr_offset=7` |
| H2O Lightning 4B | ✓ `t_dr_mode=45`, `t_dr_offset=7`, `t_dr_onoff=1` | ✓ `t_dr_mode=45`, `t_dr_offset=7`, `t_dr_onoff=1` | ✗ `t_dr_mode=45`, `t_dr_offset=7`, `t_dr_onoff=1`, `t_temp_type=0` | ✓ `t_dr_mode=45`, `t_dr_offset=7`, `t_dr_onoff=1` | ✓ `t_dr_mode=45`, `t_dr_offset=7`, `t_dr_onoff=1` |

### N09 垂直摆风与水平直吹

> Enable vertical oscillation and point horizontal airflow straight ahead.

参考：`t_swing_direction=0`, `t_up_down=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ ∅ | ✗ `t_swing_direction=0` | ✗ ∅ | ✗ `t_swing_angle=0`, `t_swing_direction=0`, `t_temp_f=90` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_outdoor_mute=0`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_direction=0`, `t_swing_follow=0`, `t_tms=0`, `t_up_down=1` | ✗ `t_swing_angle=0`, `t_swing_direction=0`, `t_temp_f=90`, `t_up_down=1` | ✗ `t_8heat=1`, `t_swing_angle=0`, `t_swing_direction=0`, `t_swing_follow=1`, `t_up_down=1` | ✗ `t_swing_angle=0`, `t_swing_direction=0`, `t_up_down=1` | ✗ `t_swing_angle=0`, `t_swing_direction=0`, `t_up_down=1` |
| H2O Lightning 4B | ✓ `t_swing_direction=0`, `t_up_down=1` | ✗ `t_swing_angle=0`, `t_swing_direction=0`, `t_up_down=1` | ✓ `t_swing_direction=0`, `t_up_down=1` | ✓ `t_swing_direction=0`, `t_up_down=1` | ✓ `t_swing_direction=0`, `t_up_down=1` |

### N10 新风与健康风区分

> Enable fresh air while keeping healthy wind unchanged.

参考：`t_fresh_air=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ ∅ | ✗ `t_outdoor_selfclean=1` | ✗ ∅ | ✗ `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_temp_f=90` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_fresh_air=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0` | ✗ `t_fresh_air=1`, `t_swing_angle=0` | ✗ `t_fresh_air=1`, `t_swing_follow=0` | ✓ `t_fresh_air=1` | ✓ `t_fresh_air=1` |
| H2O Lightning 4B | ✓ `t_fresh_air=1` | ✓ `t_fresh_air=1` | ✓ `t_fresh_air=1` | ✓ `t_fresh_air=1` | ✓ `t_fresh_air=1` |

## 证据与边界

- [冻结计划](plan.json)、[全部请求模板](experiments.json)、[离线参考](references.json)、[指标](ablation_summary.json)、[全部逐条评分](ablation_results.json)。
- 原始HTTP请求/回答：[Decider](decider/formal_receipts.jsonl)、[Liquid](liquid/formal_receipts.jsonl)、[H2O](h2o/formal_receipts.jsonl)。
- [运行前环境](formal_before_environment.json)、[运行后环境](formal_after_environment.json)。
- 既有 GPU 三模型同卡常驻；串行调用，未调整服务、权重、量化或加载状态。Decider/Liquid为BF16，H2O为FP8。模型与部署栈不同，结果代表这些部署配置。
- 基线复用较早记录，可能有时间漂移；同一用例内轮换改写组执行顺序。只有20条规范题、10条针对性诊断题，不支持推断生产总体准确率。两种候选顺序不是40条独立样本；反转两阶段会同时反转门控与值候选，未拆分两者影响。
- 所有数值候选覆盖完整合法整数范围；没有答案导向的缩减。两阶段增加门控上下文与一次可能的HTTP调用，不能把收益单独归因于某个词。
