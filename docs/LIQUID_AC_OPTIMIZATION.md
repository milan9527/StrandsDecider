# Liquid 空调控制准确率优化

**本轮不替换原两阶段。** 温度组合方案把原规范整条指令匹配从 **11/20 提升到 16/20**，但 24 条留出新问题仍为 **12/24**，与原两阶段持平；平均完整决策从 **0.734 秒增至 1.117 秒**。它未通过测试前规定的采用条件。代码和真实结果均已保留，新方案可显式调用作实验。

2026-10-30，使用既有 EC2 L4 上的 `LiquidAI/d1-2B`，对空调请求的提示词和动作协议做真实对照。模型权重、BF16 推理配置及常驻服务保持不变。本次新增的是可直接调用原生 Liquid 服务的空调客户端；通用接口和演示页面尚未切换此协议。

最终统计、是否通过预定采用条件、逐题差异及计时见 [本轮结果](../validation/ac_control/runs/2026-10-30-liquid-accuracy-v1/RESULTS.zh.md)，机器可读推荐见 [recommendation.json](../validation/ac_control/runs/2026-10-30-liquid-accuracy-v1/recommendation.json)。

## 实现的优化

第一阶段按功能语义判断是否需要控制：区分室内／室外静音、主运行模式／独立功能、目标温度／DR 偏移、防冻功能／制热模式。选项为 `omit`、`apply`、`review`；明确关闭也属于动作，保持不变属于 `omit`。`apply` 与 `review` 都进入第二阶段，第二阶段仍可选择 `omit`。`review` 是模型选择的复核分支，不是经过校准的置信度。

温度方案把 `t_temp`、`t_temp_f`、`t_temp_type` 合成一道完整动作题。例如模型选择 `t_temp_f:68`，协议才展开为 `t_temp_f=68` 与 `t_temp_type=1`。全量提供摄氏 16–32、华氏 61–90 的整数，以及只换单位和 `omit`，不根据用户文本抽数字或删候选，不读取参考答案。

每个阶段的状态仍包含原始全部 30 项设备能力，DR 百分比仍为 0–100；温度组合后第一阶段有 28 道逻辑题。其他值候选保持原定义。第二阶段只包含模型第一阶段放行的功能。

这是**最终控制指令的协议优化**：模型实际选择、动作映射和最终 `commands` 分别保存。不能把温度组合后的成绩描述成模型在原始 30 道逐 Key 问题上的原生准确率。既有逐 Key 方案仍严格计分，漏掉单位仍算错。

## 对照与数据隔离

开发集是已知原规范 20 条加既有诊断 10 条，每条测试原顺序和反转顺序。比较五个方案：原始基线、原两阶段、语义门控、语义门控＋温度组合、组合方案＋六个通用示例，共 300 条观察。

另写 24 条新表达及组合，在首次推理前同时冻结输入、参考和选择规则；先完成开发集、选定候选，才将新问题上传 GPU。验证阶段只比较原始基线、原两阶段和这个候选，每条同样测试两种顺序，共 144 条观察。这些新问题参考了已知错误类别，属于同领域留出验证，不是外部盲测集；换序也不是新增独立题目。

采用条件提前写入 [plan.json](../validation/ac_control/runs/2026-10-30-liquid-accuracy-v1/plan.json)：候选必须提高开发集原始顺序总正确数，原规范、诊断原始顺序和整体换序成绩均不能下降；再用新问题验证，要求原始顺序优于原两阶段、换序不差于原两阶段。只按开发集选一次，不根据验证结果换方案或继续改提示词。子集总数改善仍可能包含个别题目退步，详见逐题报告。

全部请求在同一 GPU 主机上依次调用 `127.0.0.1:18801/v1/systemone`，两个阶段也串行；每条任务轮换方案执行次序。每阶段每方案预热一次，无自动重试。保存完整 HTTP 请求、原始响应、模型身份、时间戳、候选映射、环境和源码哈希。标准答案只留本机，上传包内容可审计。

耗时统计为 GPU 主机客户端实际 HTTP 往返之和。一条决策包括门控，以及有放行功能时的取值请求；不是单个 Key 的推理耗时，也不是 30 次独立请求串行。`wall_ms` 从首个请求准备完成后开始，包含阶段间处理；不包含最初提示词构建、SSM/S3 传输、预热或离线评分。客户端往返不等于纯 GPU 计算时间。

## 实际问题与回答

成功改善的 S04：

> Set the air conditioner temperature to 68 degrees Fahrenheit.

原两阶段只输出 `t_temp_f=68`，漏掉单位。组合方案第一阶段放行 `temperature_action`，第二阶段从全部合法温度动作中选择 `t_temp_f:68`，最终输出：

```json
[
  {"cmdKey": "t_temp_f", "cmdValue": "68"},
  {"cmdKey": "t_temp_type", "cmdValue": "1"}
]
```

完整 [用户请求及原能力候选](../validation/ac_control/runs/2026-10-30-liquid-accuracy-v1/examples/S04-request.json)、[门控请求](../validation/ac_control/runs/2026-10-30-liquid-accuracy-v1/examples/S04-gate-request.json)、[第二阶段问题与全部选项](../validation/ac_control/runs/2026-10-30-liquid-accuracy-v1/examples/S04-value-request.json)、[模型实际回答和映射](../validation/ac_control/runs/2026-10-30-liquid-accuracy-v1/examples/S04-temperature_bundle-response.json)均可查看。

明确保留的回退 N03：

> Enable 8-degree frost protection; leave the operating mode unchanged.

正确指令是 `t_8heat=1`。原两阶段答对，温度组合方案第一阶段却把防冻功能选成 `omit`，最终返回空列表。完整 [请求](../validation/ac_control/runs/2026-10-30-liquid-accuracy-v1/examples/N03-request.json)及[实际错误回答](../validation/ac_control/runs/2026-10-30-liquid-accuracy-v1/examples/N03-temperature_bundle-response.json)保留。这说明当前门控仍会漏掉明确动作；问题组合和提示词变化也可能影响温度以外的字段，不能保证只改变温度表现。

留出验证中改善 4 条，也退步 4 条：AI Smart 开启、防冻关闭、室内清洁均在门控阶段被全部省略；“竖直位置 4＋室内静音”漏掉竖直位置，还多开了室外静音。完整错误逐项列在结果报告中。候选换序导致输出改变的案例从 11/24 降到 3/24，但正确数仍相同；更稳定不等于更正确。

本轮证据说明温度动作组合能修复一部分单位／跨温标错误，但语义门控没有稳定提高功能召回。增加六个通用示例也没有改善开发集最佳结果。后续值得单独研究“保持原门控，仅组合温度”，或使用独立的领域训练数据改善功能识别；这两项尚未在本轮验证，不能据此宣称有效。没有继续针对这 24 条验证题调提示词。

## 使用方式

客户端 [liquid_ac_client.py](../validation/ac_control/liquid_ac_client.py)直接使用已部署 Liquid 原生接口；输入是含 `state` 与 `questions` 的完整原始 payload。通过 `--strategy temperature_bundle` 显式启用组合方案，或使用 `two_stage` 作对照。按上方最终推荐及适用限制选择。

在能访问 GPU 本机端口的环境运行；测试客户端及依赖源码也已放在 GPU 本轮证据目录中：

```bash
python validation/ac_control/liquid_ac_client.py \
  --request validation/ac_control/runs/2026-10-30-liquid-accuracy-v1/examples/S04-request.json \
  --strategy temperature_bundle \
  --endpoint http://127.0.0.1:18801 \
  --output /tmp/liquid-ac-new-decision.json
```

输出包含 `status`、`commands`、`gate_choices`、`model_selections`、`action_mapping`、两阶段原始输入输出与计时。输出文件已存在时拒绝覆盖；调用失败保存为错误，不重试或补答案。没有向实际空调下发控制。

## 复现与证据

下面是一次新实验的完整顺序，需要既有 AWS 权限；`collect` 返回 Success 后才开始下一阶段。

```bash
.venv/bin/python -m pytest -q validation/ac_control/test_liquid_accuracy.py

python validation/ac_control/prepare_liquid_accuracy.py --run validation/ac_control/runs/YOUR_LIQUID_RUN
python validation/ac_control/remote_liquid_accuracy.py development --run validation/ac_control/runs/YOUR_LIQUID_RUN
python validation/ac_control/remote_liquid_accuracy.py collect --run validation/ac_control/runs/YOUR_LIQUID_RUN
python validation/ac_control/analyze_liquid_accuracy.py --run validation/ac_control/runs/YOUR_LIQUID_RUN --select

python validation/ac_control/remote_liquid_accuracy.py validation --run validation/ac_control/runs/YOUR_LIQUID_RUN
python validation/ac_control/remote_liquid_accuracy.py collect --run validation/ac_control/runs/YOUR_LIQUID_RUN
python validation/ac_control/audit_liquid_accuracy.py --run validation/ac_control/runs/YOUR_LIQUID_RUN
```

严格的新一轮留出验证需要新的、提前冻结的问题；重跑现有 24 题只能检查复现性。

[冻结计划](../validation/ac_control/runs/2026-10-30-liquid-accuracy-v1/plan.json) · [开发集选型记录](../validation/ac_control/runs/2026-10-30-liquid-accuracy-v1/selection.json) · [完整评分](../validation/ac_control/runs/2026-10-30-liquid-accuracy-v1/accuracy_summary.json) · [审计](../validation/ac_control/runs/2026-10-30-liquid-accuracy-v1/audit.json) · [本轮所有证据](../validation/ac_control/runs/2026-10-30-liquid-accuracy-v1/)。

本轮仅更新本地代码、文档及 GPU 测试目录，未执行 Git commit 或 push。
