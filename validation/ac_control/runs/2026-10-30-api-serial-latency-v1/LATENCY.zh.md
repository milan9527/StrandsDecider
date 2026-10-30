# 空调单步决策与总体耗时：Jev / GPT 串行补测

延续三个GPU模型的S03基线诊断，业务输入逐字节相同。沿用原API测试的客户端主机依次执行Jev、GPT，Jev完成后才开始GPT；各模型预热1次，每模式正式重复3轮，模式顺序交替。GPT保持low effort及原固定JSON格式提示。

> Set the air conditioner temperature to 24 degrees Celsius.

- 单步决策：一个请求只回答一个Key，保留完整30项能力状态和该题全部原始候选。
- 30步串行总时间：每一步返回后才发下一步，测量首步开始至第30步结束，包含中间记录开销。
- 一次回答30题：一个请求携带全部问题，测量收到完整回答的时间。

| 模型 | 单步均值 ms | 单步P95 ms | 30步串行总时间均值 ms | 一次回答30题均值 ms |
|---|---:|---:|---:|---:|
| Strands Decider | 97.3 | 116.7 | 2925.2 | 2878.8 |
| Liquid d1-2B | 105.8 | 115.8 | 3179.2 | 611.6 |
| H2O Lightning 4B | 200.5 | 244.3 | 6019.1 | 5887.6 |
| Jev 1.14.0 | 55.6 | 82.7 | 1679.9 | 108.1 |
| GPT 6.1 Sol low | 902.3 | 1322.8 | 27084.9 | 2308.6 |

各模型单步统计来自90次实际请求，完整请求统计来自3次请求。它们是同一个Query内30种不同Key的重复测量，并非90个独立业务场景。三个GPU模型复用前一轮已审计记录，Jev/GPT本轮新增186次正式调用和2次预热；本轮错误数为0。五模型合计465次正式调用、5次预热，保存的请求与模型运行时间区间均无重叠。

上述数字为客户端耗时：GPU服务走本机loopback，Jev走HTTPS，GPT走Bedrock。业务输入和串行规则相同，GPU与API测试客户端主机不同；模型硬件、网络、服务实现与缓存也不同。预热不计入统计，未显式配置提示缓存；原生usage完整保留。Jev未返回服务端耗时。

## 拆分后的回答

- Jev 1.14.0：第1轮改变0个Key；第2轮改变0个Key；第3轮改变0个Key。
- GPT 6.1 Sol low：第1轮改变0个Key；第2轮改变0个Key；第3轮改变0个Key。

这是一道固定Query的延迟与输出一致性诊断，不替代原20题正确率。前三模型中Liquid拆分后每轮6个Key选择改变；其原准确率属于完整30题请求。

## 各Key实测时间

| Key | Jev均值 ms | GPT均值 ms | Jev三轮选择 | GPT三轮选择 |
|---|---:|---:|---|---|
| `t_power` | 53.4 | 629.5 | omit, omit, omit | omit, omit, omit |
| `t_work_mode` | 59.3 | 829.7 | omit, omit, omit | omit, omit, omit |
| `t_temp` | 47.1 | 810.8 | 24, 24, 24 | 24, 24, 24 |
| `t_temp_f` | 61.5 | 1083.8 | omit, omit, omit | omit, omit, omit |
| `t_temp_type` | 65.5 | 793.1 | 0, 0, 0 | 0, 0, 0 |
| `t_fan_speed` | 52.4 | 860.7 | omit, omit, omit | omit, omit, omit |
| `t_fan_mute` | 49.8 | 600.2 | omit, omit, omit | omit, omit, omit |
| `t_super` | 58.3 | 1044.7 | omit, omit, omit | omit, omit, omit |
| `t_up_down` | 63.2 | 932.9 | omit, omit, omit | omit, omit, omit |
| `t_indoortemp_detection` | 47.5 | 1022.3 | omit, omit, omit | omit, omit, omit |
| `t_left_right` | 63.3 | 872.6 | omit, omit, omit | omit, omit, omit |
| `t_swing_angle` | 61.1 | 988.8 | omit, omit, omit | omit, omit, omit |
| `t_swing_direction` | 48.6 | 823.4 | omit, omit, omit | omit, omit, omit |
| `t_eco` | 64.1 | 862.8 | omit, omit, omit | omit, omit, omit |
| `t_purify` | 50.0 | 1013.1 | omit, omit, omit | omit, omit, omit |
| `t_swing_follow` | 72.1 | 1190.9 | omit, omit, omit | omit, omit, omit |
| `t_8heat` | 51.8 | 970.2 | omit, omit, omit | omit, omit, omit |
| `t_sleep` | 51.1 | 921.0 | omit, omit, omit | omit, omit, omit |
| `t_dimmer` | 52.0 | 657.4 | omit, omit, omit | omit, omit, omit |
| `t_indoor_selfclean` | 56.0 | 799.2 | omit, omit, omit | omit, omit, omit |
| `t_outdoor_selfclean` | 49.4 | 976.2 | omit, omit, omit | omit, omit, omit |
| `t_onekey_selfclean` | 58.8 | 693.9 | omit, omit, omit | omit, omit, omit |
| `t_fresh_air` | 53.5 | 1320.9 | omit, omit, omit | omit, omit, omit |
| `t_tms` | 50.9 | 872.1 | omit, omit, omit | omit, omit, omit |
| `t_health_fan` | 49.0 | 920.0 | omit, omit, omit | omit, omit, omit |
| `t_outdoor_mute` | 56.2 | 1055.4 | omit, omit, omit | omit, omit, omit |
| `t_dr_onoff` | 46.7 | 1042.5 | omit, omit, omit | omit, omit, omit |
| `t_dr_offset` | 69.4 | 908.3 | omit, omit, omit | omit, omit, omit |
| `t_dr_mode` | 52.9 | 869.4 | omit, omit, omit | omit, omit, omit |
| `t_auto_defrost_clean` | 53.4 | 703.9 | omit, omit, omit | omit, omit, omit |

[冻结计划](plan.json) · [完整输入](payload.json) · [请求与原始回答](receipts.jsonl) · [逐次指标及usage](summary.json) · [五模型合并指标](five_model_summary.json) · [前三模型补测](../2026-10-30-serial-latency-v1/LATENCY.zh.md)。
