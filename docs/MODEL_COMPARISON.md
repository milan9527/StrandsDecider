# Decider、普通大模型与 BERT：本项目如何比较

本项目使用官方 `StrandsAgents/strands-decider-2B-hobson-v19`，不是直接将 Qwen 聊天模型改名。主体为 Qwen3.5-2B，配合 LoRA 与 Pointer Head；实现锁定到 [官方源码 63d24ae](https://github.com/strands-labs/strands-decider/tree/63d24ae286e50105fba0bd1db15b0e243aea4650/src/strands_decider)。

## Decider 怎样得到一个选择

1. 应用提供业务状态 `state`、问题 `instructions`、候选项及其适用条件 `criteria`。
2. 提示构造器将它们编码为模型输入，并定位候选位置和答案位置。
3. Pointer Head 使用答案位置与候选位置的隐藏表示，经归一化、投影和点积得到候选 logits；按问题类型使用温度，再计算概率。
4. `choice` 取最高概率对应的候选。候选来自请求，模型不会临时发明新的业务动作。
5. 输出校验后，由应用执行器决定实际动作；模型本身没有资金权限。

这是可从公开实现核对的计算流程，不是模型输出的自然语言思维链。概率分布可以显示模型偏向哪个动作，不能证明它在某一次判断中“为什么忽略了某个条件”。

对于 `K > 1` 的 choice 问题，confidence 为 `clip((K × p_max − 1) / (K − 1), 0, 1)`；单候选为 1。它不同于最高候选概率，也不是金融业务正确率。`noul` 输出真概率，`score` 对有序等级计算期望；不要将 choice 的 confidence 公式套到所有类型。

## 与常见 BERT 分类器的区别

| 维度 | 常见 BERT + 固定分类头 | Strands Decider | 本项目 GPT-6.1 Sol |
| --- | --- | --- | --- |
| 类别含义 | 标签映射和监督训练定义 K 个输出维度 | 候选名称与条件随请求输入 | 提示中给出同样候选 |
| 输出方式 | 编码表示 → 固定 K 类分类头 | 对当前候选位置进行共享评分 | 自回归生成候选 ID JSON |
| 新增类别 | 通常改标签集、分类头并训练 / 微调 | 不必按 K 扩充固定输出头；仍需验证新任务能力 | 修改提示与候选；仍需验证条件遵循 |
| 典型用途 | 标签稳定、有领域标注的分类任务 | 候选变化、自然语言定义的有限选择 | 开放式生成、规划，也可做受限选择 |
| 本项目实测 | 未部署、未测速 | L4 / CUDA，逐项决策 | Bedrock Converse，reasoning `low` |

BERT 本身属于深度学习。基于 BERT 的文本对或 NLI 蕴含模型也能按候选描述评分，支持动态候选或零样本分类；动态候选并非 Decider 独有。没有 BERT 的实测数据，不能根据 Decider 快于 GPT 的样例推断 Decider 比 BERT 更快或更准确。

## 演示参考不等于执行规则

| 代码入口 | 职责 |
| --- | --- |
| `app/crypto.py::OPTIONS` | 提供候选动作和适用条件 |
| `facts()` / `payload_for()` | 计算已知事实并构造模型输入 |
| `reference()` | 用开发者定义的策略计算演示参考，用于对照 |
| `execution_action()` / `apply()` | 根据执行时的实际条件校验资金与结案，记录实际动作 |
| `app/crypto_loop.py::tick()` | 读取执行结果，将反馈用于下一轮判断、等待或重判 |

参考选择在模型输出之后独立比较，不直接填入模型输入作为答案。原始选择与参考不同只记录差异；应用允许合理的保守路径继续处理，但仍可能挂起资金。执行保护调整不能计作模型预测正确。

默认 12 次确认、60 分钟结算 SLA 是演示参数，不是行业统一标准。金额、地址、权限、记账与幂等应由支付系统执行。模型的价值主要在自然语言理解与路径选择。

## 固定流程与反馈闭环

- **固定流程**：冻结本轮输入，每步并发比较两模型，收齐建议后执行各自方案。同一输入指纹且均成功的结果才进入配对速度统计。
- **优化流程**：保持固定流程的候选 ID、证据与执行保护，按场景去除无关字段、明确候选适用条件。四个场景均支持；非退款不再携带退款审批字段，商户结算不再携带收款确认字段。两模型使用相同优化输入，原始选择与实际执行仍分别记录；不能把输入优化等同于模型微调或保证准确率。见 [具体字段与候选定义](../app/crypto_profiles.py)。
- **反馈闭环**：每侧独立地判断、执行并读取结果，外部条件缺失时等待事件，无效动作可有限重判。两侧后续输入可能不同，重点看业务是否完成、调用数、无进展和人工接管。
- **完成口径**：决策返回、步骤处理、资金动作和业务完成分别显示。只有目标订单、对应模拟账本和工单结案均确认，才显示完成。
- **输出来源**：模型选择、应用实际动作、模拟器事件和客服模板分别标记；失败请求不会被规则回放替代。

2026-10-10 的真实固定批次有 19 组成功配对和 1 次 GPT 读取超时。两组真实闭环中双方均完成业务，但这不保证未来成功。参见 [该次历史基准](results/benchmark-2026-10-10.json)、[闭环实现](CLOSED_LOOP.md) 与 [27 页 v6 优化实测演示资料](presentations/v6/README.md)。当前部署已改为 EC2 `g6.xlarge` 常驻运行；PPT 中这组图表与截图仍属于原 SageMaker 采集，不能将其误作 EC2 实测或部署迁移的性能提升证据。v6 第 23–24 页独立呈现 2026-10-11 EC2 输入优化批次，Decider 参考一致从 14/20 变为 18/20；仍有错误，未修改模型权重，也不代表稳定提速。Jev / System One 介绍属于模型背景，Jev 未参与本项目实测。

## 参考资料

- [Strands Decider 官方介绍](https://strandsagents.com/blog/introducing-strands-decider/)
- [官方 v19 模型卡](https://huggingface.co/StrandsAgents/strands-decider-2B-hobson-v19)
- [锁定版本源码](https://github.com/strands-labs/strands-decider/tree/63d24ae286e50105fba0bd1db15b0e243aea4650/src/strands_decider)：`prompting.py`、`modeling.py`、`infer.py`、`schema.py`
- [BERT 原始论文](https://aclanthology.org/N19-1423/) 与 [官方分类器](https://github.com/google-research/bert/blob/master/run_classifier.py)
- [零样本分类与文本蕴含](https://aclanthology.org/D19-1404/)
