# H2O 运行时优化证据

[完整报告](../../../../docs/H2O_OPTIMIZATION.md) · [分析结果](optimization_summary.json) · [最终审计](audit.json) · [最终部署](final_runtime.json)

没有接受新的加速配置。编译约减少 10% 耗时、causal 更快，但质量检查出现回退；已恢复原双向、单序列、eager、FP8 配置。

**回退后仅 49/50 条选择复现旧基线，N09 仍错误，诊断成绩 9/10。** N09 在当前进程内三次完整请求、三次单 Key 请求的选择和概率完全一致，跨重启差异尚未定位。审计的 `passed` 指证据与部署检查通过，`historical_choices_reproduced_after_rollback: false` 单独记录质量问题。

共 863 次正式调用（851 次主试验、12 次补充重复验证）和 8 次预热，全部有效且串行。主观察位于 `variants/`，补充观察位于 `repeatability/`，冻结输入为 `cases.json` / `payload.json`，参考答案仅用于本地离线评分。补充观察没有替换旧失败或主分母。

`runtime_trials/` 与 `rollback/` 保留配置试验及原服务备份；`transfer.json` 保留 SSM 命令 ID。100 个本轮临时 S3 对象已在 GPU、S3、本地字节校验后清理，原始证据及备份继续保存在本地与 GPU。没有 Git 提交或 GitHub 推送。
