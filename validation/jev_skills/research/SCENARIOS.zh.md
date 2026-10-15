# 108 个场景完整索引

[研究结论](README.zh.md) · [原页面固定版本](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md)

按原页编号逐项保留输入输出与技能映射。“原页状态”是上游作者对其证据的自述，不是我们新完成了 108 项测试。补充来源见 [37 个入口核对](SCENARIO_SOURCES.zh.md)。本项目此前只验证共享模板及反例，不能推算全部 108 条工作流已通过。

以下输入输出和状态节录自 MIT 授权的 jev-skill；保留[原项目许可](UPSTREAM_LICENSE)。

| # | 场景 / 原文 | 技能 | 输入 → 输出 | 原页状态 |
| ---: | --- | --- | --- | --- |
| 1 | [检查长程任务有没有跑偏](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-a01) | jev | 目标、验收项、最近结果、拟做动作 → 是否直接推进目标。 | 延伸配方；这个具体场景尚未单独评估。 |
| 2 | [从反复失败的循环里脱困](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-a02) | jev | 带退出码的尝试记录、输入变化 → 恢复路线。 | 下方展示合成输入的真实 API 返回；尚未评估这条工作流的端到端效果。 |
| 3 | [检查任务是否真的完成](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-a06) | jev-eval | 验收项、产物 ID、测试回执、版本 → 逐项证据支持度。 | 下方展示合成输入的真实 API 返回；尚未评估这条工作流的端到端效果。 |
| 4 | [拦住没有证据的“已完成”表述](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-a07) | jev-eval | 拟发汇报、独立执行记录 → 哪些成功表述缺乏支持。 | 延伸配方；这个具体场景尚未单独评估。 |
| 5 | [复盘一次 agent 失败发生在哪里](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-a27) | jev | 失败轨迹、步骤 ID、错误和参与者 → 步骤／参与者／失败类别。 | 延伸配方；这个具体场景尚未单独评估。 |
| 6 | [核对计划和实际调用是否一致](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-a03) | jev-eval | 眼前计划、完整调用及参数 → 语义上一致或不一致。 | 延伸配方；这个具体场景尚未单独评估。 |
| 7 | [发现削弱测试、刷通过的修复](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-a08) | jev-eval | 原始需求、测试意图、前后 diff → 是否削弱必要检查。 | [真实合成示例](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/evals/SCENARIO_EXAMPLES.md)：削弱测试命题为 0.97；不是端到端审查基准。 |
| 8 | [检查项目约定和语义规则](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-a09) | jev-eval | 明确规则、例外、相关代码 → 可能违反／不违反／证据不足。 | 延伸配方；这个具体场景尚未单独评估。 |
| 9 | [给即将执行的动作分风险类](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-a10) | jev | 命令、目标环境、授权证据、回滚事实 → 风险类别。 | 延伸配方；这个具体场景尚未单独评估。 |
| 10 | [标出工具结果里的诱导指令](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-a11) | jev-eval | 原任务、明确隔离的不可信网页或日志 → 是否有指令重定向企图。 | 延伸配方；这个具体场景尚未单独评估。 |
| 11 | [给代码审查排优先级](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-a12) | jev-eval | diff 块、文件职责、相关测试 → 分块风险分数和审查顺序。 | 延伸配方；这个具体场景尚未单独评估。 |
| 12 | [判断工具返回是否真正有用](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-a13) | jev-eval | 预期结果形状、实际返回、工具状态 → 可用／错误／缺信息／拒绝。 | 延伸配方；这个具体场景尚未单独评估。 |
| 13 | [匿名比较几个候选答案](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-h14) | jev-eval | 问题、独立证据、匿名候选答案 → 有锚点的评分和分歧。 | 延伸配方；这个具体场景尚未单独评估。 |
| 14 | [把 Jev 用作可重复的评测裁判](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-judge) | jev-eval | 轨迹/答案、固定标准 → 类型化标签或分数 → 评测统计。 | 已记录 LangChain 研究；调研中尚未找到 Ori 的准确实验材料，本次没有新增裁判基准实验。 |
| 15 | [用户不在时选择还能继续的工作](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-a04) | jev | 预授权队列、依赖状态、实际可用动作 → 下一步或等待。 | 延伸配方；这个具体场景尚未单独评估。 |
| 16 | [决定查证、升级模型还是交给人](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-a05) | jev | 问题、已尝试方法、缺失事实、审阅选项 → 查证／强模型／人工。 | 延伸配方；这个具体场景尚未单独评估。 |
| 17 | [决定子 agent 的消息何时打断主任务](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-a14) | jev-eval | 子任务目标、汇报、证据 ID、主任务状态 → 即刻处理／延后／重复／核验。 | 延伸配方；这个具体场景尚未单独评估。 |
| 18 | [选择下一步该用哪个工具](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-a15) | jev | 子目标、观察、实际工具说明和可用性 → 工具 ID 或无匹配。 | 延伸配方；这个具体场景尚未单独评估。 |
| 19 | [按任务选择模型档位](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-a16) | jev | 任务、模态要求、时延成本、能力卡 → 模型档位或无法路由。 | 下方展示合成输入的真实 API 返回；尚未评估这条工作流的端到端效果。 |
| 20 | [把子任务交给合适的专家](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-a17) | jev | 有界子任务、专家职责和排除项 → 专家 ID 或留在本地。 | 延伸配方；这个具体场景尚未单独评估。 |
| 21 | [从很多技能里挑需要加载的几个](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-a18) | jev | 任务、技能简介、必触发规则 → 可选技能相关性或无合适技能。 | 延伸配方；这个具体场景尚未单独评估。 |
| 22 | [给搜索或 RAG 结果重新排序](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-a19) | jev-documents | 查询、已有文档/段落及 ID → 相关性概率、排序或待复核项。 | 延伸配方；这个具体场景尚未单独评估。 |
| 23 | [在代码库里找功能入口](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-a20) | jev-documents | 问题、真实目录/符号/摘要 → 下一处值得读取的路径。 | 下方展示合成输入的真实 API 返回；尚未评估这条工作流的端到端效果。 |
| 24 | [压缩工具输出，但保留找回原文的能力](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-a21) | jev | 当前子目标、带 ID 的输出块 → 保留建议和相关性分数。 | [真实合成示例](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/evals/SCENARIO_EXAMPLES.md)：需要故障块、不需要主题备注；未执行上下文改写。 |
| 25 | [避免重复读取没有变化的信息](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-a22) | jev | 拟读操作、上次结果、参数、状态版本 → 是否可能冗余。 | 延伸配方；这个具体场景尚未单独评估。 |
| 26 | [根据任务边界和上下文压力决定何时压缩](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-compaction) | jev | 完成度、工作形态判断 + 宿主统计的上下文用量 → 提示或已授权的压缩。 | 上游描述了小规模/私有标签调试；本仓库上下文例子返回 ongoing，没有实际压缩。 |
| 27 | [决定浏览器下一步点哪里](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-a23) | jev-act | 最新 DOM/无障碍文本、目标、真实动作 ID → 下一步操作。 | [真实合成示例](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/evals/SCENARIO_EXAMPLES.md)：选出 `open_policy`，未执行浏览器动作；Ultrafast 速度来自作者演示。 |
| 28 | [网页没反应时判断等待还是介入](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-a24) | jev-act | 加载状态、错误、上一动作、等待记录 → 等待／查错／交接。 | 延伸配方；这个具体场景尚未单独评估。 |
| 29 | [核验网页动作的真实结果](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-a25) | jev-act | 最新页面回读、明确清单 → 每项是否被观察支持。 | 延伸配方；这个具体场景尚未单独评估。 |
| 30 | [个人助理把消息交接给下一条工作流](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-a26) | jev | 消息、当前任务、后续工具所需数据 → 工作流分支或澄清。 | 延伸配方；这个具体场景尚未单独评估。 |
| 31 | [解析智能家居的低风险指令](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-h26) | jev-act | 用户请求、可见设备、允许动作 → 意图、目标和是否完整。 | 延伸配方；这个具体场景尚未单独评估。 |
| 32 | [把观察变成可复用的“当前状态”](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-situations) | jev | 观察 → 具名情境概率 → 多条确定性自动化。 | 来源描述了这种方法；这里的改编尚未运行。 |
| 33 | [边说边判断浏览器操作是否完整](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-voice-browser) | jev-act | 语音转写、最新 UI、候选片段 → 意图、目标、完整性 → 操作或等待。 | 来源描述了这种方法；这里的改编尚未运行。 |
| 34 | [直接选网站工具，少走一长串点击](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-webmcp) | jev-act | 任务、网站实际工具 → 选工具 → 生成参数 → 执行与核验。 | 上游按每题三次多数成功统计为 49/49 题，实际 141/147 次成功；本仓库未复现，也不是只改接口的严格消融。 |
| 35 | [只给一个操作加判断，不必做完整 agent](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-primitive) | jev-act | 单次观察、操作内候选 → act／observe／extract 内部的局部选择。 | 作者描述；本仓库未安装 Stagehand 集成或测其耗时。 |
| 36 | [让表单根据回答选择下一问](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-forms) | jev-act | 部分表单、允许的问题 → 下一问 ID → 表单渲染器。 | 作者帖子摘录；未检查完整应用代码或复现表单。 |
| 37 | [在桌面应用里选择下一步控件](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-desktop) | jev-act | 真实控件、允许操作 → 操作/目标 → 宿主 CUA 执行。 | 上游提供集成样例而非受控加速实验；我们的 UI 冒烟是合成网页，不是这个桌面流程。 |
| 38 | [在网页里按意思找，而不只是匹配关键词](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-semantic-find) | jev-documents | 查询、带 ID 的页面文本块及相邻上下文 → 各块相关性，保留无匹配结果。 | 作者演示，未在这里安装扩展。这是语义检索，不是替换精确字符串搜索。 |
| 39 | [标出视频里的赞助口播](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-sponsor-skip) | jev-triage | 字幕行、ID 和前后文 → 是否推广、起止行 ID；时间戳由代码处理。 | 已读原项目 README，未运行扩展；上游的模型和可选转写服务需另行配置。 |
| 40 | [给客服工单分流](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-h02) | jev-triage | 工单、产品背景、队列定义 → 建议队列或待复核。 | [真实合成示例](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/evals/SCENARIO_EXAMPLES.md)：故障队列、紧急分 1.29/2；未测批量路由。 |
| 41 | [按紧急程度排列待办和故障](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-h03) | jev-triage | 报告的影响、受阻流程、事件规则 → 有锚点的紧急分数。 | 延伸配方；这个具体场景尚未单独评估。 |
| 42 | [预筛聊天记录里的未解决问题](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-h15) | jev-triage | 授权且脱敏的对话、明确关注点 → 需进一步审阅的会话。 | 延伸配方；这个具体场景尚未单独评估。 |
| 43 | [识别明确的取消或流失信号](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-h16) | jev-triage | 消息、必要的相关历史 → 具体取消意向命题概率。 | 延伸配方；这个具体场景尚未单独评估。 |
| 44 | [从销售或客服对话整理下一步](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-h17) | jev-triage | 通话记录、承诺、允许的跟进类型 → 待确认行动列表。 | 延伸配方；这个具体场景尚未单独评估。 |
| 45 | [给安全事件初步分诊](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-h18) | jev-triage | 脱敏事件、明确升级策略 → 调查类别和待复核项。 | 延伸配方；这个具体场景尚未单独评估。 |
| 46 | [筛可疑邮件和消息](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-h19) | jev-triage | 正文、显示的发送者、可见链接信息 → 可疑命题概率。 | 延伸配方；这个具体场景尚未单独评估。 |
| 47 | [把联系表单分给正确团队](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-h20) | jev-triage | 联系表单、咨询类别定义 → 队列标签或草稿处理建议。 | 延伸配方；这个具体场景尚未单独评估。 |
| 48 | [从消息里整理日程候选](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-h24) | jev-triage | 授权消息、日程相关标准 → 事件候选及类别。 | 延伸配方；这个具体场景尚未单独评估。 |
| 49 | [自己写邮件标签和处理规则](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-mail-rules) | jev-triage | 邮件、可编辑类别 → 多标签命中 → 标签或复核队列。 | 来源描述了这种方法；这里的改编尚未运行。 |
| 50 | [按自己的兴趣筛研究流和社交内容](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-personal-feed) | jev-triage | 已观察帖子、个人 rubric → 保存判断 → 可撤销排序或隐藏。 | 作者帖子摘录；本仓库未安装信息流集成。 |
| 51 | [初筛论文和阅读清单](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-h07) | jev-documents | 标题、摘要、纳入条件 → 逐项满足程度与阅读优先级。 | 延伸配方；这个具体场景尚未单独评估。 |
| 52 | [检查一句主张有没有原文支持](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-h08) | jev-documents | 准确主张、可定位的原文 → 支持／矛盾／未知。 | 延伸配方；这个具体场景尚未单独评估。 |
| 53 | [把政策要求做成可复核清单](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-h09) | jev-documents | 当前适用规则、材料摘录 → 审阅矩阵。 | 延伸配方；这个具体场景尚未单独评估。 |
| 54 | [把合同条款整理给审核人](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-h10) | jev-documents | 条款原文、审核人给定类别 → 分组后的条款清单。 | 延伸配方；这个具体场景尚未单独评估。 |
| 55 | [按品牌和编辑规则检查文案](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-h11) | jev-eval | 草稿、明确编辑规则 → 逐条风险标记。 | 延伸配方；这个具体场景尚未单独评估。 |
| 56 | [帮求职者整理岗位要求的证据](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-h21) | jev-documents | 本人授权的简历、与工作相关的要求 → 证据位置与覆盖情况。 | 延伸配方；这个具体场景尚未单独评估。 |
| 57 | [选出正确的原始字段值](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-spans) | jev-documents | 候选片段、字段角色 → 片段 ID 或无匹配 → 复制原值。 | [真实合成示例](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/evals/SCENARIO_EXAMPLES.md)：选出 s2（0.97），同时指出主张与原文矛盾；未测 OCR 或检索。 |
| 58 | [别把“最像”当成“真的有答案”](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-suitability) | jev-documents | 问题、候选 → 相对最优项 + 独立的是否存在合适答案判断。 | 来源描述了这种方法；这里的改编尚未运行。 |
| 59 | [把散乱文本恢复成标题、列表和段落](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-structure) | jev-documents | 逐行连续性判断 → 代码合块 → 块类型和属性 → 渲染。 | 来源描述了这种方法；这里的改编尚未运行。 |
| 60 | [理解日期表达，再交给代码算日期](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-dates) | jev-documents | 日期表达 → 绝对/相对日期部件 → 确定性日历解析。 | 来源描述了这种方法；这里的改编尚未运行。 |
| 61 | [复核小模型提取的结构化数据](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-extraction-cascade) | jev-documents | 生成字段、独立原文 → 逐字段判断 → 有界修复或复核。 | 来源描述了这种方法；这里的改编尚未运行。 |
| 62 | [给演讲、访谈、展示做逐段批注](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-transcript) | jev-documents | 转写单元、上下文 → 独立 rubric 概率 → 批注或时间线。 | 来源描述了这种方法；这里的改编尚未运行。 |
| 63 | [像 grep 一样按语义找日志或笔记](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-h01) | jev-triage | 编号文本块、具体检索条件 → 逐块匹配概率与候选清单。 | 延伸配方；这个具体场景尚未单独评估。 |
| 64 | [给商品或内容分层归类](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-h04) | jev-triage | 描述、分类树、候选定义 → 类别路径或其他。 | 延伸配方；这个具体场景尚未单独评估。 |
| 65 | [发现重复记录或同一实体](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-h05) | jev-documents | 两条记录、身份属性、来源 → 同实体概率和待确认项。 | 延伸配方；这个具体场景尚未单独评估。 |
| 66 | [给问卷和访谈做多标签编码](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-h06) | jev-triage | 单条回答、预定义编码本 → 独立主题标签及概率。 | 延伸配方；这个具体场景尚未单独评估。 |
| 67 | [给数据集记录做质量侧栏](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-h22) | jev-triage | 单条数据、用途 rubric → 分数和独立检查标签。 | 延伸配方；这个具体场景尚未单独评估。 |
| 68 | [沿知识图谱或大分类树逐步寻找](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-graph) | jev-documents | 当前节点、邻居描述 → 局部选择 → 有限搜索前沿。 | 来源描述了这种方法；这里的改编尚未运行。 |
| 69 | [给传统机器学习模型制作语义特征](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-features) | jev-triage | 候选问题 → 标注记录的数值特征 → 监督学习器 → 开发集误差反馈。 | 来源描述了这种方法；这里的改编尚未运行。 |
| 70 | [JSON 格式正确以后，再检查含义](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-semantic-validation) | jev-eval | 结构合法的数据、语义规则 → 每条满足／疑点／未知／不可用。 | 来源描述了这种方法；这里的改编尚未运行。 |
| 71 | [从已有命令历史里选合适的建议](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-shell-history) | jev-documents | 已有命令候选、当前上下文 → 命令建议。 | 来源描述了这种方法；这里的改编尚未运行。 |
| 72 | [在普通查询旁边加语义筛选](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-semantic-sql) | jev-triage | 确定性查询 → 选定字段 → 语义判断 → 过滤、分组或排序。 | 来源描述了这种方法；这里的改编尚未运行。 |
| 73 | [让表格列名变成可修改的语义规则](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-spreadsheet) | jev-eval | 可编辑列含义、行文本 → 评分标准 → 每行分数。 | 作者帖子摘录；本仓库未测试表格 UI 或批量准确率。 |
| 74 | [用市场回放研究决策与过期处理](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-market-replay) | jev-act | 历史/合成快照 → 有界决策 → dry-run 模拟器与回执记录。 | 作者演示与 README 的 mock/dry-run 默认模式分别记录；未连接钱包、未运行交易。 |
| 75 | [让游戏 NPC 从合法动作里作选择](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-a28) | jev-act | 可见世界、角色准则、合法动作 → 下一步动作。 | [真实合成示例](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/evals/SCENARIO_EXAMPLES.md)：检查仓库；未运行状态更新或测胜率。 |
| 76 | [按自己的标准做想法工作坊](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-h25) | jev-eval | 想法、本人定义的分级标准 → 多维评分。 | 下方展示合成输入的真实 API 返回；尚未评估这条工作流的端到端效果。 |
| 77 | [给内容选文档组件，给界面选图表或表格](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-h28) | jev-act | 结构化内容、受众、组件定义 → 组件 ID。 | 延伸配方；这个具体场景尚未单独评估。 |
| 78 | [一次测维度，随时改自己的权重](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-reweight) | jev | 独立维度判断 → 保存特征向量 → 用户权重生成排序。 | 来源描述了这种方法；这里的改编尚未运行。 |
| 79 | [世界设计、动作选择、视频呈现分开接](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-world-video) | jev-act | 世界规则 → 状态和合法动作 → 决策 → 模拟器 → 可选图像或视频。 | 作者报告约五分钟生成 264 个片段；不是本仓库复现，也不足以确定恰好调用了 264 次 API。 |
| 80 | [大模型定策略，Jev 高频选局部动作](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-strategy) | jev-act | 低频策略 → 高频局部动作 → 新状态 → 重规划触发。 | 作者演示；本仓库没有复现长程成功率。 |
| 81 | [给多个聊天角色排发言顺序](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-speakers) | jev-act | 对话状态、允许发言的角色 → 角色/回应模式 ID → 台词生成。 | 本仓库角色/语气联合调用选出 analyst + calm，完整摘录见下一场景。 |
| 82 | [给剧本或播报选择 TTS 语气](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-tts) | jev-act | 剧本、表达 rubric → 语气标签 → TTS 预设；声音由其他工具生成。 | [真实合成示例](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/evals/SCENARIO_EXAMPLES.md)：analyst + calm；没有生成语音。 |
| 83 | [让模拟谈判有退出条件，不原地打转](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-negotiation) | jev-act | 报价历史、合法选项 → 局部回应 → 宿主检查进度与死锁。 | 来源报告了谈判停滞；这里是根据失败设计的改编，不是已经证明有效的修复。 |
| 84 | [按创作要求选图片或视频模型](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-creative-route) | jev | 创作需求、当前能力卡 → 生成器 ID 或无匹配。 | 作者帖子摘录；没有复现生成或成品质量对照。 |
| 85 | [持续检查角色扮演有没有偏离人设和世界观](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-story-sensors) | jev-act | 角色卡、世界规则、最近几段剧情 → 多个独立等级评分，跨轮次观察变化。 | 作者报告，尚未复现；Jev 监测，大模型写剧情。评分不是校准后的正确率。 |
| 86 | [通过选择音乐部件，编排可编辑的 MIDI](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-midi) | jev-act | 音乐要求、和声计划、动机、最近小节 → 有限音乐选择 → 可编辑音符。 | 已看 README 和视频预览，未运行应用。Jev 选择符号化音乐部件，不生成音频；上游也有模拟模式。 |
| 87 | [用一句需求生成可编辑的判断问题](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-compile) | jev | 用户需求 → 模型起草问题 → schema 和标准复核 → Jev 逐条判断。 | 来源描述了这种方法；这里的改编尚未运行。 |
| 88 | [通过 MCP 给现有 agent 增加判断工具](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-mcp) | jev | Agent 工具调用、状态和问题 → 类型化判断 → 已有宿主流程。 | 检查到的两个版本均支持 OpenRouter，本仓库未安装；先检查会改配置或存密钥的安装助手。 |
| 89 | [边改例子边学，再让 agent 写新例子](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-playground) | jev | 可编辑例子 → 替换输入 → 检查判断与下游行为。 | 已读原始 README，未运行界面；TypeSafe AI Playground 区分真实调用、mock 和本地求解器。 |
| 90 | [拿本地模型做同题决策对照](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-local-comparison) | jev-eval | 同一批评测样例 → 分开的模型成绩单、原始输出和错误分析。 | 已读适配器 README，未安装；它不是 Jev 权重或 RLCD 复现。本项目 CLI 仍走 OpenRouter，不会偷偷切换端点。 |
| 91 | [给社区审核队列分类](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-moderation) | jev-triage | 消息 + 频道规则 → 允许 / 复核 / 疑似违规 → 管理员队列。 | 汇总或原帖线索；尚未核实原始实现。 |
| 92 | [给代码做语义高亮](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-syntax) | jev-triage | 代码片段 + 语言提示 + token 类别 → 片段标签 → 高亮渲染器。 | 已读作者原帖文字；用法为改编，未复现。 |
| 93 | [研究 AI 文本风格信号](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-ai-text) | jev-eval | 文本 + 可观察的风格标准 → 重复措辞 / 泛化结构 / 未知 → 供人审阅。 | 已读作者原帖文字；用法为改编，未复现。 |
| 94 | [给麦克风提供暂停建议](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-mute) | jev-act | 获同意的转写 + 明确会议规则 → 继续 / 建议暂停 / 复核 → 可见提示。 | 汇总或原帖线索；尚未核实原始实现。 |
| 95 | [根据意图排列启动器结果](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-launcher) | jev-documents | 输入意图 + 允许查看的近期文件或应用 → 候选 ID / none → 用户确认打开。 | 已读作者原帖文字；用法为改编，未复现。 |
| 96 | [试做带语义判断的编程语言](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-language) | jev | 程序状态 + 已定义的谓词或分支 → 类型化判断 → 解释器走受限分支。 | 已读作者原帖文字；用法为改编，未复现。 |
| 97 | [在画布里选择绘图动作](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-drawing) | jev-act | 文字化画面描述 + 可用图形、工具和目标 → 动作 ID → 宿主绘图工具。 | 汇总或原帖线索；尚未核实原始实现。 |
| 98 | [从固定候选里推荐 Emoji](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-emoji) | jev-act | 草稿 + 语气目标 + Emoji 候选描述 → Emoji ID / none → 可选插入。 | 已读作者原帖文字；用法为改编，未复现。 |
| 99 | [给剪贴板历史提供相关建议](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-clipboard) | jev-documents | 当前任务 + 明确允许读取的剪贴板条目 → 条目 ID / none → 本地预览。 | 汇总或原帖线索；尚未核实原始实现。 |
| 100 | [在模拟器里研究合成监测信号](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-vitals-demo) | jev-act | 合成信号摘要 + 仿真条件 → 演示状态 / unknown → 模拟器显示。 | 已读作者原帖文字；用法为改编，未复现。 |
| 101 | [实时选择视频特效](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-video-effects) | jev-act | 转写窗口 + 预设特效描述 → 特效 ID / none → 渲染器。 | 已读作者原帖文字；用法为改编，未复现。 |
| 102 | [通过颜色选择逐像素绘画](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-pixels) | jev-act | 场景描述 + 像素或区域坐标 + 色板 → 颜色 ID → JavaScript 绘制。 | 已读作者原帖文字；用法为改编，未复现。 |
| 103 | [给可编辑视频挑选片段](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-video-edit) | jev-act | 宿主提供的抽帧描述 + 素材 ID + 剪辑标准 → 开场 / 结尾 / 排序 → 剪辑时间线。 | 已读作者原帖文字；用法为改编，未复现。 |
| 104 | [选择下一个合法关卡片段](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-levels) | jev-act | 当前关卡状态 + 预验证的片段候选 → 片段 ID → 游戏引擎。 | 已读作者原帖文字；用法为改编，未复现。 |
| 105 | [批量拆解广告素材](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-ads) | jev-eval | 获准使用的广告文本 + 落地页证据 + 分类标准 → Hook / 形式 / Offer / CTA → 对比表。 | 已读作者原帖文字；用法为改编，未复现。 |
| 106 | [在物理仿真里选择受限动作](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-physics) | jev-act | 仿真遥测的文字摘要 + 合法控制 → 转向 / 推力 / 保持 → 仿真一步。 | 已读作者原帖文字；用法为改编，未复现。 |
| 107 | [批量整理和判定越狱评测](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-redteam-batch) | jev-eval | 获授权的已采集对话 + 待测边界 → 结果标签 + 证据状态 → 独立复核。 | 原创流程和离线样例；没有运行攻击任务或真实判分。 |
| 108 | [组织多人、多 Agent 与多轮安全评测](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md#sc-redteam-team) | jev-eval | 授权会话 + 完整轮次历史 + 预算 + 允许的下一步 → 继续 / 停止 / 复核 → 获授权的执行器。 | 原创流程和离线样例；没有运行攻击任务或真实判分。 |
