# 决策模型与支付业务演示 · v5 EC2 部署版

最新版本见 [27 页 v6 优化流程实测版](../v6/README.md)，新增两页真实优化演示；本目录保留 25 页版本。

在最新 25 页 v4 上更新当前部署，保留原来的模型介绍、Jev / BERT 比较、支付流程、速度图表与结论。

- **[下载 PPTX](Strands-Decider-模型原理与支付业务演示-v5-EC2部署版-25页-20261011.pptx)**
- [查看 PDF](Strands-Decider-模型原理与支付业务演示-v5-EC2部署版-25页-20261011.pdf)
- [EC2 架构页预览](page-09-preview.png)
- [第 14 页审批差异解释](page-14-preview.png)
- [全部 25 页预览](slides-overview.png)
- [逐页讲稿与来源](讲稿与来源.md)
- [构建记录](build-manifest.json) · [渲染检查](render-audit.json)
- [上一版 v4](../v4/README.md)

## 本次修改

| 位置 | 更新内容 |
| --- | --- |
| 第 1 页 | 更新为 v5 EC2 部署版，日期 2026-10-11 |
| 第 9 页 | 重绘 AWS 架构：EC2 位于私有 VPC；API 经私网 HTTP 调用 ECS on EC2 模型服务；采用 AWS 官方图标 |
| 第 11 页 | Decider 托管位置改为 EC2，说明私网调用路径 |
| 第 12–22、24 页 | 删除重复的数据来源页脚；数值和原始图片保持不变，采集环境说明保留在备注中 |
| 第 14 页 | 补充“收款无需退款审批”的条件、两侧输出与耗时、Decider 候选评分、可能的字段干扰，以及审批通过不等于到账；详细解释见备注 |
| 第 23–24 页 | 将结论中的“本次观测”明确为历史观测 |
| 全部备注 | 同步当前 EC2 规格、常驻方式、网络、磁盘、费用与历史数据口径 |

当前模型部署为 **us-east-1 / EC2 On-Demand `g6.xlarge` / NVIDIA L4 24 GB**。模型服务运行于 ECS on EC2，业务 API 仍在 ECS Fargate。GPU 持续运行，不因闲置停止；正常推理直接调用，失败后才检查 GPU 状态。80 GB 加密 EBS 保存模型镜像与缓存。

前端继续使用私有 S3 + CloudFront OAC，S3 禁止公共访问；内网 ALB、Fargate API 和 EC2 模型服务均无公共入口。后端直接调用 Bedrock 与 DynamoDB，图中不单列 Runtime 或 VPC Endpoint 节点。SageMaker Endpoint 已释放、控制器已禁用，原配置保留作回退。当前实现见 [部署记录](../../../deployment/DEPLOYED.md) 和 [运维说明](../../../deployment/README.md)。

## 当前架构与历史实测

**当前架构更新不等于重新测速。** 本次没有重新调用模型，也没有将旧结果改标为 EC2 数据。

- PPT 的固定输入数据仍为 **2026-10-10 的 SageMaker `ml.g6.xlarge` / L4** 采集：19 组成功配对，Decider 1.810 s、GPT 22.068 s；另有一次 GPT 读取超时。
- 反馈执行的数据和截图仍来自同日采集：USDC 每侧 6 次决策，退款每侧 9 次决策。后续输入可能不同，不合入同输入速度统计。
- 采集日期、迁移前环境和原 SageMaker 实例类型保留在备注与讲稿中，不再作为重复页脚显示。第 9 页单独说明当前 EC2 架构。
- 已有 2026-10-11 EC2 验收结果记录于部署文档，未混入上述历史图表，也没有据此宣称部署迁移带来固定性能倍数。
- 第 14 页只重新组织解释，耗时与候选概率仍取自原始实测。退款字段可能干扰判断属于待验证假设，不能从模型输出确认内部原因；没有据此宣称 GPT 总能正确判断。

来源：[固定输入数据](../../results/benchmark-2026-10-10.json)、[反馈执行数据](../v2/loop-observations.json)、[原始截图记录](../v2/capture-manifest.json)。Jev 仅作背景介绍，BERT 未参与性能实测；官方材料核对记录见 [source-manifest.json](source-manifest.json)。

保留 **25 页**；BERT 一页，反馈执行两页，不新增 GPU 启停操作提示。Demo / Repo 地址和二维码继续保留，旧 v4 PPT/PDF 不覆盖。

## 演示入口

- Demo：https://d3i7ogfx5ml7dc.cloudfront.net/#crypto
- Repo：https://github.com/milan9527/StrandsDecider

演示需要现有账号；仓库需要访问权限。文件不包含密码或访问令牌；对应代码与文档见上述仓库。

## 重新生成

```bash
uv run --with python-pptx --with pillow --with cairosvg \
  python scripts/build_presentation_v5.py

libreoffice --headless --convert-to pdf --outdir docs/presentations/v5 \
  docs/presentations/v5/Strands-Decider-模型原理与支付业务演示-v5-EC2部署版-25页-20261011.pptx
```

构建器读取仓库内的 v4 文稿、现有数据和 [AWS 官方图标](../../diagrams/aws-icons/README.md)，生成可编辑的架构图、更新后的备注及文件哈希。渲染检查覆盖页数、文本缺失、页面越界、历史数据与图片不变、末页链接、二维码及原稿未改写。
