# 空调决策输入压缩：规范审查与离线验证

> **后续九模型实测已完成，见[完整对照结果](AC_ALL_MODELS_INPUT_OPTIMIZATION_RESULTS.md)。** 本页保留前期 Clef 专用 `None` 描述方案的离线记录。全量对照使用字符串描述，并让每个内部评分任务都能在 state 中读取完整能力表，输入编码与本页不同。多数模型在这两种统一压缩写法下准确率下降，不建议直接替换原始输入；本页的 34.8% 也不能作为后续统一版本的实测降幅。

**前期离线结论：原规范允许改变输入表示。保留完整能力映射、30 个字段、283 个现有候选和全部判分约束，可以把 Clef 一次全答的输入从约 9,423 tokens 降至约 6,148 tokens，减少 34.8%。**

本阶段于 2026-10-31 完成输入转换、能力完整性检查及真实分词器核算，**当时尚未运行优化输入的模型推理。** 下文保留当时的设计与验证计划；后续推理结果见上述报告。语义信息完整不等于模型一定能正确理解新的表达，历史的 95% 准确率、3.308 秒不属于优化版成绩。

## 1. 规范允许优化哪些内容

[AC_Control_Test_Spec.md 第 2.2 节](AC_Control_Test_Spec.md#22-标准-command-set-输入)明确规定：

> 供应商可以将上表转换为 Decider 所需的选择问题格式，但语义输入必须保留完整映射。

第 1 节还要求每条用例使用同一份完整能力集，禁止把预期答案放入模型输入。因此，需要保持的是业务含义与候选覆盖；原规范没有要求把同一映射同时写入原始 JSON、问题说明、每个选项描述三处。

| 必须保持 | 可以优化 |
|---|---|
| 原始 Query、不含离线答案 | 字段说明和选项描述的措辞 |
| 全部 30 项能力、名称、Key、Value 含义和范围单位 | 能力映射在 state 或 questions 中的存放位置 |
| 用户明确要求的所有可兼容设置 | 公共规则集中表达一次 |
| 未要求的设置不下发；`omit` 与数值 `0` 不同 | 数值候选的单位集中写入字段说明 |
| 摄氏/华氏温标伴随字段 | 去除选项描述中重复的数值和命令名称 |
| 自动除霜清洁 2–4 是状态、只有 0/1 可控制 | 在字段元数据保留状态映射，将可控制值放入候选 |
| 按完整 `cmdKey/cmdValue` 集合判分，多发、漏发、选错均失败 | 用确定性的适配器把模型选择整理成 `cmdList` |

模型仍须自行选择温标等伴随字段。适配器只映射选择结果、移除 `omit`，不补温标、不纠错、不删除模型多选的合法动作。

## 2. 两个可复现的输入版本

转换代码：[compact_input_protocol.py](../validation/ac_control/compact_input_protocol.py)。

- **`compact_catalog`**：保留原始 state，包含完整标准 Command Set 和原有全局规则；字段说明保留名称及第 2.1 节的区分要点，移除重复的公共指令。枚举描述使用原始标签，例如 `On`；数值选项保留完整 ID，单位由能力表提供。
- **`schema_once`**：state 保留原 Query、设备类型、原有全局规则；完整映射集中到 30 个选择问题。每个字段说明包含名称、原始类型、区分要点，范围字段额外包含 min/max/unit；枚举标签放在各候选中，状态专用值仍保存在字段元数据中。

`schema_once` 的完整能力映射可以从请求中确定性还原，并逐项对照标准 Command Set。数值候选仍完整包含摄氏 16–32、华氏 61–90、偏移 0–31、负载 0–100；每个字段另外包含 `omit`。生成器不读取 Query 中的数字来缩小候选，也不读取标准答案。

具体的数值描述省略方式使用 Clef 官方编码器支持的 `None`：服务仍编码 `option_id` 并为每个 ID 评分。这个实现已按 Clef 检查；其他决策服务的描述字段约束与分词方式需要各自验证。

当前候选与既有测试一样，覆盖整数。规范未明确限定数值只能为整数，因此这些验证不应被扩展解读为已覆盖所有小数输入；小数需要单独定义候选或数值处理方案并评测。

## 3. 离线分词结果

使用实际测试的 Clef-Flash 固定版本 `f0b7d3cd65296abfe459e6c228b618f5d8b26d2f` 的 tokenizer 与官方 `encode_record`。逐条还原历史 **2,049 次**请求，编码长度全部与原始响应 usage 一致。

| 输入版本 | 规范 20 题全答平均 tokens | 减少 | 单字段平均 tokens | 30 步串行累计平均 tokens |
|---|---:|---:|---:|---:|
| 原始 baseline | 9,423.35 | — | 1,454.42 | 43,632.50 |
| compact_catalog | 6,753.35 | 28.3% | 1,365.42 | 40,962.50 |
| schema_once | 6,148.35 | 34.8% | 1,377.12 | 41,313.50 |

全答压缩收益更大。单字段请求也必须看见完整能力集，`schema_once` 在拆分请求时会把完整 Command Set 放回 state。因此串行累计 tokens 仅减少约 5.3%，`compact_catalog` 约减少 6.1%。这里统计输入长度，不代表服务缓存命中量或实际计费。

剩余开销包括官方编码器的字段标题、选项 JSON 包装和 283 个候选。仅把 HTTP JSON 压成一行不会删除这些模型侧内容。继续改编码模板属于另一项实验，会改变联合决策头看到的输入分布。

### 完整请求示例与核算记录

- S03 摄氏温度：[保留原表](../validation/ac_control/runs/2026-10-31-clef-input-optimization-offline-v1/examples/S03.compact_catalog.json) · [映射集中到问题](../validation/ac_control/runs/2026-10-31-clef-input-optimization-offline-v1/examples/S03.schema_once.json)。
- M08 摆风：[保留原表](../validation/ac_control/runs/2026-10-31-clef-input-optimization-offline-v1/examples/M08.compact_catalog.json) · [映射集中到问题](../validation/ac_control/runs/2026-10-31-clef-input-optimization-offline-v1/examples/M08.schema_once.json)。
- M09 需求响应：[保留原表](../validation/ac_control/runs/2026-10-31-clef-input-optimization-offline-v1/examples/M09.compact_catalog.json) · [映射集中到问题](../validation/ac_control/runs/2026-10-31-clef-input-optimization-offline-v1/examples/M09.schema_once.json)。
- [原始分词核算、各文件哈希与验证状态](../validation/ac_control/runs/2026-10-31-clef-input-optimization-offline-v1/analysis.json)。

两种转换均检查了全部 156 个既有请求；每个版本还检查了 20 个规范场景的全部 600 种单字段请求，确保拆分后完整能力集仍在。另有 [5 项自动检查](../validation/ac_control/test_compact_input_protocol.py)，覆盖输入完整性、候选不随 Query 改变、状态值限制、数值边界及单字段上下文。

## 4. 如何验证速度提升与需求满足

降低输入长度会减少主模型预填充和决策头读取上下文的计算；候选数、模型权重和部分固定开销仍在，不能按 tokens 比例承诺耗时。

后续推理对照应固定同一台 L4、同一 Clef 权重、BF16 和官方编码器，仅改变输入版本；所有外部请求串行，预热单列。重新运行 baseline 与两个候选，保留全部失败记录，不能只沿用旧 baseline 时间。

主结果分别报告 20 个规范场景的单指令/多指令完全匹配、Key/Value、多发/漏发，以及三轮单字段、30 步串行、一次全答的均值和 p95。再用既有英文改写、中文和诊断题检查表达变化；这些题已经用于历史测试，不属于新的独立盲测。

优先验证 `compact_catalog`，再验证压缩更多的 `schema_once`。若某版本更快但增加误动作，不能认定满足需求。数字范围改成分位选择、从 Query 抽取数值后只给少数候选、减少字段、自动补温标等做法，会引入新的处理步骤或改变判断责任，应作为独立流程对照，不能混入本次输入压缩成绩。

复现离线核算（仅需安装 `tokenizers`，不加载模型权重）：

```bash
python validation/ac_control/compact_input_protocol.py \
  --tokenizer /path/to/pinned-clef-tokenizer.json \
  --output /path/to/new-offline-run

python -m unittest discover -s validation/ac_control -p 'test_compact_input_protocol.py'
```
