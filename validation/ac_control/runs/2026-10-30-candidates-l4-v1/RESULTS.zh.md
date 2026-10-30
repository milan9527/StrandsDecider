# 独占 L4 候选扩展测试原始结果

规范验收主成绩只计原序 20 题，见[七模型统一对照](../../../../docs/AC_SPEC_UNIFIED_RESULTS.md)。以下 156 次为扩展观察，单独保留。

每模型 156 次质量请求；中文是 24 条英文新题的对应翻译，两种候选顺序分别计分。正确要求整组动作完全匹配，不修复模型答案。

| 模型 | 状态 | 英文 | 中文 | 总计 | 选项换序后选择改变 |
|---|---|---:|---:|---:|---:|
| Perplexity Flash | complete | 47/108 | 17/48 | 64/156 | 54/78 |
| KnowLine Gen5.5 | complete | 91/108 | 46/48 | 137/156 | 3/78 |
| Torchcast | complete | 89/108 | 43/48 | 132/156 | 10/78 |
| Clef-Flash | complete | 90/108 | 36/48 | 126/156 | 0/78 |
| H2O | complete | 98/108 | 46/48 | 144/156 | 0/78 |

Clef 官方编码器会按选项 ID 排序，因此反转传入字典后模型仍看到相同候选顺序；它的 0/78 表示原生接口结果稳定，不能作为权重抵抗候选位置变化的证据。

## 预热后延迟

S03 每模式三轮。时间为收到选择的耗时，不表示答案正确；下面另列封装导致的选择变化。不同指令均值包含原序和反序请求，缓存策略仍保留作者实现。

| 模型 | 单字段均值 ms | 30 步串行均值 s | 串行最小–最大 s | 完整 30 题均值 s | 156 条质量请求均值 s |
|---|---:|---:|---:|---:|---:|
| Perplexity Flash | 346.94 | 10.921 | 10.904–10.930 | 1.551 | 1.513 |
| KnowLine Gen5.5 | 50.42 | 3.035 | 1.612–5.431 | 0.712 | 0.952 |
| Torchcast | 288.39 | 10.818 | 10.733–10.888 | 12.541 | 12.520 |
| Clef-Flash | 535.88 | 14.483 | 14.411–14.556 | 3.297 | 3.295 |
| H2O | 231.35 | 6.361 | 6.348–6.374 | 6.239 | 6.233 |

## Perplexity Flash

正式调用 252，HTTP 预热 33，接口/格式错误 0。

| 数据集 | 原顺序 | 反顺序 |
|---|---:|---:|
| 英文规范 | 1/20 | 7/20 |
| 英文诊断 | 6/10 | 6/10 |
| 英文新增 | 10/24 | 17/24 |
| 中文翻译 | 7/24 | 10/24 |

S03 串行与完整请求的选择比较：

- 第 1 轮：改变字段 ['t_outdoor_selfclean']；串行正确=True，完整正确=False。
- 第 2 轮：改变字段 ['t_outdoor_selfclean']；串行正确=True，完整正确=False。
- 第 3 轮：改变字段 ['t_outdoor_selfclean']；串行正确=True，完整正确=False。

原顺序错误案例：

- S01：多余 [('t_outdoor_selfclean', '0')]；遗漏 无。
- S02：多余 [('t_8heat', '0'), ('t_outdoor_selfclean', '0'), ('t_power', '1')]；遗漏 无。
- S03：多余 [('t_outdoor_selfclean', '0')]；遗漏 无。
- S04：多余 [('t_dr_offset', '0'), ('t_outdoor_selfclean', '0')]；遗漏 无。
- S05：多余 [('t_dr_offset', '0'), ('t_health_fan', '0'), ('t_outdoor_selfclean', '0')]；遗漏 无。
- S06：多余 [('t_health_fan', '0'), ('t_outdoor_selfclean', '0'), ('t_power', '1')]；遗漏 无。
- S08：多余 [('t_health_fan', '0'), ('t_outdoor_selfclean', '0'), ('t_power', '1')]；遗漏 无。
- S09：多余 [('t_8heat', '0'), ('t_dr_offset', '0'), ('t_health_fan', '0'), ('t_indoor_selfclean', '0'), ('t_outdoor_selfclean', '0')]；遗漏 无。
- S10：多余 [('t_health_fan', '0'), ('t_outdoor_selfclean', '0')]；遗漏 无。
- M01：多余 [('t_8heat', '0'), ('t_dr_offset', '0'), ('t_outdoor_selfclean', '0')]；遗漏 无。
- M02：多余 [('t_dr_offset', '0'), ('t_outdoor_selfclean', '0'), ('t_power', '1')]；遗漏 无。
- M03：多余 [('t_8heat', '0'), ('t_dr_offset', '0'), ('t_outdoor_selfclean', '0'), ('t_power', '1')]；遗漏 无。
- M04：多余 [('t_dr_offset', '0'), ('t_health_fan', '0'), ('t_indoor_selfclean', '0'), ('t_outdoor_selfclean', '0')]；遗漏 无。
- M05：多余 [('t_dr_offset', '0')]；遗漏 无。
- M06：多余 [('t_8heat', '0'), ('t_dr_offset', '0'), ('t_outdoor_selfclean', '0'), ('t_power', '1')]；遗漏 无。
- M07：多余 [('t_dr_offset', '0'), ('t_health_fan', '0'), ('t_onekey_selfclean', '1')]；遗漏 无。
- M08：多余 [('t_dr_offset', '0'), ('t_health_fan', '0'), ('t_outdoor_selfclean', '0'), ('t_swing_angle', '0')]；遗漏 无。
- M09：多余 [('t_health_fan', '0'), ('t_outdoor_selfclean', '0')]；遗漏 无。
- M10：多余 [('t_8heat', '0'), ('t_dr_offset', '0'), ('t_health_fan', '0'), ('t_outdoor_selfclean', '0'), ('t_power', '1')]；遗漏 无。
- N05：多余 [('t_dr_offset', '0'), ('t_health_fan', '0'), ('t_indoor_selfclean', '0'), ('t_outdoor_selfclean', '0'), ('t_power', '1')]；遗漏 无。
- N06：多余 [('t_8heat', '0'), ('t_dr_offset', '0'), ('t_health_fan', '0'), ('t_indoor_selfclean', '0'), ('t_onekey_selfclean', '0'), ('t_outdoor_selfclean', '0'), ('t_power', '1')]；遗漏 无。
- N08：多余 [('t_health_fan', '0'), ('t_indoor_selfclean', '0'), ('t_outdoor_selfclean', '0')]；遗漏 无。
- N09：多余 [('t_dr_offset', '0'), ('t_health_fan', '0'), ('t_indoor_selfclean', '0'), ('t_left_right', '0'), ('t_onekey_selfclean', '0'), ('t_outdoor_selfclean', '0'), ('t_swing_angle', '0')]；遗漏 无。
- H03：多余 [('t_dr_offset', '0'), ('t_health_fan', '0'), ('t_outdoor_selfclean', '0')]；遗漏 无。
- H04：多余 [('t_dr_offset', '0'), ('t_health_fan', '0'), ('t_outdoor_selfclean', '0')]；遗漏 无。
- H05：多余 [('t_outdoor_selfclean', '0')]；遗漏 无。
- H06：多余 [('t_dr_offset', '0'), ('t_health_fan', '0'), ('t_outdoor_selfclean', '0')]；遗漏 无。
- H07：多余 [('t_dr_offset', '0'), ('t_health_fan', '0'), ('t_outdoor_selfclean', '0')]；遗漏 无。
- H10：多余 [('t_health_fan', '0'), ('t_outdoor_selfclean', '0')]；遗漏 无。
- H11：多余 [('t_dr_offset', '0')]；遗漏 无。
- H12：多余 [('t_dr_offset', '0'), ('t_health_fan', '0'), ('t_indoor_selfclean', '0')]；遗漏 无。
- H13：多余 [('t_dr_offset', '0'), ('t_outdoor_selfclean', '0')]；遗漏 无。
- H14：多余 [('t_outdoor_selfclean', '0')]；遗漏 无。
- H16：多余 [('t_dr_offset', '0'), ('t_outdoor_selfclean', '0')]；遗漏 无。
- H19：多余 [('t_dr_offset', '0'), ('t_outdoor_selfclean', '0')]；遗漏 无。
- H20：多余 [('t_health_fan', '0'), ('t_outdoor_selfclean', '0')]；遗漏 无。
- H22：多余 [('t_dr_offset', '0')]；遗漏 无。
- Z01：多余 [('t_outdoor_selfclean', '0')]；遗漏 无。
- Z03：多余 [('t_dr_offset', '0'), ('t_outdoor_selfclean', '0')]；遗漏 无。
- Z04：多余 [('t_dr_offset', '0'), ('t_indoor_selfclean', '0'), ('t_outdoor_selfclean', '0')]；遗漏 无。
- Z05：多余 [('t_dr_offset', '0'), ('t_health_fan', '0'), ('t_indoor_selfclean', '0'), ('t_left_right', '0'), ('t_onekey_selfclean', '0'), ('t_outdoor_selfclean', '0'), ('t_power', '1'), ('t_swing_angle', '0'), ('t_swing_direction', '0'), ('t_swing_follow', '0')]；遗漏 无。
- Z06：多余 [('t_dr_offset', '0'), ('t_health_fan', '0'), ('t_left_right', '0'), ('t_outdoor_selfclean', '0'), ('t_swing_angle', '0')]；遗漏 无。
- Z07：多余 [('t_dr_offset', '0'), ('t_health_fan', '0'), ('t_indoor_selfclean', '0'), ('t_onekey_selfclean', '0'), ('t_outdoor_selfclean', '0'), ('t_up_down', '0')]；遗漏 无。
- Z10：多余 [('t_dr_onoff', '1'), ('t_outdoor_selfclean', '0')]；遗漏 无。
- Z11：多余 [('t_dr_offset', '0')]；遗漏 无。
- Z12：多余 [('t_dr_offset', '0')]；遗漏 无。
- Z13：多余 [('t_dr_offset', '0'), ('t_outdoor_selfclean', '0')]；遗漏 无。
- Z14：多余 [('t_outdoor_selfclean', '0')]；遗漏 无。
- Z15：多余 [('t_dr_offset', '0')]；遗漏 无。
- Z16：多余 [('t_dr_offset', '0'), ('t_outdoor_selfclean', '0')]；遗漏 无。
- Z19：多余 [('t_dr_offset', '0'), ('t_outdoor_selfclean', '0')]；遗漏 无。
- Z20：多余 [('t_health_fan', '0'), ('t_indoor_selfclean', '0'), ('t_outdoor_selfclean', '0')]；遗漏 无。
- Z22：多余 [('t_dr_mode', '0'), ('t_dr_offset', '0'), ('t_onekey_selfclean', '0'), ('t_outdoor_selfclean', '0')]；遗漏 无。
- Z23：多余 [('t_outdoor_selfclean', '0')]；遗漏 无。

## KnowLine Gen5.5

正式调用 252，HTTP 预热 33，接口/格式错误 0。

| 数据集 | 原顺序 | 反顺序 |
|---|---:|---:|
| 英文规范 | 18/20 | 19/20 |
| 英文诊断 | 6/10 | 6/10 |
| 英文新增 | 20/24 | 22/24 |
| 中文翻译 | 23/24 | 23/24 |

S03 串行与完整请求的选择比较：

- 第 1 轮：改变字段 无；串行正确=True，完整正确=True。
- 第 2 轮：改变字段 无；串行正确=True，完整正确=True。
- 第 3 轮：改变字段 无；串行正确=True，完整正确=True。

原顺序错误案例：

- S04：多余 [('t_temp', '20')]；遗漏 无。
- M08：多余 [('t_swing_angle', '0')]；遗漏 无。
- N05：多余 [('t_power', '1'), ('t_temp_f', '77')]；遗漏 无。
- N06：多余 [('t_temp', '22')]；遗漏 无。
- N09：多余 [('t_swing_angle', '0')]；遗漏 无。
- N10：多余 [('t_health_fan', '1')]；遗漏 无。
- H05：多余 [('t_swing_angle', '0')]；遗漏 无。
- H08：多余 [('t_health_fan', '1')]；遗漏 无。
- H17：多余 [('t_indoor_selfclean', '1')]；遗漏 无。
- H23：多余 [('t_temp_f', '77')]；遗漏 无。
- Z05：多余 [('t_swing_angle', '0'), ('t_swing_direction', '0')]；遗漏 无。

## Torchcast

正式调用 252，HTTP 预热 33，接口/格式错误 0。

| 数据集 | 原顺序 | 反顺序 |
|---|---:|---:|
| 英文规范 | 18/20 | 16/20 |
| 英文诊断 | 8/10 | 7/10 |
| 英文新增 | 21/24 | 19/24 |
| 中文翻译 | 22/24 | 21/24 |

S03 串行与完整请求的选择比较：

- 第 1 轮：改变字段 无；串行正确=True，完整正确=True。
- 第 2 轮：改变字段 无；串行正确=True，完整正确=True。
- 第 3 轮：改变字段 无；串行正确=True，完整正确=True。

原顺序错误案例：

- M07：多余 [('t_onekey_selfclean', '1')]；遗漏 无。
- M08：多余 [('t_swing_angle', '0')]；遗漏 无。
- N06：多余 [('t_temp', '22')]；遗漏 无。
- N09：多余 [('t_swing_angle', '0')]；遗漏 无。
- H05：多余 [('t_swing_angle', '0')]；遗漏 无。
- H11：多余 [('t_fan_mute', '0')]；遗漏 无。
- H23：多余 [('t_temp_f', '80')]；遗漏 无。
- Z05：多余 [('t_left_right', '0'), ('t_swing_angle', '0'), ('t_swing_direction', '0')]；遗漏 无。
- Z06：多余 [('t_left_right', '0')]；遗漏 无。

## Clef-Flash

正式调用 252，HTTP 预热 33，接口/格式错误 0。

| 数据集 | 原顺序 | 反顺序 |
|---|---:|---:|
| 英文规范 | 19/20 | 19/20 |
| 英文诊断 | 7/10 | 7/10 |
| 英文新增 | 19/24 | 19/24 |
| 中文翻译 | 18/24 | 18/24 |

S03 串行与完整请求的选择比较：

- 第 1 轮：改变字段 无；串行正确=True，完整正确=True。
- 第 2 轮：改变字段 无；串行正确=True，完整正确=True。
- 第 3 轮：改变字段 无；串行正确=True，完整正确=True。

原顺序错误案例：

- M08：多余 [('t_swing_angle', '0')]；遗漏 无。
- N03：多余 [('t_auto_defrost_clean', '1')]；遗漏 无。
- N09：多余 [('t_left_right', '0'), ('t_swing_angle', '0')]；遗漏 无。
- N10：多余 [('t_health_fan', '1')]；遗漏 无。
- H05：多余 [('t_left_right', '0'), ('t_swing_direction', '0')]；遗漏 无。
- H06：多余 [('t_left_right', '0')]；遗漏 无。
- H08：多余 [('t_health_fan', '1')]；遗漏 无。
- H11：多余 [('t_auto_defrost_clean', '0')]；遗漏 无。
- H15：多余 [('t_indoortemp_detection', '1')]；遗漏 无。
- Z05：多余 [('t_swing_angle', '0'), ('t_swing_direction', '3')]；遗漏 无。
- Z08：多余 [('t_health_fan', '1')]；遗漏 无。
- Z10：多余 [('t_dr_onoff', '1')]；遗漏 无。
- Z15：多余 [('t_indoortemp_detection', '1')]；遗漏 无。
- Z17：多余 [('t_indoor_selfclean', '1')]；遗漏 无。
- Z18：多余 [('t_indoor_selfclean', '0'), ('t_outdoor_selfclean', '0')]；遗漏 无。

## H2O

正式调用 252，HTTP 预热 33，接口/格式错误 0。

| 数据集 | 原顺序 | 反顺序 |
|---|---:|---:|
| 英文规范 | 18/20 | 18/20 |
| 英文诊断 | 9/10 | 9/10 |
| 英文新增 | 22/24 | 22/24 |
| 中文翻译 | 23/24 | 23/24 |

S03 串行与完整请求的选择比较：

- 第 1 轮：改变字段 无；串行正确=True，完整正确=True。
- 第 2 轮：改变字段 无；串行正确=True，完整正确=True。
- 第 3 轮：改变字段 无；串行正确=True，完整正确=True。

原顺序错误案例：

- S01：多余 [('t_work_mode', '2')]；遗漏 无。
- M08：多余 [('t_swing_angle', '0')]；遗漏 无。
- N09：多余 [('t_swing_angle', '0')]；遗漏 无。
- H05：多余 [('t_swing_angle', '0')]；遗漏 无。
- H15：多余 [('t_swing_angle', '1')]；遗漏 无。
- Z05：多余 [('t_swing_angle', '0')]；遗漏 无。

完整请求、所有选项和原始回答示例见 [examples](examples/)。全部逐题评分见 [summary.json](summary.json)，原始证据见 [results](results/)。
