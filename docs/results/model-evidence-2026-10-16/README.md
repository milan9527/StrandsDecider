# 模型自主选择：原始与增强证据对比

[方法、结论与实际截图](../../MODEL_ROUTING_OPTIMIZATION.md)。这批数据的原始与优化型号都来自模型调用，没有程序排名选型。

- `results.json`：9 次预热、108 次正式路由调用（流程 36 / 原始型号 36 / 增强输入型号 36）、24 次目标执行，含真实请求、响应与页面导出。
- `summary.json`：路由统计、选型分布与目标输出，由 `scripts/summarize_routing_optimization.py` 生成。
- `candidate-order-diagnostic.json`：正式路由结束后额外做的 6 次 Decider 顺序检查，不混入正式性能。完整请求保留，只有候选顺序发生变化。
- `verification.json`：版本、测试结果、浏览器检查与文件哈希。
- `*-comparison.png`：第三轮路由和独立目标执行的汇总；`*-results.png` 为输入输出与结果面板；`mobile.png` 为手机布局。截图未替换数据。

原始与增强输入下，目标完整返回均为 6/12；完整返回不等于业务验收通过。程序选型历史批次在 `../task-ranking-2026-10-16/` 单独标记停用，不用于当前优化结论。
