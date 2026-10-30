# 空调控制：Decider、Liquid、H2O、Jev、GPT 6.1 Sol low 对照

**采集异常说明：GPT第180条（M08、反转顺序、仅改选项条件）在保存SDK对象时，因bytes字段无法JSON序列化而丢失结果。该条计采集失败，不判定为模型答错；原始顺序20题主结果不受影响，换序该组按19/20计。原记录和故障日志保持不变，只增加二进制字段的无损Base64保存后继续尚未调用的70条，没有重跑丢失题。该条返回状态、答案与耗时未知；完整返回证据覆盖新增500条中的499条。**

Jev 本轮返回版本：`jev-1.14.0`；GPT 使用 Bedrock `us.openai.gpt-6.1-sol`，每次请求显式设置 `reasoning.effort=low`。Jev/GPT各新增250条观察；三个GPU模型复用此前750条已核验观察，不重跑或改写旧证据。

同一组五种方案：原始基线、仅改候选条件、仅改规则与问题、两项合并、先选Key再选Value的两阶段。原规范20题测原始与反转候选顺序，另10条新表达/反例只测原始顺序并单独统计。两阶段的两次请求都含完整30项能力集；第二步的Key只由模型第一步选择决定，仍可选omit。

## 原规范20题：整条指令完全匹配

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---:|---:|---:|---:|---:|
| Strands Decider v19 | 4/20（20.0%） | 1/20（5.0%） | 3/20（15.0%） | 1/20（5.0%） | 0/20（0.0%） |
| Liquid d1-2B | 0/20（0.0%） | 1/20（5.0%） | 6/20（30.0%） | 4/20（20.0%） | 11/20（55.0%） |
| H2O Lightning 4B | 18/20（90.0%） | 18/20（90.0%） | 19/20（95.0%） | 18/20（90.0%） | 20/20（100.0%） |
| Jev | 19/20（95.0%） | 19/20（95.0%） | 20/20（100.0%） | 20/20（100.0%） | 20/20（100.0%） |
| GPT 6.1 Sol · low | 20/20（100.0%） | 20/20（100.0%） | 20/20（100.0%） | 20/20（100.0%） | 20/20（100.0%） |

表中为原始候选顺序的主结果。完整cmdKey/cmdValue集合必须与参考相同；任何多余、缺失、错值、调用、格式或采集错误都计为失败。模型输出不补温标、不删多余指令。

## 新表达与反例：另计10题

此诊断集在较早三模型对照前已经冻结，沿用原答案；根据旧基线错误设计，不是独立盲测集，不与20题主结果混合为一个准确率。

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---:|---:|---:|---:|---:|
| Strands Decider v19 | 0/10（0.0%） | 0/10（0.0%） | 0/10（0.0%） | 0/10（0.0%） | 0/10（0.0%） |
| Liquid d1-2B | 0/10（0.0%） | 1/10（10.0%） | 1/10（10.0%） | 4/10（40.0%） | 5/10（50.0%） |
| H2O Lightning 4B | 10/10（100.0%） | 9/10（90.0%） | 7/10（70.0%） | 8/10（80.0%） | 9/10（90.0%） |
| Jev | 10/10（100.0%） | 10/10（100.0%） | 10/10（100.0%） | 10/10（100.0%） | 10/10（100.0%） |
| GPT 6.1 Sol · low | 10/10（100.0%） | 10/10（100.0%） | 10/10（100.0%） | 10/10（100.0%） | 10/10（100.0%） |

## 候选顺序与错误类型（原规范）

| 模型 | 组别 | 原始顺序 | 反转顺序 | 输出改变 | 原始多余对 | 原始缺失对 | 调用/格式/采集失败（两顺序） |
|---|---|---:|---:|---:|---:|---:|---:|
| Strands Decider v19 | 原始基线 | 4/20（20.0%） | 2/20（10.0%） | 18/20 | 1 | 21 | 0 |
| Strands Decider v19 | 仅改选项条件 | 1/20（5.0%） | 0/20（0.0%） | 20/20 | 38 | 12 | 0 |
| Strands Decider v19 | 仅改规则与问题 | 3/20（15.0%） | 3/20（15.0%） | 8/20 | 1 | 32 | 0 |
| Strands Decider v19 | 两项合并 | 1/20（5.0%） | 0/20（0.0%） | 20/20 | 44 | 15 | 0 |
| Strands Decider v19 | 两阶段 | 0/20（0.0%） | 0/20（0.0%） | 0/20 | 0 | 40 | 0 |
| Liquid d1-2B | 原始基线 | 0/20（0.0%） | 0/20（0.0%） | 18/20 | 105 | 0 | 0 |
| Liquid d1-2B | 仅改选项条件 | 1/20（5.0%） | 2/20（10.0%） | 17/20 | 65 | 1 | 0 |
| Liquid d1-2B | 仅改规则与问题 | 6/20（30.0%） | 3/20（15.0%） | 14/20 | 25 | 2 | 0 |
| Liquid d1-2B | 两项合并 | 4/20（20.0%） | 5/20（25.0%） | 11/20 | 36 | 1 | 0 |
| Liquid d1-2B | 两阶段 | 11/20（55.0%） | 11/20（55.0%） | 5/20 | 2 | 8 | 0 |
| H2O Lightning 4B | 原始基线 | 18/20（90.0%） | 18/20（90.0%） | 0/20 | 2 | 0 | 0 |
| H2O Lightning 4B | 仅改选项条件 | 18/20（90.0%） | 18/20（90.0%） | 0/20 | 2 | 0 | 0 |
| H2O Lightning 4B | 仅改规则与问题 | 19/20（95.0%） | 19/20（95.0%） | 0/20 | 1 | 0 | 0 |
| H2O Lightning 4B | 两项合并 | 18/20（90.0%） | 18/20（90.0%） | 0/20 | 2 | 0 | 0 |
| H2O Lightning 4B | 两阶段 | 20/20（100.0%） | 20/20（100.0%） | 0/20 | 0 | 0 | 0 |
| Jev | 原始基线 | 19/20（95.0%） | 19/20（95.0%） | 0/20 | 1 | 0 | 0 |
| Jev | 仅改选项条件 | 19/20（95.0%） | 19/20（95.0%） | 0/20 | 1 | 0 | 0 |
| Jev | 仅改规则与问题 | 20/20（100.0%） | 20/20（100.0%） | 0/20 | 0 | 0 | 0 |
| Jev | 两项合并 | 20/20（100.0%） | 20/20（100.0%） | 0/20 | 0 | 0 | 0 |
| Jev | 两阶段 | 20/20（100.0%） | 20/20（100.0%） | 0/20 | 0 | 0 | 0 |
| GPT 6.1 Sol · low | 原始基线 | 20/20（100.0%） | 20/20（100.0%） | 0/20 | 0 | 0 | 0 |
| GPT 6.1 Sol · low | 仅改选项条件 | 20/20（100.0%） | 19/20（95.0%） | 0/19 | 0 | 0 | 1 |
| GPT 6.1 Sol · low | 仅改规则与问题 | 20/20（100.0%） | 20/20（100.0%） | 0/20 | 0 | 0 | 0 |
| GPT 6.1 Sol · low | 两项合并 | 20/20（100.0%） | 20/20（100.0%） | 0/20 | 0 | 0 | 0 |
| GPT 6.1 Sol · low | 两阶段 | 20/20（100.0%） | 20/20（100.0%） | 0/20 | 0 | 0 | 0 |

两种顺序重复同20题，不是40个独立样本；API模型的换序差异还可能包含生成或服务波动。

## 耗时与调用状态（原规范原始顺序）

| 模型 | 组别 | 服务端均值 ms | 服务端P95 ms | 客户端均值 ms | 实际调用数 | 格式/调用/采集失败 |
|---|---|---:|---:|---:|---:|---:|
| Strands Decider v19 | 原始基线 | 2906.9 | 2956.4 | 2919.9 | 20 | 0 |
| Strands Decider v19 | 仅改选项条件 | 3075.0 | 3129.8 | 3076.9 | 20 | 0 |
| Strands Decider v19 | 仅改规则与问题 | 3355.3 | 3406.9 | 3357.2 | 20 | 0 |
| Strands Decider v19 | 两项合并 | 3474.0 | 3514.4 | 3476.0 | 20 | 0 |
| Strands Decider v19 | 两阶段 | 3189.5 | 3237.8 | 3191.1 | 20 | 0 |
| Liquid d1-2B | 原始基线 | 608.7 | 612.5 | 610.7 | 20 | 0 |
| Liquid d1-2B | 仅改选项条件 | 826.6 | 831.3 | 828.7 | 20 | 0 |
| Liquid d1-2B | 仅改规则与问题 | 722.9 | 726.0 | 725.0 | 20 | 0 |
| Liquid d1-2B | 两项合并 | 905.2 | 908.9 | 907.2 | 20 | 0 |
| Liquid d1-2B | 两阶段 | 741.1 | 791.5 | 743.4 | 38 | 0 |
| H2O Lightning 4B | 原始基线 | 5962.1 | 6048.7 | 5963.9 | 20 | 0 |
| H2O Lightning 4B | 仅改选项条件 | 6318.1 | 6393.3 | 6320.0 | 20 | 0 |
| H2O Lightning 4B | 仅改规则与问题 | 6989.7 | 7030.6 | 6991.6 | 20 | 0 |
| H2O Lightning 4B | 两项合并 | 7254.6 | 7289.7 | 7256.5 | 20 | 0 |
| H2O Lightning 4B | 两阶段 | 7099.7 | 7612.2 | 7102.2 | 40 | 0 |
| Jev | 原始基线 | 未提供 | 未提供 | 85.7 | 20 | 0 |
| Jev | 仅改选项条件 | 未提供 | 未提供 | 103.7 | 20 | 0 |
| Jev | 仅改规则与问题 | 未提供 | 未提供 | 106.4 | 20 | 0 |
| Jev | 两项合并 | 未提供 | 未提供 | 116.0 | 20 | 0 |
| Jev | 两阶段 | 未提供 | 未提供 | 132.6 | 40 | 0 |
| GPT 6.1 Sol · low | 原始基线 | 3031.0 | 3589.0 | 3040.5 | 20 | 0 |
| GPT 6.1 Sol · low | 仅改选项条件 | 3222.6 | 4327.0 | 3233.0 | 20 | 0 |
| GPT 6.1 Sol · low | 仅改规则与问题 | 3268.9 | 4174.0 | 3278.9 | 20 | 0 |
| GPT 6.1 Sol · low | 两项合并 | 3354.8 | 4315.0 | 3364.1 | 20 | 0 |
| GPT 6.1 Sol · low | 两阶段 | 4527.4 | 5495.0 | 4547.6 | 40 | 0 |

两阶段累加实际发生的两次调用。Jev为HTTPS服务，GPT为Bedrock Converse；GPU模型主要走本机loopback，旧Decider基线走HTTPS。各服务计时边界与处理方式不同，不能直接当作纯GPU或模型计算速度比较。Jev没有返回latency_ms时仅展示实测客户端耗时，不伪造服务端时间。

## 传输与输出契约

- 业务payload逐字节复用冻结模板，包括Query、完整30项Command Set、各问题说明、候选ID、描述和顺序。数值字段覆盖全部合法整数，不按答案筛选候选。
- Jev直接调用原生 `/v1/systemone`，附加固定 `model=jev-latest`；正式响应版本必须与预检一致。既有应用转发层的16问/24候选限制不适用于原生调用，未修改应用服务。
- GPT通过现有Bedrock模型配置调用；控制面确认该推理配置映射到GPT 6.1 Sol。Converse响应不回显模型ID，身份依据实际请求modelId与保存的ACTIVE推理配置。low参数保存在每次实际请求中。[OpenAI官方模型说明](https://developers.openai.com/api/docs/models/gpt-6.1-sol)确认支持low。
- GPT增加固定、无空调知识的JSON格式说明，要求回答每个Question ID并返回字符串Candidate ID。同时明确读取state内的任务规则。它一次生成全部答案，其他模型使用原生选择接口；业务输入一致，内部模板与推理机制并不相同。
- GPT本轮未启用约束式JSON解码；严格核验完整题目集合和候选ID，只允许去除最外层JSON代码围栏。不修补缺失回答、不把数字转换成字符串、不纠正业务结果。maxTokens=8192为输出上限，effort始终low，不代表实际使用8192个token。
- 每模型单客户端串行，Jev与GPT可同时运行于独立API。无自动重试、无答案补齐；预检独立保存，不进入正式成绩。

本轮新增API观察：500；实际API调用：600。五模型共1250条观察，含复用的750条GPU历史观察。没有向真实空调下发控制。

## 全部问题与实际回答（原始顺序）

### S01 开机

> Turn on the air conditioner.

参考：`t_power=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ ∅ | ✗ `t_fresh_air=1`, `t_outdoor_selfclean=1`, `t_sleep=1`, `t_temp_f=90`, `t_work_mode=2` | ✗ ∅ | ✗ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1`, `t_temp_f=90` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_outdoor_selfclean=1`, `t_power=1`, `t_swing_angle=0`, `t_swing_follow=0` | ✗ `t_8heat=1`, `t_power=1`, `t_temp_f=90` | ✗ `t_8heat=1`, `t_power=1` | ✓ `t_power=1` | ✓ `t_power=1` |
| H2O Lightning 4B | ✗ `t_power=1`, `t_work_mode=2` | ✗ `t_power=1`, `t_work_mode=2` | ✗ `t_power=1`, `t_work_mode=2` | ✗ `t_power=1`, `t_work_mode=2` | ✓ `t_power=1` |
| Jev | ✓ `t_power=1` | ✓ `t_power=1` | ✓ `t_power=1` | ✓ `t_power=1` | ✓ `t_power=1` |
| GPT 6.1 Sol · low | ✓ `t_power=1` | ✓ `t_power=1` | ✓ `t_power=1` | ✓ `t_power=1` | ✓ `t_power=1` |

### S02 选择制冷模式

> Set the air conditioner to cooling mode.

参考：`t_work_mode=2`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ `t_temp_f=90`, `t_work_mode=2` | ✗ `t_dr_mode=100`, `t_outdoor_selfclean=1`, `t_sleep=1`, `t_temp_f=90`, `t_work_mode=2` | ✗ `t_temp_f=90` | ✗ `t_outdoor_selfclean=1`, `t_temp_f=90`, `t_temp_type=0`, `t_work_mode=2` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_outdoor_selfclean=1`, `t_power=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_work_mode=2` | ✗ `t_temp_f=90`, `t_work_mode=2` | ✓ `t_work_mode=2` | ✓ `t_work_mode=2` | ✗ ∅ |
| H2O Lightning 4B | ✓ `t_work_mode=2` | ✓ `t_work_mode=2` | ✓ `t_work_mode=2` | ✓ `t_work_mode=2` | ✓ `t_work_mode=2` |
| Jev | ✓ `t_work_mode=2` | ✓ `t_work_mode=2` | ✓ `t_work_mode=2` | ✓ `t_work_mode=2` | ✓ `t_work_mode=2` |
| GPT 6.1 Sol · low | ✓ `t_work_mode=2` | ✓ `t_work_mode=2` | ✓ `t_work_mode=2` | ✓ `t_work_mode=2` | ✓ `t_work_mode=2` |

### S03 设置摄氏温度

> Set the air conditioner temperature to 24 degrees Celsius.

参考：`t_temp=24`, `t_temp_type=0`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ `t_temp=24` | ✗ `t_dr_offset=24`, `t_temp=24`, `t_work_mode=2` | ✗ `t_temp=24` | ✗ `t_temp=24`, `t_temp_f=90`, `t_temp_type=0` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp=24`, `t_temp_f=80`, `t_temp_type=0` | ✗ `t_8heat=1`, `t_swing_angle=0`, `t_temp=24`, `t_temp_f=90`, `t_temp_type=0` | ✗ `t_8heat=1`, `t_temp=24`, `t_temp_f=80`, `t_temp_type=0` | ✗ `t_dr_offset=24`, `t_temp=24`, `t_temp_f=90`, `t_temp_type=0` | ✓ `t_temp=24`, `t_temp_type=0` |
| H2O Lightning 4B | ✓ `t_temp=24`, `t_temp_type=0` | ✓ `t_temp=24`, `t_temp_type=0` | ✓ `t_temp=24`, `t_temp_type=0` | ✓ `t_temp=24`, `t_temp_type=0` | ✓ `t_temp=24`, `t_temp_type=0` |
| Jev | ✓ `t_temp=24`, `t_temp_type=0` | ✓ `t_temp=24`, `t_temp_type=0` | ✓ `t_temp=24`, `t_temp_type=0` | ✓ `t_temp=24`, `t_temp_type=0` | ✓ `t_temp=24`, `t_temp_type=0` |
| GPT 6.1 Sol · low | ✓ `t_temp=24`, `t_temp_type=0` | ✓ `t_temp=24`, `t_temp_type=0` | ✓ `t_temp=24`, `t_temp_type=0` | ✓ `t_temp=24`, `t_temp_type=0` | ✓ `t_temp=24`, `t_temp_type=0` |

### S04 设置华氏温度

> Set the air conditioner temperature to 68 degrees Fahrenheit.

参考：`t_temp_f=68`, `t_temp_type=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ `t_temp_f=68` | ✗ `t_temp_f=68`, `t_work_mode=2` | ✗ `t_temp_f=68` | ✓ `t_temp_f=68`, `t_temp_type=1` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp_f=68`, `t_temp_type=1` | ✗ `t_8heat=1`, `t_swing_angle=0`, `t_temp_f=68`, `t_temp_type=1` | ✗ `t_8heat=1`, `t_temp=28`, `t_temp_f=68`, `t_temp_type=1` | ✗ `t_temp=30`, `t_temp_f=68`, `t_temp_type=1` | ✗ `t_temp_f=68` |
| H2O Lightning 4B | ✓ `t_temp_f=68`, `t_temp_type=1` | ✓ `t_temp_f=68`, `t_temp_type=1` | ✓ `t_temp_f=68`, `t_temp_type=1` | ✓ `t_temp_f=68`, `t_temp_type=1` | ✓ `t_temp_f=68`, `t_temp_type=1` |
| Jev | ✓ `t_temp_f=68`, `t_temp_type=1` | ✓ `t_temp_f=68`, `t_temp_type=1` | ✓ `t_temp_f=68`, `t_temp_type=1` | ✓ `t_temp_f=68`, `t_temp_type=1` | ✓ `t_temp_f=68`, `t_temp_type=1` |
| GPT 6.1 Sol · low | ✓ `t_temp_f=68`, `t_temp_type=1` | ✓ `t_temp_f=68`, `t_temp_type=1` | ✓ `t_temp_f=68`, `t_temp_type=1` | ✓ `t_temp_f=68`, `t_temp_type=1` | ✓ `t_temp_f=68`, `t_temp_type=1` |

### S05 选择高风速

> Set the air conditioner fan speed to high.

参考：`t_fan_speed=9`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✓ `t_fan_speed=9` | ✗ `t_fan_speed=9`, `t_outdoor_selfclean=1`, `t_work_mode=0` | ✓ `t_fan_speed=9` | ✗ `t_fan_speed=9`, `t_indoor_selfclean=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_temp_f=90`, `t_temp_type=0` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_dimmer=1`, `t_fan_speed=9`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0` | ✗ `t_dimmer=1`, `t_fan_speed=9`, `t_swing_angle=0`, `t_temp_f=90` | ✗ `t_dimmer=1`, `t_fan_speed=9` | ✗ `t_dimmer=1`, `t_fan_speed=9`, `t_temp_f=90`, `t_work_mode=0` | ✓ `t_fan_speed=9` |
| H2O Lightning 4B | ✓ `t_fan_speed=9` | ✓ `t_fan_speed=9` | ✓ `t_fan_speed=9` | ✓ `t_fan_speed=9` | ✓ `t_fan_speed=9` |
| Jev | ✓ `t_fan_speed=9` | ✓ `t_fan_speed=9` | ✓ `t_fan_speed=9` | ✓ `t_fan_speed=9` | ✓ `t_fan_speed=9` |
| GPT 6.1 Sol · low | ✓ `t_fan_speed=9` | ✓ `t_fan_speed=9` | ✓ `t_fan_speed=9` | ✓ `t_fan_speed=9` | ✓ `t_fan_speed=9` |

### S06 开启室内机静音

> Turn on quiet mode for the indoor unit.

参考：`t_fan_mute=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ ∅ | ✗ `t_indoor_selfclean=1`, `t_sleep=1` | ✗ ∅ | ✗ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1`, `t_temp_f=90` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_fan_mute=1`, `t_outdoor_mute=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_swing_follow=0` | ✗ `t_8heat=1`, `t_fan_mute=1`, `t_outdoor_mute=1`, `t_swing_angle=0`, `t_swing_direction=2` | ✓ `t_fan_mute=1` | ✓ `t_fan_mute=1` | ✓ `t_fan_mute=1` |
| H2O Lightning 4B | ✓ `t_fan_mute=1` | ✓ `t_fan_mute=1` | ✓ `t_fan_mute=1` | ✓ `t_fan_mute=1` | ✓ `t_fan_mute=1` |
| Jev | ✓ `t_fan_mute=1` | ✓ `t_fan_mute=1` | ✓ `t_fan_mute=1` | ✓ `t_fan_mute=1` | ✓ `t_fan_mute=1` |
| GPT 6.1 Sol · low | ✓ `t_fan_mute=1` | ✓ `t_fan_mute=1` | ✓ `t_fan_mute=1` | ✓ `t_fan_mute=1` | ✓ `t_fan_mute=1` |

### S07 开启室外机静音

> Turn on outdoor quiet mode.

参考：`t_outdoor_mute=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✓ `t_outdoor_mute=1` | ✗ `t_fan_mute=1`, `t_outdoor_mute=1`, `t_outdoor_selfclean=1` | ✗ ∅ | ✗ `t_outdoor_mute=1`, `t_outdoor_selfclean=1`, `t_temp_f=90` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_fan_mute=1`, `t_outdoor_mute=1`, `t_swing_angle=0`, `t_swing_follow=0` | ✗ `t_8heat=1`, `t_fan_mute=1`, `t_outdoor_mute=1`, `t_swing_angle=0`, `t_swing_direction=2` | ✗ `t_fan_mute=1`, `t_outdoor_mute=1` | ✗ `t_fan_mute=1`, `t_outdoor_mute=1` | ✗ `t_fan_mute=1`, `t_outdoor_mute=1` |
| H2O Lightning 4B | ✓ `t_outdoor_mute=1` | ✓ `t_outdoor_mute=1` | ✓ `t_outdoor_mute=1` | ✓ `t_outdoor_mute=1` | ✓ `t_outdoor_mute=1` |
| Jev | ✓ `t_outdoor_mute=1` | ✓ `t_outdoor_mute=1` | ✓ `t_outdoor_mute=1` | ✓ `t_outdoor_mute=1` | ✓ `t_outdoor_mute=1` |
| GPT 6.1 Sol · low | ✓ `t_outdoor_mute=1` | ✓ `t_outdoor_mute=1` | ✓ `t_outdoor_mute=1` | ✓ `t_outdoor_mute=1` | ✓ `t_outdoor_mute=1` |

### S08 开启空气净化

> Turn on air purification.

参考：`t_purify=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✓ `t_purify=1` | ✗ `t_fresh_air=1`, `t_indoor_selfclean=1`, `t_onekey_selfclean=1`, `t_outdoor_selfclean=1`, `t_purify=1` | ✓ `t_purify=1` | ✗ `t_indoor_selfclean=1`, `t_onekey_selfclean=1`, `t_outdoor_selfclean=1`, `t_purify=1`, `t_temp_f=90` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_outdoor_selfclean=1`, `t_purify=1`, `t_swing_angle=0`, `t_swing_follow=0` | ✗ `t_8heat=1`, `t_power=1`, `t_purify=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_temp_f=90` | ✓ `t_purify=1` | ✓ `t_purify=1` | ✓ `t_purify=1` |
| H2O Lightning 4B | ✓ `t_purify=1` | ✓ `t_purify=1` | ✓ `t_purify=1` | ✓ `t_purify=1` | ✓ `t_purify=1` |
| Jev | ✓ `t_purify=1` | ✓ `t_purify=1` | ✓ `t_purify=1` | ✓ `t_purify=1` | ✓ `t_purify=1` |
| GPT 6.1 Sol · low | ✓ `t_purify=1` | ✓ `t_purify=1` | ✓ `t_purify=1` | ✓ `t_purify=1` | ✓ `t_purify=1` |

### S09 关闭 LED 显示屏

> Turn off the air conditioner display light.

参考：`t_dimmer=0`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ ∅ | ✗ `t_power=0` | ✗ ∅ | ✗ `t_temp_f=90` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=0`, `t_dimmer=0`, `t_dr_mode=0`, `t_fan_mute=0`, `t_outdoor_mute=0`, `t_outdoor_selfclean=1`, `t_power=0`, `t_swing_angle=0`, `t_swing_follow=0`, `t_tms=0` | ✗ `t_dr_onoff=0`, `t_power=0`, `t_swing_direction=2` | ✗ `t_8heat=0`, `t_swing_follow=0` | ✗ ∅ | ✗ ∅ |
| H2O Lightning 4B | ✓ `t_dimmer=0` | ✓ `t_dimmer=0` | ✓ `t_dimmer=0` | ✓ `t_dimmer=0` | ✓ `t_dimmer=0` |
| Jev | ✓ `t_dimmer=0` | ✓ `t_dimmer=0` | ✓ `t_dimmer=0` | ✓ `t_dimmer=0` | ✓ `t_dimmer=0` |
| GPT 6.1 Sol · low | ✓ `t_dimmer=0` | ✓ `t_dimmer=0` | ✓ `t_dimmer=0` | ✓ `t_dimmer=0` | ✓ `t_dimmer=0` |

### S10 选择两侧水平送风

> Set the horizontal airflow to both sides.

参考：`t_swing_direction=2`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✓ `t_swing_direction=2` | ✓ `t_swing_direction=2` | ✓ `t_swing_direction=2` | ✗ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_temp_f=90` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_outdoor_mute=0`, `t_outdoor_selfclean=1`, `t_swing_angle=3`, `t_swing_direction=2`, `t_swing_follow=0` | ✓ `t_swing_direction=2` | ✓ `t_swing_direction=2` | ✗ `t_left_right=1`, `t_swing_direction=2` | ✓ `t_swing_direction=2` |
| H2O Lightning 4B | ✓ `t_swing_direction=2` | ✓ `t_swing_direction=2` | ✓ `t_swing_direction=2` | ✓ `t_swing_direction=2` | ✓ `t_swing_direction=2` |
| Jev | ✓ `t_swing_direction=2` | ✓ `t_swing_direction=2` | ✓ `t_swing_direction=2` | ✓ `t_swing_direction=2` | ✓ `t_swing_direction=2` |
| GPT 6.1 Sol · low | ✓ `t_swing_direction=2` | ✓ `t_swing_direction=2` | ✓ `t_swing_direction=2` | ✓ `t_swing_direction=2` | ✓ `t_swing_direction=2` |

### M01 电源、模式与摄氏温度

> Turn on the air conditioner, switch it to cooling mode, and set the temperature to 24 degrees Celsius.

参考：`t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ `t_temp=24`, `t_work_mode=2` | ✗ `t_dr_offset=24`, `t_temp=24`, `t_work_mode=2` | ✗ ∅ | ✗ `t_temp=24`, `t_temp_f=90`, `t_temp_type=0`, `t_work_mode=2` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=0`, `t_dr_offset=24`, `t_dr_onoff=1`, `t_outdoor_selfclean=1`, `t_power=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp=24`, `t_temp_f=80`, `t_temp_type=0`, `t_work_mode=2` | ✗ `t_dr_onoff=1`, `t_power=1`, `t_swing_angle=0`, `t_temp=24`, `t_temp_f=90`, `t_temp_type=0`, `t_work_mode=2` | ✗ `t_8heat=1`, `t_power=1`, `t_temp=24`, `t_temp_f=80`, `t_temp_type=0`, `t_work_mode=2` | ✗ `t_8heat=1`, `t_dr_offset=24`, `t_dr_onoff=1`, `t_power=1`, `t_temp=24`, `t_temp_f=90`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2` |
| H2O Lightning 4B | ✓ `t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2` |
| Jev | ✓ `t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2` |
| GPT 6.1 Sol · low | ✓ `t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_power=1`, `t_temp=24`, `t_temp_type=0`, `t_work_mode=2` |

### M02 制热模式、温度与风速

> Switch the air conditioner to heating mode, set it to 26 degrees Celsius, and use medium fan speed.

参考：`t_fan_speed=7`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ `t_fan_speed=7`, `t_temp=26`, `t_work_mode=1` | ✗ `t_dr_offset=26`, `t_temp=26`, `t_work_mode=1` | ✗ `t_temp=26` | ✗ `t_temp=26`, `t_temp_f=90`, `t_temp_type=0`, `t_work_mode=1` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_dimmer=1`, `t_dr_offset=26`, `t_fan_speed=7`, `t_outdoor_selfclean=1`, `t_power=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp=26`, `t_temp_f=76`, `t_temp_type=0`, `t_work_mode=1` | ✗ `t_8heat=1`, `t_dimmer=1`, `t_dr_offset=26`, `t_dr_onoff=1`, `t_fan_speed=7`, `t_power=1`, `t_swing_angle=0`, `t_temp=26`, `t_temp_f=90`, `t_temp_type=0`, `t_work_mode=1` | ✗ `t_8heat=1`, `t_dr_offset=30`, `t_fan_speed=7`, `t_temp=26`, `t_temp_f=70`, `t_temp_type=0`, `t_work_mode=1` | ✗ `t_8heat=1`, `t_dimmer=1`, `t_dr_mode=26`, `t_dr_offset=26`, `t_dr_onoff=1`, `t_fan_speed=7`, `t_temp=26`, `t_temp_f=90`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=7`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1` |
| H2O Lightning 4B | ✓ `t_fan_speed=7`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=7`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=7`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=7`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=7`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1` |
| Jev | ✓ `t_fan_speed=7`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=7`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=7`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=7`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=7`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1` |
| GPT 6.1 Sol · low | ✓ `t_fan_speed=7`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=7`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=7`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=7`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=7`, `t_temp=26`, `t_temp_type=0`, `t_work_mode=1` |

### M03 制冷模式、高风速与节能

> Set cooling mode, change the fan speed to high, and turn on energy saving.

参考：`t_eco=1`, `t_fan_speed=9`, `t_work_mode=2`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ `t_fan_speed=9`, `t_work_mode=2` | ✗ `t_eco=1`, `t_fan_speed=9`, `t_outdoor_selfclean=1`, `t_work_mode=2` | ✗ ∅ | ✗ `t_outdoor_selfclean=1`, `t_temp_f=90` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_dimmer=1`, `t_eco=1`, `t_fan_speed=9`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_work_mode=2` | ✗ `t_dimmer=1`, `t_eco=1`, `t_fan_speed=9`, `t_swing_angle=0`, `t_temp_f=90`, `t_work_mode=2` | ✓ `t_eco=1`, `t_fan_speed=9`, `t_work_mode=2` | ✗ `t_dimmer=1`, `t_eco=1`, `t_fan_mute=1`, `t_fan_speed=9`, `t_super=1`, `t_work_mode=2` | ✗ `t_eco=1`, `t_fan_speed=9` |
| H2O Lightning 4B | ✓ `t_eco=1`, `t_fan_speed=9`, `t_work_mode=2` | ✓ `t_eco=1`, `t_fan_speed=9`, `t_work_mode=2` | ✓ `t_eco=1`, `t_fan_speed=9`, `t_work_mode=2` | ✓ `t_eco=1`, `t_fan_speed=9`, `t_work_mode=2` | ✓ `t_eco=1`, `t_fan_speed=9`, `t_work_mode=2` |
| Jev | ✓ `t_eco=1`, `t_fan_speed=9`, `t_work_mode=2` | ✓ `t_eco=1`, `t_fan_speed=9`, `t_work_mode=2` | ✓ `t_eco=1`, `t_fan_speed=9`, `t_work_mode=2` | ✓ `t_eco=1`, `t_fan_speed=9`, `t_work_mode=2` | ✓ `t_eco=1`, `t_fan_speed=9`, `t_work_mode=2` |
| GPT 6.1 Sol · low | ✓ `t_eco=1`, `t_fan_speed=9`, `t_work_mode=2` | ✓ `t_eco=1`, `t_fan_speed=9`, `t_work_mode=2` | ✓ `t_eco=1`, `t_fan_speed=9`, `t_work_mode=2` | ✓ `t_eco=1`, `t_fan_speed=9`, `t_work_mode=2` | ✓ `t_eco=1`, `t_fan_speed=9`, `t_work_mode=2` |

### M04 室内与室外静音

> Turn on both indoor quiet mode and outdoor quiet mode.

参考：`t_fan_mute=1`, `t_outdoor_mute=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ `t_outdoor_mute=1` | ✗ `t_fan_mute=1`, `t_outdoor_mute=1`, `t_outdoor_selfclean=1`, `t_swing_direction=2` | ✗ ∅ | ✗ `t_indoor_selfclean=1`, `t_outdoor_mute=1`, `t_outdoor_selfclean=1`, `t_temp_f=90` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_fan_mute=1`, `t_indoor_selfclean=1`, `t_onekey_selfclean=1`, `t_outdoor_mute=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_swing_follow=0` | ✗ `t_fan_mute=1`, `t_outdoor_mute=1`, `t_swing_angle=0`, `t_swing_direction=2` | ✓ `t_fan_mute=1`, `t_outdoor_mute=1` | ✗ `t_fan_mute=1`, `t_outdoor_mute=1`, `t_outdoor_selfclean=1` | ✓ `t_fan_mute=1`, `t_outdoor_mute=1` |
| H2O Lightning 4B | ✓ `t_fan_mute=1`, `t_outdoor_mute=1` | ✓ `t_fan_mute=1`, `t_outdoor_mute=1` | ✓ `t_fan_mute=1`, `t_outdoor_mute=1` | ✓ `t_fan_mute=1`, `t_outdoor_mute=1` | ✓ `t_fan_mute=1`, `t_outdoor_mute=1` |
| Jev | ✓ `t_fan_mute=1`, `t_outdoor_mute=1` | ✓ `t_fan_mute=1`, `t_outdoor_mute=1` | ✓ `t_fan_mute=1`, `t_outdoor_mute=1` | ✓ `t_fan_mute=1`, `t_outdoor_mute=1` | ✓ `t_fan_mute=1`, `t_outdoor_mute=1` |
| GPT 6.1 Sol · low | ✓ `t_fan_mute=1`, `t_outdoor_mute=1` | ✓ `t_fan_mute=1`, `t_outdoor_mute=1` | ✓ `t_fan_mute=1`, `t_outdoor_mute=1` | ✓ `t_fan_mute=1`, `t_outdoor_mute=1` | ✓ `t_fan_mute=1`, `t_outdoor_mute=1` |

### M05 空气净化与显示屏

> Turn on air purification and turn off the display light.

参考：`t_dimmer=0`, `t_purify=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ ∅ | ✗ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1`, `t_purify=1` | ✗ ∅ | ✗ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1`, `t_purify=1`, `t_temp_f=90` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=0`, `t_dimmer=0`, `t_dr_onoff=0`, `t_fan_mute=0`, `t_outdoor_mute=0`, `t_outdoor_selfclean=1`, `t_purify=1`, `t_swing_angle=0`, `t_swing_follow=0` | ✗ `t_dimmer=0`, `t_dr_onoff=0`, `t_fan_mute=0`, `t_outdoor_mute=0`, `t_power=1`, `t_purify=1`, `t_swing_angle=0` | ✗ `t_fan_mute=0`, `t_outdoor_mute=0`, `t_purify=1`, `t_swing_follow=0` | ✗ `t_dimmer=0`, `t_dr_onoff=0`, `t_fan_mute=0`, `t_purify=1` | ✗ `t_purify=1` |
| H2O Lightning 4B | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` |
| Jev | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` |
| GPT 6.1 Sol · low | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` |

### M06 新风与健康风

> Enable fresh air and healthy wind.

参考：`t_fresh_air=1`, `t_health_fan=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ ∅ | ✗ `t_fresh_air=1`, `t_health_fan=1`, `t_indoor_selfclean=1`, `t_onekey_selfclean=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0` | ✗ ∅ | ✗ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_temp_f=90` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_fresh_air=1`, `t_health_fan=1`, `t_onekey_selfclean=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_swing_follow=0` | ✗ `t_8heat=1`, `t_fresh_air=1`, `t_health_fan=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_temp_f=90` | ✗ `t_8heat=1`, `t_fresh_air=1`, `t_health_fan=1`, `t_swing_follow=2` | ✗ `t_fresh_air=1`, `t_health_fan=1`, `t_temp_f=90` | ✓ `t_fresh_air=1`, `t_health_fan=1` |
| H2O Lightning 4B | ✓ `t_fresh_air=1`, `t_health_fan=1` | ✓ `t_fresh_air=1`, `t_health_fan=1` | ✓ `t_fresh_air=1`, `t_health_fan=1` | ✓ `t_fresh_air=1`, `t_health_fan=1` | ✓ `t_fresh_air=1`, `t_health_fan=1` |
| Jev | ✓ `t_fresh_air=1`, `t_health_fan=1` | ✓ `t_fresh_air=1`, `t_health_fan=1` | ✓ `t_fresh_air=1`, `t_health_fan=1` | ✓ `t_fresh_air=1`, `t_health_fan=1` | ✓ `t_fresh_air=1`, `t_health_fan=1` |
| GPT 6.1 Sol · low | ✓ `t_fresh_air=1`, `t_health_fan=1` | ✓ `t_fresh_air=1`, `t_health_fan=1` | ✓ `t_fresh_air=1`, `t_health_fan=1` | ✓ `t_fresh_air=1`, `t_health_fan=1` | ✓ `t_fresh_air=1`, `t_health_fan=1` |

### M07 室内与室外自清洁

> Start indoor self-clean and outdoor self-clean.

参考：`t_indoor_selfclean=1`, `t_outdoor_selfclean=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ ∅ | ✗ `t_indoor_selfclean=1`, `t_onekey_selfclean=1`, `t_outdoor_selfclean=1` | ✗ ∅ | ✗ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1`, `t_temp_f=90` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_indoor_selfclean=1`, `t_onekey_selfclean=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0` | ✗ `t_8heat=1`, `t_indoor_selfclean=1`, `t_onekey_selfclean=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_direction=2` | ✗ `t_8heat=1`, `t_indoor_selfclean=1`, `t_outdoor_selfclean=1` | ✗ `t_indoor_selfclean=1`, `t_onekey_selfclean=1`, `t_outdoor_selfclean=1` | ✓ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1` |
| H2O Lightning 4B | ✓ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1` | ✓ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1` | ✓ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1` | ✓ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1` | ✓ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1` |
| Jev | ✓ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1` | ✓ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1` | ✓ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1` | ✓ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1` | ✓ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1` |
| GPT 6.1 Sol · low | ✓ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1` | ✓ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1` | ✓ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1` | ✓ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1` | ✓ `t_indoor_selfclean=1`, `t_outdoor_selfclean=1` |

### M08 垂直与水平风向

> Turn on up-and-down swing and set the horizontal airflow to both sides.

参考：`t_swing_direction=2`, `t_up_down=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ `t_swing_direction=2` | ✗ `t_left_right=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1` | ✗ `t_swing_direction=2` | ✗ `t_swing_angle=0`, `t_swing_direction=2` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_left_right=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_swing_follow=0`, `t_up_down=1` | ✗ `t_left_right=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1` | ✗ `t_left_right=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1` | ✗ `t_left_right=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1` | ✗ `t_left_right=1`, `t_swing_direction=2`, `t_up_down=1` |
| H2O Lightning 4B | ✗ `t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1` | ✗ `t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1` | ✓ `t_swing_direction=2`, `t_up_down=1` | ✗ `t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1` | ✓ `t_swing_direction=2`, `t_up_down=1` |
| Jev | ✗ `t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1` | ✗ `t_swing_angle=0`, `t_swing_direction=2`, `t_up_down=1` | ✓ `t_swing_direction=2`, `t_up_down=1` | ✓ `t_swing_direction=2`, `t_up_down=1` | ✓ `t_swing_direction=2`, `t_up_down=1` |
| GPT 6.1 Sol · low | ✓ `t_swing_direction=2`, `t_up_down=1` | ✓ `t_swing_direction=2`, `t_up_down=1` | ✓ `t_swing_direction=2`, `t_up_down=1` | ✓ `t_swing_direction=2`, `t_up_down=1` | ✓ `t_swing_direction=2`, `t_up_down=1` |

### M09 需求响应设置

> Turn on demand response, set the DR temperature offset to 5 degrees, and set the DR load capacity to 60 percent.

参考：`t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ `t_dr_offset=5` | ✗ `t_dr_mode=60`, `t_dr_offset=5` | ✗ ∅ | ✗ `t_dr_mode=60`, `t_dr_offset=5`, `t_temp_type=0` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp_type=1` | ✗ `t_8heat=1`, `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_temp_f=90` | ✗ `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1`, `t_temp_f=70` | ✗ `t_8heat=1`, `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1`, `t_temp=31`, `t_temp_f=90` | ✗ `t_dr_mode=60`, `t_dr_offset=5` |
| H2O Lightning 4B | ✓ `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1` | ✓ `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1` | ✓ `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1` | ✓ `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1` | ✓ `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1` |
| Jev | ✓ `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1` | ✓ `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1` | ✓ `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1` | ✓ `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1` | ✓ `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1` |
| GPT 6.1 Sol · low | ✓ `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1` | ✓ `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1` | ✓ `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1` | ✓ `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1` | ✓ `t_dr_mode=60`, `t_dr_offset=5`, `t_dr_onoff=1` |

### M10 制冷模式、Super Mode 与温度

> Switch to cooling mode, turn on Super Mode, and set the temperature to 22 degrees Celsius.

参考：`t_super=1`, `t_temp=22`, `t_temp_type=0`, `t_work_mode=2`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ `t_temp=22`, `t_work_mode=2` | ✗ `t_dr_offset=22`, `t_super=1`, `t_temp=22`, `t_work_mode=2` | ✗ `t_temp=22` | ✗ `t_temp=22`, `t_temp_f=90`, `t_temp_type=0`, `t_work_mode=2` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_dr_offset=22`, `t_outdoor_selfclean=1`, `t_super=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp=22`, `t_temp_f=70`, `t_temp_type=0`, `t_work_mode=2` | ✗ `t_8heat=1`, `t_dr_offset=22`, `t_super=1`, `t_swing_angle=0`, `t_temp=22`, `t_temp_f=90`, `t_temp_type=0`, `t_work_mode=2` | ✗ `t_8heat=1`, `t_super=1`, `t_temp=22`, `t_temp_f=70`, `t_temp_type=0`, `t_work_mode=2` | ✗ `t_8heat=1`, `t_dr_mode=22`, `t_dr_offset=22`, `t_dr_onoff=1`, `t_super=1`, `t_temp=22`, `t_temp_f=90`, `t_temp_type=0`, `t_work_mode=2` | ✗ `t_super=1`, `t_temp=22` |
| H2O Lightning 4B | ✓ `t_super=1`, `t_temp=22`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_super=1`, `t_temp=22`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_super=1`, `t_temp=22`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_super=1`, `t_temp=22`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_super=1`, `t_temp=22`, `t_temp_type=0`, `t_work_mode=2` |
| Jev | ✓ `t_super=1`, `t_temp=22`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_super=1`, `t_temp=22`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_super=1`, `t_temp=22`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_super=1`, `t_temp=22`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_super=1`, `t_temp=22`, `t_temp_type=0`, `t_work_mode=2` |
| GPT 6.1 Sol · low | ✓ `t_super=1`, `t_temp=22`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_super=1`, `t_temp=22`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_super=1`, `t_temp=22`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_super=1`, `t_temp=22`, `t_temp_type=0`, `t_work_mode=2` | ✓ `t_super=1`, `t_temp=22`, `t_temp_type=0`, `t_work_mode=2` |

### N01 仅开机，保持模式

> Please power on the AC without changing its operating mode.

参考：`t_power=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ ∅ | ✗ ∅ | ✗ ∅ | ✗ ∅ | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_dimmer=0`, `t_outdoor_selfclean=1`, `t_power=1`, `t_swing_angle=0`, `t_swing_follow=0` | ✗ `t_8heat=1`, `t_power=1`, `t_swing_angle=0`, `t_temp_f=90` | ✓ `t_power=1` | ✓ `t_power=1` | ✓ `t_power=1` |
| H2O Lightning 4B | ✓ `t_power=1` | ✓ `t_power=1` | ✓ `t_power=1` | ✓ `t_power=1` | ✓ `t_power=1` |
| Jev | ✓ `t_power=1` | ✓ `t_power=1` | ✓ `t_power=1` | ✓ `t_power=1` | ✓ `t_power=1` |
| GPT 6.1 Sol · low | ✓ `t_power=1` | ✓ `t_power=1` | ✓ `t_power=1` | ✓ `t_power=1` | ✓ `t_power=1` |

### N02 舒适自动与主模式区分

> Enable Comfort Auto; leave the operating mode unchanged.

参考：`t_indoortemp_detection=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ ∅ | ✗ ∅ | ✗ ∅ | ✗ ∅ | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_indoortemp_detection=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0` | ✗ `t_indoortemp_detection=1`, `t_temp_f=90` | ✗ `t_indoortemp_detection=1`, `t_tms=1` | ✓ `t_indoortemp_detection=1` | ✓ `t_indoortemp_detection=1` |
| H2O Lightning 4B | ✓ `t_indoortemp_detection=1` | ✓ `t_indoortemp_detection=1` | ✓ `t_indoortemp_detection=1` | ✓ `t_indoortemp_detection=1` | ✓ `t_indoortemp_detection=1` |
| Jev | ✓ `t_indoortemp_detection=1` | ✓ `t_indoortemp_detection=1` | ✓ `t_indoortemp_detection=1` | ✓ `t_indoortemp_detection=1` | ✓ `t_indoortemp_detection=1` |
| GPT 6.1 Sol · low | ✓ `t_indoortemp_detection=1` | ✓ `t_indoortemp_detection=1` | ✓ `t_indoortemp_detection=1` | ✓ `t_indoortemp_detection=1` | ✓ `t_indoortemp_detection=1` |

### N03 防冻制热与主模式区分

> Enable 8-degree frost protection; leave the operating mode unchanged.

参考：`t_8heat=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ ∅ | ✗ ∅ | ✗ ∅ | ✗ `t_temp_f=90` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_outdoor_mute=0`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp_type=1`, `t_tms=0` | ✗ `t_8heat=1`, `t_swing_angle=0`, `t_temp_f=90`, `t_temp_type=1` | ✗ `t_8heat=1`, `t_temp_f=90`, `t_temp_type=1` | ✗ `t_8heat=1`, `t_temp_f=90`, `t_temp_type=1` | ✓ `t_8heat=1` |
| H2O Lightning 4B | ✓ `t_8heat=1` | ✓ `t_8heat=1` | ✗ `t_8heat=1`, `t_temp_type=0` | ✗ `t_8heat=1`, `t_temp_type=0` | ✓ `t_8heat=1` |
| Jev | ✓ `t_8heat=1` | ✓ `t_8heat=1` | ✓ `t_8heat=1` | ✓ `t_8heat=1` | ✓ `t_8heat=1` |
| GPT 6.1 Sol · low | ✓ `t_8heat=1` | ✓ `t_8heat=1` | ✓ `t_8heat=1` | ✓ `t_8heat=1` | ✓ `t_8heat=1` |

### N04 关闭室内静音，保持室外设置

> Stop indoor quiet mode, but leave outdoor quiet unchanged.

参考：`t_fan_mute=0`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ ∅ | ✗ ∅ | ✗ ∅ | ✗ ∅ | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=0`, `t_fan_mute=0`, `t_swing_angle=0`, `t_swing_follow=0` | ✓ `t_fan_mute=0` | ✗ `t_fan_mute=0`, `t_swing_follow=0` | ✓ `t_fan_mute=0` | ✓ `t_fan_mute=0` |
| H2O Lightning 4B | ✓ `t_fan_mute=0` | ✓ `t_fan_mute=0` | ✗ `t_fan_mute=0`, `t_indoortemp_detection=0` | ✗ `t_fan_mute=0`, `t_indoortemp_detection=0` | ✗ `t_fan_mute=0`, `t_indoortemp_detection=0` |
| Jev | ✓ `t_fan_mute=0` | ✓ `t_fan_mute=0` | ✓ `t_fan_mute=0` | ✓ `t_fan_mute=0` | ✓ `t_fan_mute=0` |
| GPT 6.1 Sol · low | ✓ `t_fan_mute=0` | ✓ `t_fan_mute=0` | ✓ `t_fan_mute=0` | ✓ `t_fan_mute=0` | ✓ `t_fan_mute=0` |

### N05 新表达摄氏温度组合

> Use heating at 25 degrees Celsius with low fan speed.

参考：`t_fan_speed=5`, `t_temp=25`, `t_temp_type=0`, `t_work_mode=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ `t_temp=25` | ✗ `t_dr_offset=25`, `t_fan_speed=5`, `t_temp=25`, `t_work_mode=1` | ✗ `t_temp=25` | ✗ `t_temp=25`, `t_temp_f=90`, `t_temp_type=0` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_dimmer=1`, `t_dr_mode=25`, `t_dr_offset=25`, `t_fan_speed=5`, `t_outdoor_mute=0`, `t_outdoor_selfclean=1`, `t_power=1`, `t_swing_angle=0`, `t_swing_follow=0`, `t_temp=25`, `t_temp_f=77`, `t_temp_type=0`, `t_work_mode=1` | ✗ `t_8heat=1`, `t_dimmer=1`, `t_dr_offset=25`, `t_fan_speed=5`, `t_power=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_temp=25`, `t_temp_f=90`, `t_temp_type=0`, `t_work_mode=1` | ✗ `t_8heat=1`, `t_dr_offset=25`, `t_fan_speed=5`, `t_temp=25`, `t_temp_f=75`, `t_temp_type=0`, `t_work_mode=1` | ✗ `t_8heat=1`, `t_dimmer=1`, `t_dr_mode=25`, `t_dr_offset=25`, `t_fan_speed=5`, `t_temp=25`, `t_temp_f=90`, `t_temp_type=0`, `t_work_mode=1` | ✗ `t_8heat=1`, `t_fan_speed=5`, `t_temp=25`, `t_temp_type=0`, `t_work_mode=1` |
| H2O Lightning 4B | ✓ `t_fan_speed=5`, `t_temp=25`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=5`, `t_temp=25`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=5`, `t_temp=25`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=5`, `t_temp=25`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=5`, `t_temp=25`, `t_temp_type=0`, `t_work_mode=1` |
| Jev | ✓ `t_fan_speed=5`, `t_temp=25`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=5`, `t_temp=25`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=5`, `t_temp=25`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=5`, `t_temp=25`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=5`, `t_temp=25`, `t_temp_type=0`, `t_work_mode=1` |
| GPT 6.1 Sol · low | ✓ `t_fan_speed=5`, `t_temp=25`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=5`, `t_temp=25`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=5`, `t_temp=25`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=5`, `t_temp=25`, `t_temp_type=0`, `t_work_mode=1` | ✓ `t_fan_speed=5`, `t_temp=25`, `t_temp_type=0`, `t_work_mode=1` |

### N06 新表达华氏温度组合

> Use cooling at 72 degrees Fahrenheit with medium-high fan speed.

参考：`t_fan_speed=8`, `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ `t_fan_speed=8`, `t_temp_f=72`, `t_work_mode=2` | ✗ `t_fan_speed=8`, `t_temp_f=72`, `t_work_mode=2` | ✗ `t_temp_f=72` | ✗ `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_dimmer=1`, `t_dr_mode=72`, `t_fan_speed=8`, `t_outdoor_mute=0`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_swing_follow=0`, `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2` | ✗ `t_8heat=1`, `t_fan_speed=8`, `t_swing_angle=0`, `t_swing_direction=2`, `t_temp=30`, `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2` | ✗ `t_8heat=1`, `t_fan_speed=8`, `t_temp=25`, `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2` | ✗ `t_8heat=1`, `t_fan_speed=8`, `t_temp=31`, `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2` | ✗ `t_fan_speed=8`, `t_temp_f=72` |
| H2O Lightning 4B | ✓ `t_fan_speed=8`, `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2` | ✓ `t_fan_speed=8`, `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2` | ✓ `t_fan_speed=8`, `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2` | ✓ `t_fan_speed=8`, `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2` | ✓ `t_fan_speed=8`, `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2` |
| Jev | ✓ `t_fan_speed=8`, `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2` | ✓ `t_fan_speed=8`, `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2` | ✓ `t_fan_speed=8`, `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2` | ✓ `t_fan_speed=8`, `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2` | ✓ `t_fan_speed=8`, `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2` |
| GPT 6.1 Sol · low | ✓ `t_fan_speed=8`, `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2` | ✓ `t_fan_speed=8`, `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2` | ✓ `t_fan_speed=8`, `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2` | ✓ `t_fan_speed=8`, `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2` | ✓ `t_fan_speed=8`, `t_temp_f=72`, `t_temp_type=1`, `t_work_mode=2` |

### N07 灯光净化，保持电源

> Switch off the display light and switch on air purification; leave the main power setting unchanged.

参考：`t_dimmer=0`, `t_purify=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ ∅ | ✗ ∅ | ✗ ∅ | ✗ ∅ | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=0`, `t_dimmer=0`, `t_fresh_air=1`, `t_outdoor_mute=0`, `t_outdoor_selfclean=1`, `t_purify=1`, `t_swing_angle=0`, `t_swing_follow=0` | ✗ `t_fresh_air=1`, `t_outdoor_selfclean=1`, `t_purify=1`, `t_swing_angle=0` | ✗ `t_purify=1` | ✗ `t_purify=1` | ✗ `t_purify=1` |
| H2O Lightning 4B | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` |
| Jev | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` |
| GPT 6.1 Sol · low | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` | ✓ `t_dimmer=0`, `t_purify=1` |

### N08 新数值需求响应

> Enable demand response with a 7-degree temperature offset and 45 percent load capacity.

参考：`t_dr_mode=45`, `t_dr_offset=7`, `t_dr_onoff=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ ∅ | ✗ `t_8heat=1`, `t_dr_mode=45`, `t_dr_offset=7`, `t_temp=16` | ✗ ∅ | ✗ `t_dr_mode=45`, `t_dr_offset=31`, `t_temp_f=90`, `t_temp_type=0` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_dr_mode=45`, `t_dr_offset=7`, `t_dr_onoff=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_swing_follow=0`, `t_temp=27`, `t_temp_f=77`, `t_temp_type=1` | ✗ `t_8heat=1`, `t_dr_mode=45`, `t_dr_offset=7`, `t_dr_onoff=1`, `t_swing_angle=0`, `t_swing_direction=2`, `t_temp=31`, `t_temp_f=90`, `t_temp_type=1` | ✗ `t_8heat=1`, `t_dr_mode=45`, `t_dr_offset=7`, `t_dr_onoff=1`, `t_temp=27`, `t_temp_f=70`, `t_temp_type=1` | ✗ `t_8heat=1`, `t_dr_mode=45`, `t_dr_offset=7`, `t_dr_onoff=1`, `t_temp=31`, `t_temp_f=90`, `t_temp_type=1` | ✗ `t_dr_mode=45`, `t_dr_offset=7` |
| H2O Lightning 4B | ✓ `t_dr_mode=45`, `t_dr_offset=7`, `t_dr_onoff=1` | ✓ `t_dr_mode=45`, `t_dr_offset=7`, `t_dr_onoff=1` | ✗ `t_dr_mode=45`, `t_dr_offset=7`, `t_dr_onoff=1`, `t_temp_type=0` | ✓ `t_dr_mode=45`, `t_dr_offset=7`, `t_dr_onoff=1` | ✓ `t_dr_mode=45`, `t_dr_offset=7`, `t_dr_onoff=1` |
| Jev | ✓ `t_dr_mode=45`, `t_dr_offset=7`, `t_dr_onoff=1` | ✓ `t_dr_mode=45`, `t_dr_offset=7`, `t_dr_onoff=1` | ✓ `t_dr_mode=45`, `t_dr_offset=7`, `t_dr_onoff=1` | ✓ `t_dr_mode=45`, `t_dr_offset=7`, `t_dr_onoff=1` | ✓ `t_dr_mode=45`, `t_dr_offset=7`, `t_dr_onoff=1` |
| GPT 6.1 Sol · low | ✓ `t_dr_mode=45`, `t_dr_offset=7`, `t_dr_onoff=1` | ✓ `t_dr_mode=45`, `t_dr_offset=7`, `t_dr_onoff=1` | ✓ `t_dr_mode=45`, `t_dr_offset=7`, `t_dr_onoff=1` | ✓ `t_dr_mode=45`, `t_dr_offset=7`, `t_dr_onoff=1` | ✓ `t_dr_mode=45`, `t_dr_offset=7`, `t_dr_onoff=1` |

### N09 垂直摆风与水平直吹

> Enable vertical oscillation and point horizontal airflow straight ahead.

参考：`t_swing_direction=0`, `t_up_down=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ ∅ | ✗ `t_swing_direction=0` | ✗ ∅ | ✗ `t_swing_angle=0`, `t_swing_direction=0`, `t_temp_f=90` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_outdoor_mute=0`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_direction=0`, `t_swing_follow=0`, `t_tms=0`, `t_up_down=1` | ✗ `t_swing_angle=0`, `t_swing_direction=0`, `t_temp_f=90`, `t_up_down=1` | ✗ `t_8heat=1`, `t_swing_angle=0`, `t_swing_direction=0`, `t_swing_follow=1`, `t_up_down=1` | ✗ `t_swing_angle=0`, `t_swing_direction=0`, `t_up_down=1` | ✗ `t_swing_angle=0`, `t_swing_direction=0`, `t_up_down=1` |
| H2O Lightning 4B | ✓ `t_swing_direction=0`, `t_up_down=1` | ✗ `t_swing_angle=0`, `t_swing_direction=0`, `t_up_down=1` | ✓ `t_swing_direction=0`, `t_up_down=1` | ✓ `t_swing_direction=0`, `t_up_down=1` | ✓ `t_swing_direction=0`, `t_up_down=1` |
| Jev | ✓ `t_swing_direction=0`, `t_up_down=1` | ✓ `t_swing_direction=0`, `t_up_down=1` | ✓ `t_swing_direction=0`, `t_up_down=1` | ✓ `t_swing_direction=0`, `t_up_down=1` | ✓ `t_swing_direction=0`, `t_up_down=1` |
| GPT 6.1 Sol · low | ✓ `t_swing_direction=0`, `t_up_down=1` | ✓ `t_swing_direction=0`, `t_up_down=1` | ✓ `t_swing_direction=0`, `t_up_down=1` | ✓ `t_swing_direction=0`, `t_up_down=1` | ✓ `t_swing_direction=0`, `t_up_down=1` |

### N10 新风与健康风区分

> Enable fresh air while keeping healthy wind unchanged.

参考：`t_fresh_air=1`

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---|---|---|---|---|
| Strands Decider v19 | ✗ ∅ | ✗ `t_outdoor_selfclean=1` | ✗ ∅ | ✗ `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_temp_f=90` | ✗ ∅ |
| Liquid d1-2B | ✗ `t_8heat=1`, `t_fresh_air=1`, `t_outdoor_selfclean=1`, `t_swing_angle=0`, `t_swing_follow=0` | ✗ `t_fresh_air=1`, `t_swing_angle=0` | ✗ `t_fresh_air=1`, `t_swing_follow=0` | ✓ `t_fresh_air=1` | ✓ `t_fresh_air=1` |
| H2O Lightning 4B | ✓ `t_fresh_air=1` | ✓ `t_fresh_air=1` | ✓ `t_fresh_air=1` | ✓ `t_fresh_air=1` | ✓ `t_fresh_air=1` |
| Jev | ✓ `t_fresh_air=1` | ✓ `t_fresh_air=1` | ✓ `t_fresh_air=1` | ✓ `t_fresh_air=1` | ✓ `t_fresh_air=1` |
| GPT 6.1 Sol · low | ✓ `t_fresh_air=1` | ✓ `t_fresh_air=1` | ✓ `t_fresh_air=1` | ✓ `t_fresh_air=1` | ✓ `t_fresh_air=1` |

## 证据

- [冻结计划](plan.json)、[全部任务模板](experiments.json)、[离线参考](references.json)、[指标](five_model_summary.json)、[逐条评分](five_model_results.json)、[核验记录](audit.json)。
- [Jev原始调用](jev/formal_receipts.jsonl)、[GPT前179条](gpt/formal_receipts.jsonl)、[GPT后70条](gpt/remainder_receipts.jsonl)。
- [Bedrock模型配置](bedrock_profile.json)、[Jev运行记录](jev/formal_run.json)、[GPT运行记录](gpt/formal_run.json)。
- [S03完整请求与回答](examples/S03.api_raw.json)、[N04反例完整请求与回答](examples/N04.api_raw.json)。
- [此前三模型报告](../2026-10-30-prompt-ablation-v1/ABLATION.zh.md)。旧原始响应重新解码评分与已保存结果一致，文件哈希未改变。

- [GPT采集故障日志](gpt_formal.log)、[故障与续跑计划](gpt/recovery_plan.json)、[续跑记录](gpt/remainder_run.json)。原始formal_run.json保留中断时的状态，最终合并状态见five_model_summary.json。新增调用数含丢失记录对应的1次调用尝试。
- [五模型错误定位、缓存用量与M08完整问题选项](DIAGNOSTICS.zh.md)。后70条SDK bytes字段使用`__sdk_bytes_base64__`标记无损保存；只改变日志编码，不改变模型请求、effort、解析或评分。
