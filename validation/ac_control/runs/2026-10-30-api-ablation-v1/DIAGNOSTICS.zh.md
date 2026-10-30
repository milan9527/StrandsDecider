# 五模型错误定位与完整请求示例

以下内容由已完成评分的原始观察生成，不发起推理、不修改答案或评分。

## 两阶段门控：原规范20题、原始候选顺序

| 模型 | 选中Key | 其中正确 | 所需Key召回 | 全omit题数 | Key集合正确 | 最终指令正确 |
|---|---:|---:|---:|---:|---:|---:|
| Strands Decider v19 | 0 | 0 | 0/40 | 20/20 | 0/20 | 0/20 |
| Liquid d1-2B | 35 | 32 | 32/40 | 2/20 | 10/20 | 11/20 |
| H2O Lightning 4B | 40 | 40 | 40/40 | 0/20 | 20/20 | 20/20 |
| Jev | 40 | 40 | 40/40 | 0/20 | 20/20 | 20/20 |
| GPT 6.1 Sol · low | 40 | 40 | 40/40 | 0/20 | 20/20 | 20/20 |

门控漏选的Key不能由第二阶段补回；多选的Key仍可在第二阶段选omit。空选择虽然可能对候选换序稳定，但不代表正确。

## Jev / GPT 全部错误观察

每种候选顺序单独列出；原规范与新增诊断题仍分开计分。

| 模型 | 用例 | 顺序 | 方案 | 参考 | 实际 | 状态 |
|---|---|---|---|---|---|---|
| Jev | M08 | original | 原始基线 | `t_swing_direction=2`, `t_up_down=1` | `t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1` | ok |
| Jev | M08 | original | 仅改选项条件 | `t_swing_direction=2`, `t_up_down=1` | `t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1` | ok |
| Jev | M08 | reversed | 原始基线 | `t_swing_direction=2`, `t_up_down=1` | `t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1` | ok |
| Jev | M08 | reversed | 仅改选项条件 | `t_swing_direction=2`, `t_up_down=1` | `t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1` | ok |
| GPT 6.1 Sol · low | M08 | reversed | 仅改选项条件 | `t_swing_direction=2`, `t_up_down=1` | ∅ | capture_error |

`capture_error`表示原始返回未能保存，实际答案未知，表中的∅仅为评分占位。它按失败留在分母，但不能解释为模型输出了空指令。


## M08：上下摆风与水平送风

> Turn on up-and-down swing and set the horizontal airflow to both sides.

参考：`t_swing_direction=2`, `t_up_down=1`

这条Query要求开启上下摆风、水平向两侧送风。`t_up_down=1`已表达上下摆风，按规范不应再发等价的`t_swing_angle=0`。

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ `t_swing_direction=2` | ✗ `t_left_right=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1` | ✗ `t_swing_direction=2` | ✗ `t_swing_angle=0`, `t_swing_direction=2` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_left_right=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_swing_follow=0`, `t_up_down=1` | ✗ `t_left_right=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1` | ✗ `t_left_right=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1` | ✗ `t_left_right=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1` | ✗ `t_left_right=1`, `t_swing_direction=2`, `t_up_down=1` |
| H2O Lightning 4B | ✗ `t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1` | ✗ `t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1` | ✓ `t_swing_direction=2`, `t_up_down=1` | ✗ `t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1` | ✓ `t_swing_direction=2`, `t_up_down=1` |
| Jev | ✗ `t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1` | ✗ `t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1` | ✓ `t_swing_direction=2`, `t_up_down=1` | ✓ `t_swing_direction=2`, `t_up_down=1` | ✓ `t_swing_direction=2`, `t_up_down=1` |
| GPT 6.1 Sol · low | ✓ `t_swing_direction=2`, `t_up_down=1` | ✓ `t_swing_direction=2`, `t_up_down=1` | ✓ `t_swing_direction=2`, `t_up_down=1` | ✓ `t_swing_direction=2`, `t_up_down=1` | ✓ `t_swing_direction=2`, `t_up_down=1` |

- [M08五组完整问题、选项及任务规则](examples/M08.requests.zh.md)：state展开为JSON，保留完整30项能力及全部候选。
- [M08五模型实际指令](examples/M08.actual_outputs.json)。
- [M08 Jev与GPT实际请求和原始回答](examples/M08.api_raw.json)：含GPT完整系统提示、modelId、low参数与SDK返回，以及两阶段实际选中的问题。

## API返回的用量

以下累计有完整记录的正式调用的原生usage字段，预检单独保存。丢失记录的1次调用无法获得usage，未纳入用量合计。两家API字段口径不同，不能直接据此比较价格。GPT命中缓存的输入token单列；延迟来自本轮实际API路径及缓存状态。

| API | 正式调用数 | 原生usage合计 |
|---|---:|---|
| Jev | 300 | `{"input_tokens": 2201873, "output_tokens": 586324}` |
| GPT 6.1 Sol · low | 299 | `{"inputTokens": 598, "outputTokens": 52557, "totalTokens": 1591161, "cacheReadInputTokens": 46433, "cacheWriteInputTokens": 1491573}` |

[五模型完整成绩、耗时及逐题回答](FIVE_MODELS.zh.md)。
