# Strands Decider · 决策实验室

基于 [Strands Decider 官方介绍](https://strandsagents.com/blog/introducing-strands-decider/)的中文交互演示。FastAPI 后端 + 原生 HTML/CSS/JavaScript，无需 Node.js 构建。

支持：

- **用户名登录**：自建用户名 / 密码认证，无 Cognito；支持退出、会话过期、登录限流和管理员重置密码。
- **决策工作台**：12 个场景，覆盖业务运营、Agent 流程、内容理解、数据与运维；支持分类筛选、关键词搜索，可编辑上下文、问题类型与选项，一次最多 8 个问题。
- **三种官方问题类型**：`choice`、`noul`、`score`，展示结构化结果、候选项分布、confidence、JSON 和请求代码。
- **决策计时**：每个问题显示实测耗时，运行中显示累计时间，完成后显示总时间；运行记录和 JSON 导出保留计时数据。
- **工具调用守卫**：复现天气案例，用两个判断决定 `Guide` / `Proceed`，可调整策略阈值。
- **运行记录**：按账号在当前标签页保存最近 30 次请求，刷新后保留，退出或关闭标签页后清除。
- **两种模式**：无需下载模型的示例回放，以及连接官方服务的真实推理。

AWS 部署使用独立的 `frontend/` 静态站点和 ECS API / 模型容器；架构、更新及运维步骤见 [deployment/README.md](deployment/README.md)。

**在线演示：https://d30wbetbveqce3.cloudfront.net**（AWS `us-east-2`，私有 S3 + CloudFront OAC + 私网 ECS）。

## 快速运行

需要 Python 3.11+ 和 [uv](https://docs.astral.sh/uv/getting-started/installation/)。

```bash
uv sync
uv run python -m scripts.manage_users create admin --generate-to .deployment/local-credentials.json
export AUTH_COOKIE_SECURE=false  # 仅本地 HTTP 开发
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

打开 **http://localhost:8000**，使用生成文件中的账号密码登录。默认是示例回放，选择场景后点击「运行决策」；快捷键 `Ctrl/⌘ + Enter`。

示例模式的概率是为教学设置的预设数值，**不是模型输出，也不展示虚构的推理时间或 token 用量**。只允许回放未修改的预设；修改文本或问题后需切换到真实模型。真实推理失败时会直接报错，不会退回示例数据。

## 时间的含义

- **单项耗时**：后端发起该问题的模型请求，到收到并校验结果的实际时间，包括 API 到模型的通信开销。
- **总时间**：浏览器发起请求，到收到并解析完整结果的实际时间，包括鉴权、排队、网络与处理开销，因此通常大于各项耗时之和。
- **模型处理耗时合计**：模型服务返回的各项推理时间相加，不含浏览器网络与 API 排队时间。
- **示例回放**：每项标记“未推理”，只显示实际读取示例的总时间；不伪造模型耗时。

官方批处理只提供整批耗时，不能准确分摊到每个问题。界面设置 `measure_decisions: true`，在同一次浏览器请求内依次调用每个问题以获取真实计时；它可能比共享前缀的批量推理更慢。直接调用 API 时省略该参数或设置 `false`，仍使用原来的批处理，不提供单项计时。工作台和工具调用守卫使用同一规则。

## 运行真实模型

在另一终端运行：

```bash
bash scripts/serve_model.sh
```

脚本安装可选模型依赖，启动官方 `strands-decider serve`，默认配置：

| 配置 | 默认值 |
| --- | --- |
| 检查点 | `StrandsAgents/strands-decider-2B-hobson-v19` |
| 设备 | `cpu` |
| 模型地址 | `http://127.0.0.1:8099` |
| 严格上下文窗口 | 开启；超长输入返回错误 |
| CPU 线程 | `OMP_NUM_THREADS=4` |

首次启动需要访问 Hugging Face，下载约 4.5 GB 的 Qwen3.5-2B 基座权重以及 Decider 适配器。权重缓存在 Hugging Face 默认缓存目录，不放进项目。模型加载完成后，页面右上角点击刷新连接，再切换到「真实模型」。

可覆盖设备、检查点和端口：

```bash
# Apple silicon；需满足 PyTorch MPS 运行条件
DECIDER_DEVICE=mps bash scripts/serve_model.sh

# NVIDIA GPU；需要相应 CUDA 运行环境
DECIDER_DEVICE=cuda bash scripts/serve_model.sh

# 官方仓库目前也发布了 v21；本演示默认保留博客里的 v19
DECIDER_MODEL=StrandsAgents/strands-decider-2B-hobson-v21 bash scripts/serve_model.sh
```

可连接另一台机器上的官方模型服务：

```bash
STRANDS_DECIDER_URL=http://your-model-host:8099 \
DECIDER_TIMEOUT=180 \
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`.env.example` 列出了配置项；通过 shell 导出，或给 uvicorn 添加 `--env-file .env`。模型脚本读取 shell 环境变量。推理请求只发往服务端配置的地址。官方模型引擎使用可变推理状态，本后端串行访问它；请保持单个 Web worker，避免多个进程同时访问同一模型服务。

模型依赖固定到官方源码提交 [`63d24ae`](https://github.com/strands-labs/strands-decider/commit/63d24ae286e50105fba0bd1db15b0e243aea4650)，因为 PyPI `0.1.0` 缺少这里使用的 `--strict-window`。同时固定官方文档验证过的 Torch / Transformers / PEFT 版本，并提交 `uv.lock`。选择其他设备时可能需要额外安装相应内核；详见[官方推理说明](https://github.com/strands-labs/strands-decider/blob/main/docs/inference.md)。

## 演示路线

场景支持按分类筛选，或搜索 `RAG`、`退款`、`ECS` 等关键词。选中场景后会显示用途说明和“试一试”提示；修改输入后切换到真实模型观察变化。

| 分类 | 场景 | 演示重点 |
| --- | --- | --- |
| 业务运营 | 客服工单分流 | 负责团队、紧急程度、客户情绪 |
| 业务运营 | 退款资格审核 | 退货条件、金额审批、下一步流程 |
| 业务运营 | 销售线索优先级 | 购买意向、上线时间、跟进方式 |
| Agent 流程 | Agent 工具选择 | 工具路由、必要参数是否缺失 |
| Agent 流程 | RAG 回答依据 | 现有证据是否足够、是否继续检索 |
| Agent 流程 | 工具操作审批 | 工具与用户意图是否一致、写操作授权、只读重新规划 |
| 内容理解 | 评论情感分析 | 情感量表、推荐意愿 |
| 内容理解 | 多语言识别 | 在自定义语言候选项中选择 |
| 内容理解 | 社区内容审核 | 区分正常负面评价与促销内容 |
| 内容理解 | 摘要质量检查 | 事实一致性、忠实度、重写建议 |
| 数据与运维 | 发票字段校验 | 单据类型、采购单号要求、处理条件 |
| 数据与运维 | 运维告警分级 | ECS / ALB 示例信号、客户影响、值班通知判断 |

场景输入和示例结果均为演示数据。所有场景只展示判断，不执行退款、SQL 或 AWS 操作。真实输出可能与预设分布不同；预设概率不是模型的准确率或实际运行结果。

推荐先尝试：

1. 在「客服工单分流」点击运行：同一个状态同时得到部门选择、紧急程度判断和挫败程度评分。
2. 切换到「JSON 响应」，观察三个答案分别带有 `choice`、`noul` 和 `score` 字段。
3. 连接模型后修改上下文，或添加自定义问题，再用真实模式运行。选项编辑区接受 JSON 对象（Choice/Noul）或从低到高的 JSON 数组（Score）。
4. 进入「工具调用守卫」，先运行「缺少城市」：Agent 猜测 Seattle，策略应倾向 `Guide`。
5. 切换「已提供城市」：模型重新检查，策略可能允许 `Proceed`。实际行为由返回概率和所设阈值决定。
6. 查看「运行记录」，导出本次实验的输入和输出。

**几个概念：**

- `noul` 返回 `P(true)`，不是额外的 confidence。接近 0.5 表示不确定。
- Choice confidence 使用 `(N × p_max − 1) / (N − 1)`，不等于最高选项概率。
- Score 是有序等级索引的期望值，confidence 反映概率分布的集中程度。
- `Guide` / `Proceed` 是 Python 策略的结果，Decider 只给出判断概率。
- Web 守卫演示检查拟议工具调用，**不执行天气工具，也不调用 Agent LLM**。0.45 是博客案例使用的实验阈值，不是通用保证。

## 可选：接入真正的 Strands Agent

`examples/strands_agent.py` 将同一套问题和策略接到 `InterventionHandler.before_tool_call`。它需要已启动的 Decider，以及有 Bedrock 模型访问权限的 AWS 凭据。Agent LLM 调用可能产生 Bedrock 费用；天气工具返回的是明确标注的示例天气。

```bash
uv run --with strands-agents python -m examples.strands_agent

# 可根据自己的 AWS 区域/账户修改 Bedrock 模型
uv run --with strands-agents python -m examples.strands_agent \
  --model us.anthropic.claude-haiku-4-5-20251001-v1:0 \
  --message "What's the weather in Seattle?"
```

这是可选接入样例；本项目的验证覆盖了本地模型与 Web 守卫，未调用 Bedrock 来验证完整 Agent 循环。

## API

交互式文档：http://localhost:8000/api/docs （先在同一浏览器登录）。

除登录、进程存活和就绪探针外，所有 API 都需要有效会话。POST 请求还需 `X-Decider-Client: web`；浏览器请求会校验 Origin。没有公共注册接口。

| 接口 | 用途 |
| --- | --- |
| `POST /api/auth/login` | 校验用户名和密码，设置会话 Cookie |
| `GET /api/auth/me` | 返回当前用户名和会话到期时间 |
| `POST /api/auth/logout` | 服务端撤销会话并清除 Cookie |
| `GET /api/health` | 检查真实模型连接、模型名称与设备 |
| `GET /api/examples` | 获取 12 个场景的分类、说明、修改提示、上下文和问题 |
| `POST /api/decide` | 示例回放或官方 System One 推理 |
| `POST /api/guard` | 执行两项工具检查并返回策略结果 |

真实请求示例：

```bash
umask 077
curl --fail http://localhost:8000/api/auth/login \
  -c cookies.txt \
  -H 'X-Decider-Client: web' \
  -H 'Content-Type: application/json' \
  --data-binary @.deployment/local-credentials.json

curl http://localhost:8000/api/decide \
  -b cookies.txt \
  -H 'X-Decider-Client: web' \
  -H 'Content-Type: application/json' \
  -d '{
    "mode": "live",
    "measure_decisions": true,
    "state": "Help! My payouts have been failing for 3 days!",
    "questions": {
      "department": {
        "type": "choice",
        "instructions": "Which team should handle this?",
        "criteria": {"billing": "Payments and invoices", "sales": "New purchases"}
      },
      "is_urgent": {"type": "noul", "instructions": "Does this convey urgency?"}
    }
  }'
```

真实结果的 `timings` 包含 `execution`（`individual` / `batch`）、`decisions_ms`（按问题 ID）、`queue_ms`、`processing_ms`、`backend_total_ms`。其中后端总时间包含等待推理槽位的时间；`round_trip_ms` 保留为处理阶段的耗时。浏览器另外记录 `timings.client_total_ms`，用于界面总时间、运行记录和导出。示例及批处理的 `decisions_ms` 为 `null`，不会用平均值代替实测值。

## 验证

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check app tests examples scripts
node --check frontend/static/app.js   # 可选 JavaScript 语法检查
```

测试覆盖：登录与 API 访问控制、Cookie 属性、退出撤销、会话过期、账号禁用与密码重置、跨站请求、持久化限流，以及三种协议、错误处理、守卫边界、逐项计时与排队合计、整次运行超时、并发运行保持问题连续执行。

浏览器端检查（需要已启动的 Web 服务）：

```bash
uv run --with playwright playwright install chromium
uv run --with playwright python scripts/check_browser.py --credentials .deployment/local-credentials.json
# 同时验证一次真实模型推理：
# uv run --with playwright python scripts/check_browser.py --credentials .deployment/local-credentials.json --live
# 如需使用已经安装的 Chromium：
# CHROMIUM_PATH=/path/to/chrome uv run --with playwright python scripts/check_browser.py --credentials .deployment/local-credentials.json

# 逐个验证新增场景的真实推理，保存实际输出与耗时
uv run python -m scripts.check_scenarios \
  --credentials .deployment/local-credentials.json \
  --ids refund leads moderation invoice incident rag approval summary \
  --output .deployment/scenarios-local.json
```

`check_scenarios` 验证输入可执行、响应结构和计时完整性，不以预设答案判定模型准确率。省略 `--ids` 可运行全部场景；指定 `--url` 可验证 AWS 环境。

早期批处理验证中，本机 ARM64 CPU 运行 v19 的客服样例三个问题约 4.9 秒、天气守卫约 4.8 秒。它们不代表逐项计时模式的耗时，也不是性能保证；设备、输入长度、问题数量和热身状态都会改变耗时。

## 项目结构

```text
app/
  main.py            # FastAPI、协议校验、官方服务代理
  auth.py            # scrypt 密码、可撤销会话、DynamoDB / SQLite
  schemas.py         # 输入模型与限制
  examples.py        # 明确标注的预设数据、守卫问题
  policy.py          # 工具调用状态与 Guide / Proceed 策略
frontend/            # 独立中文 Web 界面，可直接发布到 S3
  index.html
  static/
deployment/          # CloudFormation、Docker、离线模型打包与部署脚本
examples/
  strands_agent.py   # 可选 Bedrock + Strands Agent 接入
scripts/
  serve_model.sh     # 启动官方模型服务
  check_browser.py   # 浏览器交互检查
  check_scenarios.py # 真实场景执行、结果结构与逐项计时检查
  manage_users.py    # 创建、重置、停用账号（无公共注册接口）
tests/
  test_api.py        # 后端协议、错误与策略测试
  test_auth.py       # 认证、会话、限流与 CSRF 测试
  test_timings.py    # 逐项计时、合计、排队、超时与并发测试
```

模型与演示面向实验用途。页面字体优先使用在线字体，无法联网时自动使用系统字体。浏览器运行记录会保存输入文本，可在「运行记录」中清空。模型说明与权重以[官方仓库](https://github.com/strands-labs/strands-decider)为准；本项目不是官方产品。
