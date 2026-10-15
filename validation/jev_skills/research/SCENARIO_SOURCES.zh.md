# 场景补充来源与应用核对

[综合结论](README.zh.md) · [108 个场景](SCENARIOS.zh.md)

S01–S34 是原页面场景区额外直接链接；S35–S37 是从其中作者原帖进一步找到的实现。原帖是作者的陈述，本次未观看并核验所有视频、未运行应用。下面将读取事实、用途和不能推出的结论逐项列出。

## S01 · 11. 给代码审查排优先级

Blink 官网是编辑后检查团队约定的产品；不要与文件导航实验的功能混为一谈。首页所称半秒内反馈没有配套质量基准。

[原始入口](https://blink.review/) · [本次读取地址](https://blink.review/) · 状态 `source_fetched`


## S02 · 14. 把 Jev 用作可重复的评测裁判

OpenRouter Ori Eval 原帖报告裁判延迟优势；速度不等于正确率，不能把不同评测来源直接合并。

[原始入口](https://x.com/OpenRouter/status/2101412965765529853) · [本次读取地址](https://x.com/OpenRouter/status/2101412965765529853) · 状态 `source_fetched`


## S03 · 22. 给搜索或 RAG 结果重新排序

记忆检索的快速个人实验，原帖称减少 94% tokens、快 2–3 倍；没有证明长期任务效果不下降。

[原始入口](https://x.com/moritzkremb/status/2100566009312940457) · [本次读取地址](https://x.com/moritzkremb/status/2100566009312940457) · 状态 `source_fetched`


## S04 · 37. 在桌面应用里选择下一步控件

Jev + AXe 操作 iOS 模拟器，支持“可接动作循环”的演示；原帖没有可核验的准确率或倍数表。

[原始入口](https://x.com/camsoft2000/status/2100648648434434298) · [本次读取地址](https://x.com/camsoft2000/status/2100648648434434298) · 状态 `source_fetched`


## S05 · 38. 在网页里按意思找，而不只是匹配关键词

网页语义查找演示；进一步找到 Needle 的项目说明，见 S37。

[原始入口](https://x.com/Saboo_Shubham_/status/2101576462042366114) · [本次读取地址](https://x.com/Saboo_Shubham_/status/2101576462042366114) · 状态 `source_fetched`


## S06 · 57. 选出正确的原始字段值

官方原文字段抽取：正则找候选、模型选候选、代码复制并标准化；候选遗漏仍会造成漏提取。

[原始入口](https://docs.typesafe.ai/cookbooks/pre_parsed_value_extraction_cookbook) · [本次读取地址](https://docs.typesafe.ai/cookbooks/pre_parsed_value_extraction_cookbook) · 状态 `source_fetched`


## S07 · 58. 别把“最像”当成“真的有答案”

官方 semantic find：Choice 对 218 个行 ID 排序，同时用 Noul 检查存在答案；最高排名不自动代表适用。

[原始入口](https://docs.typesafe.ai/cookbooks/semantic_find) · [本次读取地址](https://docs.typesafe.ai/cookbooks/semantic_find) · 状态 `source_fetched`


## S08 · 59. 把散乱文本恢复成标题、列表和段落

官方格式恢复：先判断断行合并，再判块类型，两阶段有依赖；代码渲染 Markdown，避免改写原文。

[原始入口](https://docs.typesafe.ai/cookbooks/autoformat) · [本次读取地址](https://docs.typesafe.ai/cookbooks/autoformat) · 状态 `source_fetched`


## S09 · 60. 理解日期表达，再交给代码算日期

官方日期抽取：模型识别日期组成，代码完成日历运算和合法性检查；仅格式合法仍不能证明取对业务日期。

[原始入口](https://docs.typesafe.ai/cookbooks/date_extraction_cookbook) · [本次读取地址](https://docs.typesafe.ai/cookbooks/date_extraction_cookbook) · 状态 `source_fetched`


## S10 · 61. 复核小模型提取的结构化数据

官方提取级联：小模型先提取，Jev 逐字段核验，触发后交强模型；报告同时需要错误漏放与升级比例。

[原始入口](https://docs.typesafe.ai/cookbooks/sde_cascade) · [本次读取地址](https://docs.typesafe.ai/cookbooks/sde_cascade) · 状态 `source_fetched`


## S11 · 68. 沿知识图谱或大分类树逐步寻找

官方层次分类：树节点上的 Choice 配合 greedy/beam search，代码做路径搜索与长度归一化；要比较叶子正确率和总调用。

[原始入口](https://docs.typesafe.ai/cookbooks/hierarchical_classification) · [本次读取地址](https://docs.typesafe.ai/cookbooks/hierarchical_classification) · 状态 `source_fetched`


## S12 · 68. 沿知识图谱或大分类树逐步寻找

知识图谱原帖实际演示词语语义重要性评分和图构造；与“在既有图上搜索”相关但不是同一个任务。

[原始入口](https://x.com/yoheinakajima/status/2100674306405814568) · [本次读取地址](https://x.com/yoheinakajima/status/2100674306405814568) · 状态 `source_fetched`


## S13 · 69. 给传统机器学习模型制作语义特征

官方语义特征：LLM 提问题，Jev 转数值列，CatBoost 做监督学习；示例为 2,000 条酒评，需保持训练/留出分离。

[原始入口](https://docs.typesafe.ai/cookbooks/autoresearch_feature_discovery) · [本次读取地址](https://docs.typesafe.ai/cookbooks/autoresearch_feature_discovery) · 状态 `source_fetched`


## S14 · 80. 大模型定策略，Jev 高频选局部动作

Pac-Man 由 Astra 定策略、Jev 选动作；原帖强调早期实验，没有稳定游戏成绩。

[原始入口](https://x.com/daniel_mac8/status/2100335929273524541) · [本次读取地址](https://x.com/daniel_mac8/status/2100335929273524541) · 状态 `source_fetched`


## S15 · 81. 给多个聊天角色排发言顺序

日文原帖讨论聊天轮次、七种 TTS 情绪、状态与审核等用法，包含拟实现表述；不能全部算作已运行应用。

[原始入口](https://x.com/greenhill_pharm/status/2101492328137711891) · [本次读取地址](https://x.com/greenhill_pharm/status/2101492328137711891) · 状态 `source_fetched`


## S16 · 85. 持续检查角色扮演有没有偏离人设和世界观

Reddit 入口本次未能读取；同一主题的 ST-jeved 已按 X03 独立研究。

[原始入口](https://www.reddit.com/r/SillyTavernAI/comments/1wl7uje/jev_might_be_the_next_frontier_for_improving/) · [本次读取地址](https://www.reddit.com/r/SillyTavernAI/comments/1wl7uje/jev_might_be_the_next_frontier_for_improving/) · 状态 `source_unavailable`


## S17 · 86. 通过选择音乐部件，编排可编辑的 MIDI

Jevthoven 的视频附件未逐帧分析；音乐实现与实验材料按 P27 和此前 DEMO_PROJECTS 研究。

[原始入口](https://github.com/user-attachments/assets/176c69e4-501e-4b71-8517-957cc692882a) · [本次读取地址](https://github.com/user-attachments/assets/176c69e4-501e-4b71-8517-957cc692882a) · 状态 `video_not_transcribed`


## S18 · 87. 用一句需求生成可编辑的判断问题

OpenRouter Prompt to questions：Claude 转写问题，Jev 对每行判断；未登录页面只有初始零计数，不是性能结果。

[原始入口](https://openrouter.ai/labs/jev/compile) · [本次读取地址](https://openrouter.ai/labs/jev/compile) · 状态 `source_fetched`


## S19 · 90. 拿本地模型做同题决策对照

Reddit 入口本次未能读取；jevify 原仓库已按 P34 研究。

[原始入口](https://www.reddit.com/r/OpenSourceeAI/comments/1wl9m9n/jevify_super_simple_way_to_serve_llms_as_a/) · [本次读取地址](https://www.reddit.com/r/OpenSourceeAI/comments/1wl9m9n/jevify_super_simple_way_to_serve_llms_as_a/) · 状态 `source_unavailable`


## S20 · 91. 给社区审核队列分类

Discord 审核原帖带开源链接，进一步核对 S35；一键赦免是上下文示例反馈，不保证绝不误判。

[原始入口](https://x.com/brainstormity/status/2100471987860553931) · [本次读取地址](https://x.com/brainstormity/status/2100471987860553931) · 状态 `source_fetched`


## S21 · 92. 给代码做语义高亮

任意语言语义高亮演示；适合教学原型，颜色可显示不等于语法解析正确。

[原始入口](https://x.com/imarikchakma/status/2100587614927741435) · [本次读取地址](https://x.com/imarikchakma/status/2100587614927741435) · 状态 `source_fetched`


## S22 · 93. 研究 AI 文本风格信号

AI 文本检测原帖称大幅节费但缺少误报集与可复算比较；不能据此判断作者身份或不端。

[原始入口](https://x.com/Totzenberger/status/2100575503061004579) · [本次读取地址](https://x.com/Totzenberger/status/2100575503061004579) · 状态 `source_fetched`


## S23 · 94. 给麦克风提供暂停建议

麦克风自动静音的概念演示；原帖没有说明转写、判断准确率和延迟链路。原页改编成建议提示更易评估。

[原始入口](https://x.com/Sybuilds/status/2100417692096459074) · [本次读取地址](https://x.com/Sybuilds/status/2100417692096459074) · 状态 `source_fetched`


## S24 · 95. 根据意图排列启动器结果

意图启动器据任务和最近文件排序，原帖称约 100ms；需要与普通文件排序比较，并丢弃旧输入的响应。

[原始入口](https://x.com/dabit3/status/2100756930054504776) · [本次读取地址](https://x.com/dabit3/status/2100756930054504776) · 状态 `source_fetched`


## S25 · 95. 根据意图排列启动器结果

原帖实际是输入期间判断意图和参数、提前触发函数；原页的自动补全属于改编，不能写成同一实现。

[原始入口](https://x.com/miiura/status/2100615772053877164) · [本次读取地址](https://x.com/miiura/status/2100615772053877164) · 状态 `source_fetched`


## S26 · 97. 在画布里选择绘图动作

绘图动作原帖本次未能读取；只保留原页线索，不补造工具链或效果。

[原始入口](https://x.com/VladTerin/status/2100762694223618177) · [本次读取地址](https://x.com/VladTerin/status/2100762694223618177) · 状态 `source_unavailable`


## S27 · 98. 从固定候选里推荐 Emoji

Emoji 候选选择原帖称 100–200ms，3 与 200 个候选速度相近；只是作者演示，未证选择质量不变。

[原始入口](https://x.com/riku720720/status/2100705558512963602) · [本次读取地址](https://x.com/riku720720/status/2100705558512963602) · 状态 `source_fetched`


## S28 · 99. 给剪贴板历史提供相关建议

剪贴板历史结合当前应用/输入框上下文的个人玩具；“挺准”是主观描述，没有标注结果。

[原始入口](https://x.com/CoooolXyh/status/2101284346640654362) · [本次读取地址](https://x.com/CoooolXyh/status/2101284346640654362) · 状态 `source_fetched`


## S29 · 100. 在模拟器里研究合成监测信号

生命体征模拟的两种状态演示；没有临床测试，也没有完整灵敏度/特异度数据。

[原始入口](https://x.com/roiyaruRIZ/status/2101130711067431018) · [本次读取地址](https://x.com/roiyaruRIZ/status/2101130711067431018) · 状态 `source_fetched`


## S30 · 101. 实时选择视频特效

明确以文字转写选择预设视频特效；模型不直接处理像素，渲染与时间同步另有组件。

[原始入口](https://x.com/ponyo877/status/2101139914419290345) · [本次读取地址](https://x.com/ponyo877/status/2101139914419290345) · 状态 `source_fetched`


## S31 · 102. 通过颜色选择逐像素绘画

Jevinci 原帖明确 JavaScript 绘画、逐像素选色且视频 4 倍速；当前实现说明见 S36。

[原始入口](https://x.com/anshuc/status/2101040309522121072) · [本次读取地址](https://x.com/anshuc/status/2101040309522121072) · 状态 `source_fetched`


## S32 · 103. 给可编辑视频挑选片段

作者用 16 条滑雪素材的抽帧描述选择片段，再用 Computer Use 操作 CapCut，做出 16 秒混剪，称不到 5 分钟；额度变化非精确 token。

[原始入口](https://x.com/GeekCatX/status/2101223068580643172) · [本次读取地址](https://x.com/GeekCatX/status/2101223068580643172) · 状态 `source_fetched`


## S33 · 104. 选择下一个合法关卡片段

实时游戏关卡演示；没有证明所有关卡可达、可解，应由引擎独立校验。

[原始入口](https://x.com/HugoDuprez/status/2100953089003921543) · [本次读取地址](https://x.com/HugoDuprez/status/2100953089003921543) · 状态 `source_fetched`


## S34 · 106. 在物理仿真里选择受限动作

驾驶模拟原帖称一小时搭建；是开发演示，不是自动驾驶能力或车辆安全实测。

[原始入口](https://x.com/jpschroeder/status/2100347770867458384) · [本次读取地址](https://x.com/jpschroeder/status/2100347770867458384) · 状态 `source_fetched`


## S35 · Discord moderation bot

Discord Bot 有真实删除/超时动作、审计、反馈和故障放行设计；README 无误判率基准。赦免案例进上下文并非权重更新。

[原始入口](https://github.com/brainstormity/Jev-Moderation-Bot) · [本次读取地址](https://raw.githubusercontent.com/brainstormity/Jev-Moderation-Bot/325ea7f4ae889b666ca6133ddac0efcf2f1e7afc/README.md) · 状态 `source_fetched`
固定版本：`325ea7f4ae889b666ca6133ddac0efcf2f1e7afc`。

## S36 · Jevinci

Jevinci 当前 README 标题为 jev-paint：概率到颜色，再由确定性纹理算法绘制；HSL/RGB 通道组合假设独立，模型不提供联合分布。

[原始入口](https://github.com/achimala/jevinci) · [本次读取地址](https://raw.githubusercontent.com/achimala/jevinci/ecf9c48d290e086bde790d6e24b93324667155e9/README.md) · 状态 `source_fetched`
固定版本：`ecf9c48d290e086bde790d6e24b93324667155e9`。

## S37 · Needle semantic find

Needle 在网页原文中高亮语义相关句，使用 Vercel Gateway；0.58 为默认相关性阈值，未证明完整召回。不能直接搜索 Chrome 内置 PDF 阅读器。

[原始入口](https://github.com/Shubhamsaboo/awesome-llm-apps/tree/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/advanced_llm_apps/needle) · [本次读取地址](https://raw.githubusercontent.com/Shubhamsaboo/awesome-llm-apps/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/advanced_llm_apps/needle/README.md) · 状态 `source_fetched`
固定版本：`4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2`。

