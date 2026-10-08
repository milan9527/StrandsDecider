# 已部署环境

部署及验收日期：2026-10-08。

**访问地址：https://d30wbetbveqce3.cloudfront.net**

API 文档：https://d30wbetbveqce3.cloudfront.net/api/docs

| 项目 | 当前值 |
| --- | --- |
| AWS Region | `us-east-2` |
| CloudFormation stack | `strands-decider-demo` |
| Stack 状态 | `UPDATE_COMPLETE` |
| CloudFront distribution | `E2OTYMNXHAUP4X` |
| CloudFront VPC Origin | `vo_016dHcrysO7DPfYCVYqwSK` |
| S3 bucket | `strands-decider-demo-frontendbucket-lmcuzhb95pgk` |
| VPC | `vpc-00641884e5c4ebfe7` |
| ECS cluster / service | `strands-decider-demo` |
| Task | 1 个健康 ARM64 Fargate Task，4 vCPU / 16 GiB |
| ECR API repository | `strands-decider-demo-api` |
| ECR model repository | `strands-decider-demo-model` |
| API 镜像 tag | `20261008-auth1` |
| 模型镜像 tag | `20261008-aws1` |
| 认证 | 自建用户名 / 密码，无 Cognito |
| DynamoDB 认证表 | `strands-decider-demo-auth` |
| 模型 | `strands-decider-2B-hobson-v19` |
| CloudWatch 日志组 | `/ecs/strands-decider-demo` |

## 已完成的验收

- S3 四项 Block Public Access 全部开启，AWS 返回 `IsPublic: false`。
- S3 匿名读取已上传的 `index.html` 返回 **403**；同一文件通过 CloudFront 返回 **200**。
- OAC 使用 `always` / `sigv4`，Bucket policy 的允许语句只授权上述 distribution ARN。
- API 使用 CloudFront VPC Origin 和内网 ALB；ECS Task 的 ENI 没有公网 IP，VPC 路由表没有互联网默认路由。
- 登录后 CloudFront `/api/health` 返回 `connected: true`。
- 通过 CloudFront 登录后的真实推理一次返回 Choice、Noul 和 Score 三种答案，`source: live`；客服场景选择 `billing`。认证更新验收时三问题推理观测耗时约 8.33 秒，不是性能保证。
- 未登录及退出后访问业务 API 均返回 `401`；重放退出前的 Cookie 同样被拒绝。线上会话 Cookie 的 `Secure`、`HttpOnly` 和 `SameSite=Strict` 已验证。
- 浏览器验证通过：用户名登录、错误密码、刷新保持登录、退出、API 访问控制、四个场景、输入修改与错误提示、真实推理、守卫分支、当前标签页运行记录、JSON 导出、390px / 320px 布局。
- 57 项后端测试、JavaScript 语法检查、Ruff 和 CloudFormation lint 通过。
- 模型镜像在 Docker `--network none` 下成功执行真实推理。

首次部署在 `us-east-1` 遇到 VPC / Internet Gateway 配额上限，随后改用 `us-east-2`；首次失败部署的 stack 和空资源已清理。`us-east-1` 的 VPC 配额增额申请属于账号配额管理，不承载本应用。

更新、日志查看与清理说明见 [README.md](README.md)。本文件记录上述验收时点的环境；后续发布输出以 `.deployment/outputs.json` 和 CloudFormation 为准。

管理员用户名 `admin`；强随机密码保存在本机 `.deployment/admin-credentials.json`，文件权限 0600。密码不写入本文档、前端或镜像。账号创建、停用与密码重置命令见 [README.md](README.md#登录与账号管理)。
