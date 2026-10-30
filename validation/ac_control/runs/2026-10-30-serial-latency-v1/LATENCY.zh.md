# 空调延迟复核：单任务与逐Key串行

使用原测试S03基线的完整业务输入；每个模式预先固定，三个模型依次测试。每模型先预热一次，每种模式重复3次并交替顺序；无并发HTTP请求，不启停模型。

> Set the air conditioner temperature to 24 degrees Celsius.

- 完整任务：一次请求包含30个Key选择题，等待全部回答后才开始下一任务。
- 逐Key串行：每次只发一个Key的问题，等待返回后再发下一个；30题全部执行。每次仍携带相同完整30项能力集，不按参考答案过滤问题或候选。
- 下表的单题时间来自实际逐Key请求计时；整任务时间分别按对应执行方式测量。

| 模型 | 完整30题请求均值 ms | 独立单题均值 ms | 独立单题P95 ms | 逐Key串行完成30题均值 ms |
|---|---:|---:|---:|---:|
| Strands Decider v19 | 2878.8 | 97.3 | 116.7 | 2925.2 |
| Liquid d1-2B | 611.6 | 105.8 | 115.8 | 3179.2 |
| H2O Lightning 4B | 5887.6 | 200.5 | 244.3 | 6019.1 |

完整请求均值每模型3次；单题统计每模型90次，包含不同Key与候选规模。逐Key整任务耗时包含30次请求及中间记录开销。这是一道固定Query的延迟诊断，不替代原20题正确率测试，也不是独立同分布的90道测试题。

## 拆分后输出是否改变

- Strands Decider v19：第1轮改变0个Key；第2轮改变0个Key；第3轮改变0个Key。
- Liquid d1-2B：第1轮改变6个Key（t_temp_f, t_swing_angle, t_8heat, t_health_fan, t_outdoor_mute, t_dr_offset）；第2轮改变6个Key（t_temp_f, t_swing_angle, t_8heat, t_health_fan, t_outdoor_mute, t_dr_offset）；第3轮改变6个Key（t_temp_f, t_swing_angle, t_8heat, t_health_fan, t_outdoor_mute, t_dr_offset）。
- H2O Lightning 4B：第1轮改变0个Key；第2轮改变0个Key；第3轮改变0个Key。

请求state与每题文本一致，不保证服务内部的截断、分批和预处理完全相同；若输出变化，不能直接用该诊断替换原成绩。

正式调用279次，预热3次；全部响应有效。保存的请求时间区间无重叠，三个模型测试区间无重叠。

[计划](plan.json) · [完整原始输入](payload.json) · [原始响应](receipts.jsonl) · [逐次指标](summary.json) · [运行时源码摘录](runtime_sources.json) · [H2O运行参数](runtime_config.json) · [原实验串行核验](original_serial_audit.json)。
