# 适配说明

[English](ADAPTER.md) | 简体中文

## 与官方推理的对应关系

| 官方实现 | 本项目 |
|---|---|
| Qwen3.5 文本底座 + PEFT LoRA | `export.py` 用官方底座加载器与 PEFT `merge_and_unload(safe_merge=True)` 导出 |
| `render_state` / `render_question` | 直接使用固定提交中的官方实现 |
| `_chunks` / `_fit` / `_option_token_index` | 每个请求创建独立的轻量上下文调用；不共用 `_last_offsets` |
| Transformer 输出的最后隐藏状态 | vLLM Qwen3.5 模型的完整 prefill 隐藏状态 |
| `PointerHead` | 直接使用官方类，加载原 `head.safetensors`，保持 FP32 |
| `temperature_by_kind` | 随每个问题传入 pooler |
| `_to_answer` | 直接使用官方实现，保留三种类型和 score 的 ordinal smoothing |
| `/v1/systemone` | 保留请求/响应结构和 `latency_ms` |

vLLM 插件通过 `vllm.general_plugins` 注册 `StrandsDeciderForPooling`。服务必须通过本项目的 `decider-vllm serve` 启动，普通 chat/completions、embeddings 或裸 `/pooling` 请求没有候选位置 metadata，不能作为等价接口。

## 关键文件

| 文件 | 职责 |
|---|---|
| `src/decider_vllm/export.py` | 合并和导出，原子写入，拒绝覆盖 |
| `src/decider_vllm/artifacts.py` | 导出清单及校验 |
| `src/decider_vllm/preprocessing.py` | 官方文本处理与请求独立位置 |
| `src/decider_vllm/pointer.py` | packed token 输入的批量候选评分 |
| `src/decider_vllm/vllm_model.py` | Qwen3.5 pooling 插件与 GPU 权重加载 |
| `src/decider_vllm/backend.py` | 异步请求、调度元数据和取消 |
| `src/decider_vllm/server.py` | HTTP 接口、容量限制和生命周期 |
| `src/decider_vllm/evaluation.py` | 真实接口对齐、压测及原始数据 |

## 首版约束

- 仅支持 v19 的 Qwen3.5 Pointer Head；不自动升级 checkpoint。
- 单 GPU、tensor parallel = pipeline parallel = 1。
- BF16 底座、FP32 head；量化和动态 LoRA 不支持。
- 默认严格执行 4096 token 窗口，超出返回 422。`--allow-truncation` 使用官方相同截断逻辑；若截掉候选项仍拒绝请求。
- 禁止图片输入。
- 关闭 prefix caching 和 chunked prefill，避免缺失候选隐藏状态；pooler 会检查实际处理长度并拒绝不完整数据。
- 关闭 CUDA Graph，尚未验证图捕获与本自定义 pooler 的兼容性。
- 不依赖 vLLM 默认的 LAST、MEAN pooling 或标准固定分类头。
- 多问题分别提交完整状态和问题，不保证原服务共享上下文路径的 token 用量和耗时。
- pooler 兼容 vLLM 启动时没有业务 metadata 的合成 profiling 请求；业务入口始终显式提供 metadata。
- 新服务没有原演示的 GPU 启停、DynamoDB 独占租约、用户登录或业务执行逻辑。

## 校验目标

1. 原始模型与导出模型使用相同的 tokenizer、文本模板、候选顺序和窗口规则。
2. 单问题、多问题、混合长度和混合候选数的批处理结果可对齐。
3. 与官方参考相比，选择一致；默认概率/置信度绝对偏差阈值为 0.02，可以显式调整。
4. 并发时输入、候选位置和结果不会交叉。
5. 超时、断连或一个问题失败时，兄弟问题被取消，容量恢复。
6. 在目标 GPU 完成加载和行为对齐后，才能判断性能和是否适合替换原服务。

引擎替换不会修正模型学到的业务判断；已有错误可能继续存在。质量优化和性能优化需要分别测量。

## GPU 测量状态

L4 上已完成真实模型加载、21 请求 / 23 判断对齐，以及并发 1–32 的测量，见 [GPU 并发报告](GPU_CONCURRENCY.zh-CN.md)。当前配置在并发 4–8 附近达到吞吐平台；首轮并发 16 出现两次超时，延长测试并发 32 又出现三次，根因尚未确认。

后续的 [公网 API 部署](API.zh-CN.md) 已为 HTTP 请求、预处理、vLLM 提交和结果返回增加关联 ID 与阶段耗时。HTTP 测试复现了断连监听的取消等待竞争问题，可能导致推理完成后响应清理仍被阻塞；现已改为直接等待 ASGI 断连消息。这是经过验证的代码修复，但不能据此认定每个历史 GPU 超时都有相同原因。原始测量保持不变，公网接口验证单独记录在 [部署记录](DEPLOYED.zh-CN.md)。

后续性能优化应逐项验证更大的 token batch、CPU 预处理开销、同步点及 CUDA Graph 兼容性，每项都需重跑行为对齐。当前已有提速同时涉及 LoRA 合并、计算内核和批处理调度，不能把收益全部归因于某一个 vLLM 参数。

## 依赖依据

- [Strands Decider 固定源码](https://github.com/strands-labs/strands-decider/tree/63d24ae286e50105fba0bd1db15b0e243aea4650)
- [vLLM 0.31.0](https://github.com/vllm-project/vllm/tree/v0.31.0)
- [Qwen3.5 实现](https://github.com/vllm-project/vllm/blob/v0.31.0/vllm/model_executor/models/qwen3_5.py)
- [Pooling metadata](https://github.com/vllm-project/vllm/blob/v0.31.0/vllm/v1/pool/metadata.py)
- [Pooling 模型适配](https://github.com/vllm-project/vllm/blob/v0.31.0/vllm/model_executor/models/adapters.py)
- [Pooling 文档](https://docs.vllm.ai/en/stable/models/pooling_models/)

依赖以各自许可证提供。本项目通过依赖导入官方模型类和输入处理，没有重新分发模型权重。
