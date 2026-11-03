# Liquid d1-2B：从 EC2 部署到空调 LoRA 微调的完整手册

本手册将 **创建 EC2 → 安装环境 → 下载并验证模型 → 原模型试运行 → 数据准备 → LoRA 训练 → 完整对照评估 → 合并与服务部署 → 接入应用** 串成一条可操作的流程。

对象是 `LiquidAI/d1-2B` 的原生候选选择能力。输入仍为 `state + questions`，每个字段从给定候选中选值；训练保留官方编码、问题分组和选择头。参考实验见 [Liquid LoRA 实测](LIQUID_AC_LORA_RESULTS.md)，线上演示的运行方式见 [AC_CONTROL_DEMO.md](AC_CONTROL_DEMO.md)。

**验证范围：**原训练、合并推理及线上接入已经实测；本次手册新增的独立目录准备、发布包生成和离线核算在本机检查。编写手册时没有新建 EC2，也没有重新跑 GPU 训练。首次在新 AMI 上安装后，需要执行下面的环境检查和梯度验证，不能直接假设会复现原成绩。

## 目录

1. [资源、版本与执行位置](#1-资源版本与执行位置)
2. [创建 EC2 与访问权限](#2-创建-ec2-与访问权限)
3. [准备数据及源码包](#3-准备数据及源码包)
4. [GPU 环境与固定版本权重](#4-gpu-环境与固定版本权重)
5. [运行原模型](#5-运行原模型)
6. [梯度验证与正式训练](#6-梯度验证与正式训练)
7. [完整评估与离线评分](#7-完整评估与离线评分)
8. [生成合并模型服务并常驻](#8-生成合并模型服务并常驻)
9. [鉴权网关与应用接入](#9-鉴权网关与应用接入)
10. [自定义数据、调参及复现边界](#10-自定义数据调参及复现边界)
11. [故障排查、备份与回退](#11-故障排查备份与回退)

## 1. 资源、版本与执行位置

### 硬件与软件

| 项目 | 本手册使用的配置 |
|---|---|
| AWS 区域 | 优先 `us-east-1`，在有容量的可用区选择子网 |
| EC2 | On-Demand `g6.xlarge`，x86_64，4 vCPU、16 GiB RAM、1 张 NVIDIA L4 |
| 系统 | AWS 提供的 Ubuntu 24.04 GPU Deep Learning AMI，已带兼容的 NVIDIA 驱动 |
| 磁盘 | 加密 gp3，建议 150–250 GiB；下面示例为 250 GiB |
| Python | 独立 Python 3.12 虚拟环境 |
| 推理 / 训练 | PyTorch `2.13.0+cu130`、Transformers `5.20.2`、BF16 |
| 模型 | `LiquidAI/d1-2B` |
| 固定模型 revision | `cfe5760ff5d5998f91d9ac56bd4b2dbd96996d41` |
| 模型文件 SHA-256 | `b5e573687315e82ea80f4f7dd8d76b5cec3b6ee97e3509fd0493cfebb203719f` |
| 训练方式 | 自定义 `LoRALinear` 包装，仅文本注意力 `q_proj/v_proj` |
| 服务端口 | 模型及评估器 `127.0.0.1:18821`；鉴权网关 `18125` |

软件版本来自[实际评估服务记录](../validation/ac_control/runs/2026-11-01-liquid-lora-v1/evaluation/server.json)及当时的[环境清单](../validation/ac_control/runs/2026-10-31-all-models-input-optimization-v1/logs/h2o-requirements.txt)。当时复用了名为 `h2o` 的环境，**Liquid 本身不需要 H2O、其 vLLM 补丁或 PEFT Trainer**。新环境按下文安装独立依赖。

固定 revision 的[官方模型说明](https://huggingface.co/LiquidAI/d1-2B/blob/cfe5760ff5d5998f91d9ac56bd4b2dbd96996d41/README.md)说明了 `AutoModel`、`trust_remote_code=True`、`system_one` 和 `set_size=16`。同目录包含模型许可证。

### 两个执行位置

- **控制机**：当前项目工作区或你的管理电脑，保存测试标准答案、运行 AWS CLI、准备数据和离线评分。需要 Python 3.11+、AWS CLI v2、`boto3`，以及本仓库中包含本手册和 `manual.py` 的源码。
- **GPU 主机**：新建 EC2，执行模型加载、训练和推理。只上传训练 / 验证标签，以及不带标签的测试输入。

不要直接运行旧的 `infra.py`、`continue_run.py`：其中固定了原实验实例、Bucket 和操作名。下面直接使用可传入 `--root` / `--model` 的 `worker.py`、`evaluate.py`，通过新的 [manual.py](../validation/ac_control/liquid_lora/manual.py) 准备文件、离线核算和生成发布包。该辅助工具本身不会调用 AWS、启动训练或重启服务。

目录约定：

```text
控制机 / 本仓库
  .deployment/liquid-ac/<RUN_ID>/
    train.json / dev.json / test.json
    historical-references.json       # 测试答案留在控制机
    runtime-input.tar.gz             # GPU 输入，不含测试答案
    source-tools.tar.gz              # 同一版本的服务源码与辅助工具
    smoke/ training/ evaluation/     # GPU 执行后下载
    summary.json / audit.json        # 控制机离线核算

GPU /opt/liquid-ac/
  env/                              # Python 虚拟环境
  repo/                             # 从控制机传来的必要源码
  models/liquid/                    # 固定 revision 的完整 HF 模型目录
  runs/<RUN_ID>/                    # 训练输入、检查点、日志和推理回执
  releases/<RUN_ID>/                # 固定 SHA 的适配器与服务源码
```

新实验使用新 `RUN_ID`。`prepare`、`smoke`、`train` 和 `release` 会拒绝覆盖已存在的相应输出；评估已有回执时也不会自动重跑。

## 2. 创建 EC2 与访问权限

### 2.1 控制机：填写本账号的资源参数

以下参数需要在你的 AWS 账号选择，不能使用历史报告里的实例 ID 或安全组。进入本仓库根目录，在同一个 Bash 会话执行控制机命令。

```bash
export AC_REGION=us-east-1
export AC_RUN_ID="ac-lora-$(date -u +%Y%m%d-%H%M%S)"
export AC_ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
export AC_BUCKET="liquid-ac-${AC_ACCOUNT}-${AC_RUN_ID}"
export AC_ROLE="${AC_RUN_ID}-gpu"
export AC_PROFILE="${AC_RUN_ID}-gpu"
export AC_LOCAL_RUN="$PWD/.deployment/liquid-ac/$AC_RUN_ID"
export AC_TOOLS="$PWD/validation/ac_control/liquid_lora"

# 填入同一可用区、同一 VPC 的实际资源。
export AC_AMI="ami-REPLACE_WITH_VERIFIED_GPU_AMI"
export AC_SUBNET="subnet-REPLACE_WITH_SELECTED_SUBNET"
export AC_GPU_SG="sg-REPLACE_WITH_GPU_SECURITY_GROUP"
```

在 EC2 控制台选择 **AWS 发布、Ubuntu 24.04、x86_64、带 NVIDIA 驱动的 GPU Deep Learning AMI**。AMI 随区域和日期变化，不在手册中写死；确认它支持 CUDA 13，再填写 `AC_AMI`。`g6.xlarge` 至少需要 4 个 G/VT 类 On-Demand vCPU 配额。容量不足时换 `us-east-1` 内其他可用区及其子网，不同时提交多台实例。

建议通过 Systems Manager Session Manager 登录。实例需要到 SSM、S3、模型下载和 Python 包源的网络通路：私有子网可使用 NAT，或结合 VPC endpoints 与下载代理；仅有 SSM/S3 endpoints 不能下载 Hugging Face / PyPI。下面 EC2 命令不会自动分配公网 IP，需要子网已有相应出站能力。

训练阶段安全组无需开放推理端口。使用 SSH 时仅向管理 IP 开放 22；使用 SSM 可不开放入站端口。应用接入阶段再向 API 安全组开放 18125，18821 始终只监听本机。

### 2.2 控制机：私有存储和实例角色

下面创建本次独立 Bucket 和角色，不修改原演示的实例角色。

```bash
aws s3api create-bucket --region "$AC_REGION" --bucket "$AC_BUCKET"
aws s3api put-public-access-block --region "$AC_REGION" --bucket "$AC_BUCKET" \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-encryption --region "$AC_REGION" --bucket "$AC_BUCKET" \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

mkdir -p .deployment/liquid-ac-setup
cat > .deployment/liquid-ac-setup/trust.json <<'JSON'
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}
JSON
aws iam create-role --role-name "$AC_ROLE" \
  --assume-role-policy-document file://.deployment/liquid-ac-setup/trust.json
aws iam attach-role-policy --role-name "$AC_ROLE" \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore

python3 - <<'PY'
import json, os
from pathlib import Path
b, prefix = os.environ["AC_BUCKET"], "runs/" + os.environ["AC_RUN_ID"]
policy = {"Version":"2012-10-17","Statement":[
    {"Effect":"Allow","Action":["s3:ListBucket"],"Resource":f"arn:aws:s3:::{b}",
     "Condition":{"StringLike":{"s3:prefix":[prefix+"/*"]}}},
    {"Effect":"Allow","Action":["s3:GetObject"],"Resource":f"arn:aws:s3:::{b}/{prefix}/input/*"},
    {"Effect":"Allow","Action":["s3:PutObject"],"Resource":[
        f"arn:aws:s3:::{b}/{prefix}/output/*",
        f"arn:aws:s3:::{b}/{prefix}/releases/*"]}
]}
Path(".deployment/liquid-ac-setup/s3-policy.json").write_text(json.dumps(policy))
PY
aws iam put-role-policy --role-name "$AC_ROLE" --policy-name LiquidExperimentObjects \
  --policy-document file://.deployment/liquid-ac-setup/s3-policy.json
aws iam create-instance-profile --instance-profile-name "$AC_PROFILE"
aws iam add-role-to-instance-profile --instance-profile-name "$AC_PROFILE" --role-name "$AC_ROLE"
```

上面的 `create-bucket` 是 **us-east-1 专用形式**。换区域时需增加匹配的 `LocationConstraint`。若角色刚创建时 EC2 报 instance profile 尚不可用，等待 IAM 传播后再提交；不要因 SSH / SSM 暂时未就绪重复创建 EC2。

### 2.3 控制机：启动并连接

```bash
export AC_ROOT_DEVICE="$(aws ec2 describe-images --region "$AC_REGION" \
  --image-ids "$AC_AMI" --query 'Images[0].RootDeviceName' --output text)"
python3 - <<'PY'
import json, os
from pathlib import Path
Path(".deployment/liquid-ac-setup/disk.json").write_text(json.dumps([{
    "DeviceName":os.environ["AC_ROOT_DEVICE"],
    "Ebs":{"VolumeSize":250,"VolumeType":"gp3","Encrypted":True,"DeleteOnTermination":True}
}]))
PY
export AC_INSTANCE="$(aws ec2 run-instances --region "$AC_REGION" \
  --image-id "$AC_AMI" --instance-type g6.xlarge \
  --network-interfaces "DeviceIndex=0,SubnetId=$AC_SUBNET,Groups=[$AC_GPU_SG],AssociatePublicIpAddress=false" \
  --iam-instance-profile "Name=$AC_PROFILE" \
  --metadata-options HttpTokens=required,HttpEndpoint=enabled \
  --block-device-mappings file://.deployment/liquid-ac-setup/disk.json \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$AC_RUN_ID}]" \
  --client-token "$AC_RUN_ID" --count 1 \
  --query 'Instances[0].InstanceId' --output text)"
aws ec2 wait instance-running --region "$AC_REGION" --instance-ids "$AC_INSTANCE"
aws ssm describe-instance-information --region "$AC_REGION" \
  --filters "Key=InstanceIds,Values=$AC_INSTANCE"
```

确认 SSM `PingStatus=Online` 后，通过 EC2 控制台的“连接 → Session Manager”，或已安装 Session Manager plugin 的 AWS CLI 执行：

```bash
aws ssm start-session --region "$AC_REGION" --target "$AC_INSTANCE"
```

GPU 主机后续命令以 Ubuntu 的 `ubuntu` 用户运行；SSM 默认用户不同可执行 `sudo -iu ubuntu`。记录 `AC_INSTANCE`、`AC_RUN_ID`、Bucket 和 AMI ID。本手册不设置自动关机；完成后先备份，再按资源需求维护实例。

## 3. 准备数据及源码包

### 3.1 控制机：冻结本轮输入

默认复用已经公开的 1,024 条训练、96 条验证、192 条新表达测试，以及 78 条历史回归查询。规范正文已从 `docs/` 删除，原文在[冻结归档](../validation/ac_control/runs/2026-10-30-v1/spec.md)中，数据不依赖已删除的文件。

控制机准备 Python 环境后执行；已有项目 `.venv` 可直接使用。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install boto3
.venv/bin/python "$AC_TOOLS/manual.py" prepare --run-dir "$AC_LOCAL_RUN"

tar --exclude=__pycache__ --exclude='*.pyc' -czf "$AC_LOCAL_RUN/source-tools.tar.gz" \
  validation/ac_control/liquid_lora/manual.py \
  validation/ac_control/liquid_lora/worker.py \
  validation/ac_control/liquid_lora/evaluate.py \
  deployment/open_models/ac_lora_server.py \
  deployment/open_models/ac_lora_gateway.py \
  validation/ac_control/runs/2026-11-01-liquid-lora-v1/evaluation/server.json

sha256sum "$AC_LOCAL_RUN/runtime-input.tar.gz" "$AC_LOCAL_RUN/source-tools.tar.gz"
tar -tzf "$AC_LOCAL_RUN/runtime-input.tar.gz"
aws s3 cp "$AC_LOCAL_RUN/runtime-input.tar.gz" \
  "s3://$AC_BUCKET/runs/$AC_RUN_ID/input/runtime-input.tar.gz" --region "$AC_REGION"
aws s3 cp "$AC_LOCAL_RUN/source-tools.tar.gz" \
  "s3://$AC_BUCKET/runs/$AC_RUN_ID/input/source-tools.tar.gz" --region "$AC_REGION"
```

保留打印的两个 SHA-256，供 GPU 解包前核对。源码包从当前工作区创建，因此即使手册尚未推送，也能传递同一套辅助工具。

GPU 输入包只包含：

```text
worker.py
evaluate.py
template.json
train.json
dev.json
test-inputs.json
historical-cases.json
```

`test.json`、`historical-references.json` 留在控制机；训练及验证标签允许上传，测试答案不传给训练 / 推理进程。`prepare` 会记录输入哈希和当前 README 哈希，后续评分期间保持这个源码工作区不变。

### 3.2 数据格式

训练文件每条记录包含用户 query 和 **全部 30 个字段**的标签，标签值都是字符串。未请求修改的字段标为 `"omit"`，关闭值 `"0"` 仍是实际命令。例如“关闭显示灯”应有 `t_dimmer="0"`，其他字段为 omit。

从数据文件查看一条完整记录：

```bash
.venv/bin/python - <<'PY'
import json, os
from pathlib import Path
root = Path(os.environ["AC_LOCAL_RUN"])
rows = json.loads((root/"train.json").read_text())
print(json.dumps(rows[0], ensure_ascii=False, indent=2))
assert len(rows) == 1024 and len(rows[0]["labels"]) == 30
PY
```

温度必须包含伴随温标：`t_temp=24` 同时有 `t_temp_type=0`；华氏温度使用 `t_temp_f` 与 `t_temp_type=1`。数据由动作意图生成标签，不依赖教师模型。数据集共享词汇和生成器，是同领域合成测试，不能当作真实用户分布盲测。

## 4. GPU 环境与固定版本权重

### 4.1 GPU 主机：初始化目录与变量

将下列三个值换成控制机刚才实际使用的值；在同一个 GPU Bash 会话执行后续命令。

```bash
export AC_REGION=us-east-1
export AC_RUN_ID="REPLACE_WITH_CONTROLLER_RUN_ID"
export AC_BUCKET="REPLACE_WITH_CONTROLLER_BUCKET"
export AC_BASE=/opt/liquid-ac
export AC_REPO="$AC_BASE/repo"
export AC_GPU_RUN="$AC_BASE/runs/$AC_RUN_ID"
export AC_MODEL="$AC_BASE/models/liquid"
export AC_PY="$AC_BASE/env/bin/python"
export AC_RUNTIME_SHA="REPLACE_WITH_RUNTIME_INPUT_SHA256"
export AC_SOURCE_SHA="REPLACE_WITH_SOURCE_TOOLS_SHA256"

sudo install -d -o ubuntu -g ubuntu "$AC_BASE"
mkdir -p "$AC_REPO" "$AC_GPU_RUN" "$AC_MODEL" "$AC_BASE/downloads"
nvidia-smi
df -h "$AC_BASE"
```

确认 GPU 为 L4、驱动支持 CUDA 13、磁盘容量足够。若 `nvidia-smi` 失败，先修复 GPU AMI / 驱动，或重新选用兼容 AMI，再继续。不要在正在承载原演示的 GPU 上按本手册训练。

Ubuntu 基础工具：

```bash
sudo apt-get update
sudo apt-get install -y python3.12-venv curl unzip ca-certificates ripgrep libgl1 libglib2.0-0
python3.12 -m venv "$AC_BASE/env"
"$AC_PY" -m pip install --upgrade pip
"$AC_PY" -m pip install torch==2.13.0 torchvision==0.28.0 \
  --index-url https://download.pytorch.org/whl/cu130
"$AC_PY" -m pip install \
  transformers==5.20.2 huggingface-hub==2.4.0 \
  pillow==13.0.0 safetensors==0.8.0 tokenizers==0.23.3 \
  numpy==2.3.5 einops==0.8.2 \
  fastapi==0.136.3 uvicorn==0.54.0 httpx==0.28.1 boto3
```

上面是根据实测环境整理的独立安装配方，不是完整操作系统镜像锁文件。包源无法提供相应版本时，应取回当时保存的环境或建立新版本验收，不能静默改版本后沿用历史成绩。这里不使用项目 `--extra model`：该 extra 属于 Strands 的另一套依赖。

GPU AMI 若没有 AWS CLI，安装 CLI v2：

```bash
if ! command -v aws >/dev/null; then
  curl -fsS https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip \
    -o "$AC_BASE/downloads/awscliv2.zip"
  unzip -q "$AC_BASE/downloads/awscliv2.zip" -d "$AC_BASE/downloads"
  sudo "$AC_BASE/downloads/aws/install"
fi
aws sts get-caller-identity
```

实例使用 IAM role，不往主机写 AWS access key。

### 4.2 GPU 主机：下载输入与源码

```bash
aws s3 cp "s3://$AC_BUCKET/runs/$AC_RUN_ID/input/runtime-input.tar.gz" \
  "$AC_BASE/downloads/runtime-input.tar.gz" --region "$AC_REGION"
aws s3 cp "s3://$AC_BUCKET/runs/$AC_RUN_ID/input/source-tools.tar.gz" \
  "$AC_BASE/downloads/source-tools.tar.gz" --region "$AC_REGION"
printf '%s  %s\n' "$AC_RUNTIME_SHA" "$AC_BASE/downloads/runtime-input.tar.gz" | sha256sum -c -
printf '%s  %s\n' "$AC_SOURCE_SHA" "$AC_BASE/downloads/source-tools.tar.gz" | sha256sum -c -
tar -xzf "$AC_BASE/downloads/runtime-input.tar.gz" -C "$AC_GPU_RUN"
tar -xzf "$AC_BASE/downloads/source-tools.tar.gz" -C "$AC_REPO"
```

只解包你刚才在控制机生成并校验过的包。确认 `AC_GPU_RUN` 中没有 `test.json`、`historical-references.json`。

### 4.3 GPU 主机：下载固定 revision

```bash
export HF_HOME="$AC_BASE/hf-cache"
export TOKENIZERS_PARALLELISM=false
"$AC_PY" - <<'PY'
import os
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id="LiquidAI/d1-2B",
    revision="cfe5760ff5d5998f91d9ac56bd4b2dbd96996d41",
    local_dir=os.environ["AC_MODEL"],
    max_workers=4,
)
PY
"$AC_PY" "$AC_REPO/validation/ac_control/liquid_lora/manual.py" \
  verify-model --model-dir "$AC_MODEL"
"$AC_PY" - <<'PY'
import torch, transformers
assert torch.cuda.is_available()
assert torch.cuda.is_bf16_supported()
x = torch.randn(64, 64, device="cuda", dtype=torch.bfloat16)
assert torch.isfinite(x @ x).all()
torch.cuda.synchronize()
print(torch.__version__, torch.version.cuda, transformers.__version__)
print(torch.cuda.get_device_name(0))
PY
"$AC_PY" -m pip freeze > "$AC_GPU_RUN/environment-requirements.txt"
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv \
  > "$AC_GPU_RUN/gpu.csv"
```

`verify-model` 核对基础权重和 26 份自定义 Python 文件，与原实测记录一致；下载 revision 固定了配置和 tokenizer 的来源。模型通过 Hugging Face 自定义代码加载，正式训练时只读本机模型目录。

## 5. 运行原模型

先确认没有其他 GPU 任务：

```bash
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv
```

下面只调用一次原模型，不写适配器。使用完整 S01 输入，结果可能包含多发命令；先检查接口完整性，不要求原模型答对。

```bash
"$AC_PY" - <<'PY'
import json, os, sys
from pathlib import Path
root = Path(os.environ["AC_GPU_RUN"])
sys.path.insert(0, str(root))
from worker import Native
cases = json.loads((root/"historical-cases.json").read_text())
request = next(c["payload"] for c in cases
               if c["case_id"] == "S01" and c["order"] == "original")
native = Native(Path(os.environ["AC_MODEL"]))
raw = native.infer(request)
assert set(raw["answers"]) == set(request["questions"])
assert all(a["choice"] in request["questions"][k]["criteria"]
           for k, a in raw["answers"].items())
(root/"baseline-smoke.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2))
print(json.dumps({k:a["choice"] for k,a in raw["answers"].items()
                  if a["choice"] != "omit"}, ensure_ascii=False))
PY
```

进程退出后会释放 GPU 显存。原模型结果没有自动改成参考答案；正式评估还会重新加载基线模型并与 LoRA 配对。

## 6. 梯度验证与正式训练

### 6.1 LoRA 配置及计算方式

| 参数 | 本次实现 |
|---|---|
| rank / alpha / dropout | 16 / 32 / 0.05 |
| 可训练参数 | 1,171,456；仅文本注意力 q/v 投影 |
| 冻结 | 基础权重、视觉部分、嵌入、原选择头 |
| 精度 | 基础权重及前向 BF16，LoRA 参数 FP32 保存 |
| 优化器 | AdamW，lr `5e-5`，正式训练 weight decay `0.01` |
| 梯度累积 / 裁剪 | 16 条完整请求 / norm `1.0` |
| 数据 / 更新次数 | 1,024 条，1 epoch，64 次优化器更新 |
| 检查点 | 处理 256、512、1024 条后各保存并评价 dev |
| 随机种子 | `11012026` |
| 梯度检查点 | 开启，`use_reentrant=False` |

每个完整请求按官方默认 `set_size=16` 编码。30 个字段分成两个问题组，分别反向传播并累计为同一条请求的损失；不把整个任务变成 JSON 文本生成。

有执行字段和省略字段时：

```text
loss = 0.5 × mean(执行字段的交叉熵)
     + 0.5 × mean(omit 字段的交叉熵)
```

只有一类字段时使用该类的均值。候选别名沿用官方最大评分规则；字段及候选在训练中随机换序，标签位置同步调整。LoRA 为 `W + (alpha/r)BA`，B 零初始化；A 在最初梯度步骤为零梯度不一定是故障。

### 6.2 GPU 主机：8 步梯度验证

使用 systemd 临时服务，避免关闭 SSM 会话中断训练。以下单元名专属于本次新实验，不操作原演示单元。

```bash
sudo systemd-run --unit="liquid-ac-smoke-$AC_RUN_ID" \
  --property=User=ubuntu --property=WorkingDirectory="$AC_GPU_RUN" \
  --property=Restart=no \
  --setenv="HF_HOME=$AC_BASE/hf-cache" --setenv=TOKENIZERS_PARALLELISM=false \
  "$AC_PY" -u "$AC_GPU_RUN/worker.py" smoke --root "$AC_GPU_RUN" --model "$AC_MODEL"
journalctl -fu "liquid-ac-smoke-$AC_RUN_ID"
```

`Ctrl+C` 退出 `journalctl` 只停止看日志，不停止计算。单元完成后检查：

```bash
"$AC_PY" - <<'PY'
import json, os
from pathlib import Path
root = Path(os.environ["AC_GPU_RUN"])
r = json.loads((root/"smoke/result.json").read_text())
assert r["passed"] and r["frozen_weights_unchanged"] and r["adapter_reload_equal"]
print("smoke passed", r["losses"][0], "->", r["losses"][-1])
print((root/"smoke/modules.json").read_text())
PY
```

它验证训练评分与官方选择一致、梯度有限、8 步损失下降、基础权重未更新、适配器可重载。不要只看 systemd 显示 active；以最终 JSON 为准。失败时先排查，不继续正式训练。

### 6.3 GPU 主机：正式训练

```bash
sudo systemd-run --unit="liquid-ac-train-$AC_RUN_ID" \
  --property=User=ubuntu --property=WorkingDirectory="$AC_GPU_RUN" \
  --property=Restart=no \
  --setenv="HF_HOME=$AC_BASE/hf-cache" --setenv=TOKENIZERS_PARALLELISM=false \
  "$AC_PY" -u "$AC_GPU_RUN/worker.py" train --root "$AC_GPU_RUN" --model "$AC_MODEL"
journalctl -fu "liquid-ac-train-$AC_RUN_ID"
```

正式训练从原模型和新初始化 LoRA 开始，**不加载 smoke 的适配器**。先评估 96 条 dev 基线，再训练；原实验训练及中间验证约 39.9 分钟，不含初始 dev、模型加载和完整测试。

查看进度和最终选择：

```bash
cat "$AC_GPU_RUN/training/progress.json"
cat "$AC_GPU_RUN/training/checkpoints.json"
cat "$AC_GPU_RUN/training/selection.json"
```

尚未产生文件时表示对应阶段未完成。结束须出现 `TRAINING_COMPLETE`，并确认：

```bash
"$AC_PY" - <<'PY'
import hashlib, json, os
from pathlib import Path
root = Path(os.environ["AC_GPU_RUN"])
s = json.loads((root/"training/selection.json").read_text())
assert not s["heldout_used"] and s["frozen_weights_unchanged"]
selected = s["selected"]
p = root/"training"/selected["path"]
assert hashlib.sha256(p.read_bytes()).hexdigest() == selected["sha256"]
print(json.dumps(selected, indent=2))
PY
```

按 **dev 完整正确数最高 → 多发加漏发最少 → 更早检查点** 选择。原实验选中 `adapter-1024.pt`，新实验可能选中其他检查点，不能硬编码沿用旧文件名或旧 SHA。

脚本没有优化器状态恢复功能。目录已存在时不要删除后盲目重跑；保留失败日志，为重试创建新的实验目录。

## 7. 完整评估与离线评分

### 7.1 GPU 主机：启动评估服务

训练进程结束、18821 未被占用后：

```bash
mkdir -p "$AC_GPU_RUN/evaluation"
sudo systemd-run --unit="liquid-ac-eval-$AC_RUN_ID" \
  --property=User=ubuntu --property=WorkingDirectory="$AC_GPU_RUN" \
  --property=Restart=no \
  --setenv="HF_HOME=$AC_BASE/hf-cache" --setenv=TOKENIZERS_PARALLELISM=false \
  "$AC_PY" -u "$AC_GPU_RUN/evaluate.py" serve --root "$AC_GPU_RUN" --model "$AC_MODEL"
journalctl -u "liquid-ac-eval-$AC_RUN_ID" -n 30 --no-pager
curl -fsS http://127.0.0.1:18821/health
```

等到 health 返回 `ready=true` 后再运行客户端。初始化会重新加载适配器、关闭 LoRA dropout、在 8 个 dev 探针上检查重载，再合并权重并恢复原生投影融合。**正式 LoRA 成绩全部来自合并后的 BF16 模型**。合并可能有浮点差异，查看 `evaluation/reload-merge.json`，不要只凭公式认为数值完全相同。

评估器同时驻留 base 与 LoRA 两份模型，外部请求仍串行。不要同时运行线上单模型服务或其他 GPU 基准。

### 7.2 GPU 主机：一次完成质量与性能对照

```bash
sudo systemd-run --unit="liquid-ac-eval-client-$AC_RUN_ID" \
  --property=User=ubuntu --property=WorkingDirectory="$AC_GPU_RUN" \
  --property=Restart=no \
  "$AC_PY" -u "$AC_GPU_RUN/evaluate.py" run --root "$AC_GPU_RUN" --model "$AC_MODEL"
journalctl -fu "liquid-ac-eval-client-$AC_RUN_ID"
```

无接口错误时，本流程产生 **4,862 次 HTTP 调用**：

| 部分 | 请求次数 |
|---|---:|
| 192 条新表达 × 原序 / 倒序 × base / LoRA | 768 |
| 78 条历史查询 × 原序 / 倒序 × base / LoRA | 312 |
| 原规范 20 条 × 3 轮 ×（30 次单字段 + 1 次全答）× 两模型 | 3,720 |
| 两模型的串行及全答预热 | 62 |
| 合计 | 4,862 |

单步时间来自实际单字段调用；30 步串行使用同一条用户指令，各字段之间不传递上一步答案；一次全答一次发送 30 问。base / LoRA 交替先后顺序，全部请求外部并发 1。模型加载、重载校验和文件上传不在正式请求时间内。

`complete.json` 的任务块数应为 **1,324**，与 HTTP 次数不同。遇到接口错误时，当前串行任务可提前结束，实际调用数会减少，错误不会补成 omit 或自动重试。

```bash
cat "$AC_GPU_RUN/evaluation/progress.json"
cat "$AC_GPU_RUN/evaluation/complete.json"
```

评估客户端完成后，先停止本轮双模型评估服务，释放显存：

```bash
sudo systemctl stop "liquid-ac-eval-$AC_RUN_ID"
```

### 7.3 GPU → 控制机：归档并离线评分

GPU 主机上传：

```bash
for AC_FOLDER in smoke training evaluation; do
  aws s3 sync "$AC_GPU_RUN/$AC_FOLDER" \
    "s3://$AC_BUCKET/runs/$AC_RUN_ID/output/$AC_FOLDER" --region "$AC_REGION"
done
aws s3 cp "$AC_GPU_RUN/environment-requirements.txt" \
  "s3://$AC_BUCKET/runs/$AC_RUN_ID/output/environment-requirements.txt" --region "$AC_REGION"
aws s3 cp "$AC_GPU_RUN/gpu.csv" \
  "s3://$AC_BUCKET/runs/$AC_RUN_ID/output/gpu.csv" --region "$AC_REGION"
```

控制机执行：

```bash
aws s3 sync "s3://$AC_BUCKET/runs/$AC_RUN_ID/output/" "$AC_LOCAL_RUN/" --region "$AC_REGION"
.venv/bin/python "$AC_TOOLS/manual.py" score --run-dir "$AC_LOCAL_RUN"
cat "$AC_LOCAL_RUN/audit.json"
cat "$AC_LOCAL_RUN/summary.json"
```

核算复用原评估逻辑，会检查完整任务数、输入哈希、调用无重叠、候选合法性、检查点和源码 SHA，并把选择与控制机的标准答案比较。输出仅写入本轮目录，不覆盖旧的 `docs/LIQUID_AC_LORA_RESULTS.md`。

重点阅读：

- `summary.json → groups`：各数据集、顺序及方式的完整正确率、执行 / omit 字段正确数、均值、P95、错误数量。
- `single_step`：实际单字段正确率与耗时；其中有很多正确答案为 omit，不能等同于整条指令正确率。
- `conditions` / `adopted`：预定相对改进门槛，包括 heldout 改善、执行字段及规范不退化、全答均值 / P95 在基线 110% 以内、接口零错误。
- `scored.json`、`choice-changes.json`：具体多发、漏发、错值与微调前后变化。

原实验规范全答从 0/60 提升到 54/60，均值约 0.657 秒；新实验应报告自己的结果。门槛通过仍不代表真实设备控制的生产验收。

## 8. 生成合并模型服务并常驻

### 8.1 传回验收结果

只有核算通过后才继续。控制机上传 `summary.json`、`audit.json`，不上传测试标准答案：

```bash
for AC_FILE in summary.json audit.json; do
  aws s3 cp "$AC_LOCAL_RUN/$AC_FILE" \
    "s3://$AC_BUCKET/runs/$AC_RUN_ID/input/$AC_FILE" --region "$AC_REGION"
done
```

GPU 主机下载并创建一个新发布目录：

```bash
for AC_FILE in summary.json audit.json; do
  aws s3 cp "s3://$AC_BUCKET/runs/$AC_RUN_ID/input/$AC_FILE" \
    "$AC_GPU_RUN/$AC_FILE" --region "$AC_REGION"
done
export AC_RELEASE="$AC_BASE/releases/$AC_RUN_ID"
"$AC_PY" "$AC_REPO/validation/ac_control/liquid_lora/manual.py" release \
  --run-dir "$AC_GPU_RUN" --model-dir "$AC_MODEL" --release-dir "$AC_RELEASE"
cat "$AC_RELEASE/manifest.json"
```

辅助工具检查本轮选中检查点、实际评估身份、基础权重和门槛，再生成：

```text
releases/<RUN_ID>/
  training/adapter.pt
  worker.py
  server.py
  gateway.py
  manifest.json
```

服务和网关均固定到**这次所选适配器的 SHA**；模型只从已验证目录加载。合并发生在服务进程内，不会覆盖 Hugging Face 的 `model.safetensors`。部署制品是基础模型目录＋适配器＋冻结推理代码＋manifest，不是一个 PEFT `adapter_config.json` 包，也不是已经导出的独立 merged safetensors。

### 8.2 GPU 主机：建立持久单模型服务

确认评估器已经停止。下面操作的是新主机上自己的 `liquid-ac-model.service`。

```bash
sudo tee /etc/systemd/system/liquid-ac-model.service >/dev/null <<UNIT
[Unit]
Description=Liquid d1-2B merged AC LoRA
After=network-online.target
Wants=network-online.target

[Service]
User=ubuntu
WorkingDirectory=$AC_RELEASE
Environment=HF_HOME=$AC_BASE/hf-cache
Environment=TOKENIZERS_PARALLELISM=false
ExecStart=$AC_PY -u $AC_RELEASE/server.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now liquid-ac-model.service
journalctl -u liquid-ac-model.service -n 30 --no-pager
curl -fsS http://127.0.0.1:18821/health
```

启动初始化可能需等待。以 health 的 `ready`、`model`、`selected.sha256` 和 `base_sha256` 为准，不仅看 systemd 的 active。单模型上线只驻留合并后的 LoRA；原服务实测约使用 5–6 GiB GPU 显存，不作为任意输入长度的峰值保证。

一次真实请求验收：

```bash
"$AC_PY" - <<'PY'
import json, os, urllib.request
from pathlib import Path
root = Path(os.environ["AC_GPU_RUN"])
case = next(c for c in json.loads((root/"historical-cases.json").read_text())
            if c["case_id"] == "S01" and c["order"] == "original")
request = urllib.request.Request(
    "http://127.0.0.1:18821/lora",
    data=json.dumps(case["payload"], ensure_ascii=False).encode(),
    headers={"Content-Type":"application/json"},
)
with urllib.request.urlopen(request, timeout=120) as response:
    raw = json.load(response)
assert set(raw["answers"]) == set(case["payload"]["questions"])
print(json.dumps({k:a["choice"] for k,a in raw["answers"].items()
                  if a["choice"] != "omit"}, ensure_ascii=False))
PY
```

## 9. 鉴权网关与应用接入

### 9.1 控制机：创建网关密钥并授权 GPU 读取

沿用第 2 节的控制机变量，用本次唯一的 Secret 名。密钥不打印、不写入 Git、不作为命令行参数。

```bash
export AC_SECRET_NAME="liquid-ac/$AC_RUN_ID/gateway"
export AC_SECRET_ARN="$(.venv/bin/python - <<'PY'
import boto3, json, os, secrets
sm = boto3.client("secretsmanager", region_name=os.environ["AC_REGION"])
r = sm.create_secret(Name=os.environ["AC_SECRET_NAME"], SecretString=secrets.token_urlsafe(40))
policy = {"Version":"2012-10-17","Statement":[{
    "Effect":"Allow","Action":["secretsmanager:GetSecretValue"],"Resource":r["ARN"]
}]}
boto3.client("iam").put_role_policy(
    RoleName=os.environ["AC_ROLE"], PolicyName="LiquidGatewaySecret",
    PolicyDocument=json.dumps(policy),
)
print(r["ARN"])
PY
)"
```

Secret 已存在时使用已有 ARN，或按轮换流程处理，不重复创建。若使用客户管理 KMS key，另授予对应解密权限；本示例使用 Secrets Manager 默认加密。

### 9.2 GPU 主机：启动认证网关

填写控制机返回的 ARN。这个 ARN 不是密钥。

```bash
export AC_SECRET_ARN="REPLACE_WITH_SECRET_ARN"
sudo install -d -m 700 /etc/liquid-ac
sudo env AC_SECRET_ARN="$AC_SECRET_ARN" AC_REGION="$AC_REGION" "$AC_PY" - <<'PY'
import boto3, os
from pathlib import Path
os.umask(0o077)
token = boto3.client("secretsmanager", region_name=os.environ["AC_REGION"]).get_secret_value(
    SecretId=os.environ["AC_SECRET_ARN"])["SecretString"].strip()
assert token and all(c.isalnum() or c in "-_" for c in token)
Path("/etc/liquid-ac/gateway.env").write_text(
    "AC_LORA_TOKEN="+token+"\nAC_LORA_BIND=0.0.0.0\n")
PY
sudo tee /etc/systemd/system/liquid-ac-gateway.service >/dev/null <<UNIT
[Unit]
Description=Private authenticated Liquid AC gateway
After=network-online.target liquid-ac-model.service
Wants=network-online.target

[Service]
User=ubuntu
EnvironmentFile=/etc/liquid-ac/gateway.env
ExecStart=$AC_PY -u $AC_RELEASE/gateway.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now liquid-ac-gateway.service
```

未带 Bearer 的请求应返回 401：

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18125/health
```

带密钥的健康检查如下，脚本只打印响应，不打印 token：

```bash
sudo "$AC_PY" - <<'PY'
import json, urllib.request
from pathlib import Path
env = dict(line.split("=", 1) for line in Path("/etc/liquid-ac/gateway.env").read_text().splitlines())
req = urllib.request.Request("http://127.0.0.1:18125/health",
                             headers={"Authorization":"Bearer "+env["AC_LORA_TOKEN"]})
with urllib.request.urlopen(req, timeout=120) as response:
    print(json.dumps(json.load(response), indent=2))
PY
```

网关 `/v1/systemone` 接收完整业务请求，最多 30 问、每问最多 102 个候选；每次转发前核验适配器身份。模型服务留在 loopback，认证网关才向私网调用方开放。

### 9.3 控制机：开放 API 到 GPU 的私网路径

若 GPU 与业务 API 在同一 VPC，只需安全组；不同 VPC 还需要 peering / 其他私网连接及**双向路由**。先确认 CIDR 不冲突、连接 active，再为 API 子网和 GPU 子网各自的路由表添加目的路由。已有连接不得重复创建或覆盖默认路由。

同 VPC 示例，只允许业务 API 安全组访问 18125：

```bash
export AC_API_SG="sg-REPLACE_WITH_API_SECURITY_GROUP"
aws ec2 authorize-security-group-ingress --region "$AC_REGION" \
  --group-id "$AC_GPU_SG" --protocol tcp --port 18125 --source-group "$AC_API_SG"
```

跨 VPC 安全组引用须满足 AWS 对同区域 peering 等的限制；无法引用时使用精确的 API 私网来源范围。不要把 18125 开给 `0.0.0.0/0`。

### 9.4 接入现有空调演示 API

这一节以**已经部署本项目主应用**为前提。首次创建整个前端 / ECS / CloudFront 系统见 [AWS 部署说明](../deployment/README.md)。本手册的新 GPU 服务也可以独立使用，无需部署完整演示。

需要一致的三处配置：

| 位置 | 应使用的值 |
|---|---|
| 新模型服务及网关 | 发布目录 manifest 的 `adapter_sha256`；`manual.py release` 已固定 |
| 业务 API `app/ac_control.py` 的 `ADAPTER` | 同一个新 SHA，随新 API 镜像发布 |
| CloudFormation `AcLoraUrl` / `AcLoraSecretArn` | 新 GPU 私网 URL `http://PRIVATE_IP:18125` / 上面的 Secret ARN |

**原线上 API 固定的是原适配器 SHA。** 新训练得到的 SHA 即使准确率更好，也会被旧 API 拒绝。按本轮 manifest 更新 API 校验值并发布新镜像；不要删除身份校验，也不要覆盖已有镜像标签。若确实取得原适配器，可复用原 SHA，但仓库没有提供其权重下载。

API 发布需先具备主应用部署说明中的 `uv`、Docker、AWS 权限及构建环境。使用独立、内容已核对的源码工作区，执行：

```bash
# 先在源码中把 app/ac_control.py 的 ADAPTER 更新为本轮 manifest 的值。
# YOUR_NEW_TAG 必须是尚未使用的镜像标签。
uv run python deployment/deploy.py --region us-east-1 --api-only --tag YOUR_NEW_TAG
```

该命令会更新 API 和前端；只想准备制品时不要执行发布。部署前检查当前工作区仅包含拟发布内容，避免将其他未完成修改一并打包。

`deploy.py` 保留已有 `AcLora*` 参数，但没有专门设置新 URL / Secret 的 CLI 选项。已有主栈可用下列方式更新两个参数，其余值及模板保留；填写本账号的实际主栈名和 GPU 私网 IP：

```bash
export AC_STACK="REPLACE_WITH_EXISTING_APPLICATION_STACK"
export AC_LORA_URL="http://REPLACE_WITH_GPU_PRIVATE_IP:18125"
.venv/bin/python - <<'PY'
import boto3, os
cf = boto3.client("cloudformation", region_name=os.environ["AC_REGION"])
s = cf.describe_stacks(StackName=os.environ["AC_STACK"])["Stacks"][0]
assert s["StackStatus"] in ("CREATE_COMPLETE", "UPDATE_COMPLETE")
changes = {"AcLoraUrl":os.environ["AC_LORA_URL"], "AcLoraSecretArn":os.environ["AC_SECRET_ARN"]}
assert changes.keys() <= {p["ParameterKey"] for p in s["Parameters"]}, "先发布含 AcLora 参数的模板"
params = [{"ParameterKey":p["ParameterKey"],
           **({"ParameterValue":changes[p["ParameterKey"]]} if p["ParameterKey"] in changes
              else {"UsePreviousValue":True})} for p in s["Parameters"]]
cf.update_stack(StackName=s["StackName"], UsePreviousTemplate=True,
                Parameters=params, Capabilities=s.get("Capabilities", []))
print("Stack update submitted; check CloudFormation and ECS rollout before validation.")
PY
```

当前模板会为 ECS **execution role** 授权读取该 Secret，并调整 Secrets Manager VPC endpoint policy；GPU 的读取权限在 9.1 单独配置。使用私有 endpoint 时，其 policy、IAM、Secret resource policy 和 KMS policy 必须共同允许读取。更换 Secret 内容后，网关需重新生成 env 并重启，ECS Task 也需重新部署才能读取新值。

单机替换期间应暂停新对比任务，保存正在运行的记录。无中断要求时，先在另一套端口 / 实例验证新服务，再切 API；现有网关和评估器默认都固定了 18821，不能在同端口启动两个模型进程。

最终在页面选择 S01、S09、M08、M09，检查实际模型身份、完整输出、错误展示、单步 / 串行 / 全答耗时与导出。以这次回执验收，不把历史准确率填入新模型的实时结果。

## 10. 自定义数据、调参及复现边界

本手册默认流程完整复现本次训练方法，`manual.py prepare` 使用固定数据，不会自动收集用户指令。迁移到自己的空调或领域时：

1. 先固定完整能力表、合法值、字段区分及 omit 规则，再写用户表达和 30 字段标签。改变候选集合意味着新的任务版本，不能沿用旧标准答案。
2. 按用户表达、动作组合、设备和真实来源划分 train / dev / test，保留独立真实测试集。同一个表达的轻微改写不要随机落入不同分区。
3. 覆盖“关闭=0”和“保持不变=omit”、相近功能、否定、明确不修改的设置及温标伴随字段。优先补充显示灯、连续摆风与摆风角度、DR 开关等已知易混淆功能。
4. 输出同结构 `train.json`、`dev.json`、`test.json`；`test-inputs.json` 仅有 `id/query/language`。重新冻结数据哈希，生成新的传输包，保留测试标签在控制机。
5. 先进行梯度验证，再只用 dev 选择检查点；最终测试集不参与调参。若更改模型结构、损失或分组，重新验证训练评分与官方推理选择一致。

**现有 `worker.py` 是本次 1,024 条实验实现，不是任意数据量的通用 Trainer。** 梯度累积固定 16，最后不满 16 条不会自动执行剩余梯度；检查点位置固定为 256 / 512 / 1024。改变数据量时必须同时调整最后一次 optimizer step、检查点和选择逻辑。当前 portable 工具也按冻结脚本校验源文件；参数实验需要另存源码、更新相应实验清单和审计，不能修改历史记录来伪装一致。

可先保持 rank=16、lr=5e-5，优先改善数据，再做单因素对照。修改 rank / alpha / dropout 要让训练和加载时的 `LoRALinear` 定义一致；`.pt` 只保存 A/B 参数，不能靠权重文件自动恢复所有超参数。训练完不应在启用 dropout 的模型上做推理，必须 `.eval()`。

固定随机种子、相同硬件和包版本也不保证新适配器 SHA 或浮点输出完全相同。报告新检查点身份和新成绩；原实验的 90% 是这批规范场景结果，不是生产准确率承诺。

## 11. 故障排查、备份与回退

### 常见问题

| 现象 | 检查及处理 |
|---|---|
| EC2 容量不足 / 配额不足 | 分别检查目标 AZ 容量及 G/VT On-Demand vCPU 配额；复用同一 client token，先确认是否已有实例创建成功 |
| SSM 不在线 | 实例角色、SSM agent、DNS、出站 HTTPS / endpoints、系统启动状态 |
| S3 403 | Bucket、对象前缀、区域与 IAM policy；本手册只授权本轮 `runs/<RUN_ID>/...` |
| `torch.cuda.is_available()` 为 false | 是否装到 CUDA wheel、驱动是否可用；核对运行的是 `AC_PY`，不是系统 Python |
| CUDA / torchvision 导入错误 | 核对 torch 2.13、torchvision 0.28 和 cu130 配套；避免在原 H2O / Decider 环境交叉安装 |
| `No verified text-only q/v targets` | 固定 revision 或远程代码不一致；检查模型哈希，不扩大匹配规则后直接训练 |
| loss 非有限 / 梯度未出现 | 检查原生评分路径、目标标签、dtype、梯度检查点；先定位 smoke 失败，不能只降低日志级别 |
| CUDA OOM | 确认训练时只有一个模型进程；保留每个问题组单独反传和梯度检查点，检查输入长度及缓存 |
| `FileExistsError` / `Do not repeat evaluation` | 这是防止覆盖和重复调用的保护；查原任务状态，为新尝试使用新目录 |
| 评估 health 连接失败 | 查初始化日志及端口占用；CUDA 模型未加载完成时 systemd 可能已显示 active |
| 重载一致但合并选择变化 | 查看 `reload-merge.json`；BF16 合并有数值变化，最终验收使用合并后的实际完整结果 |
| gateway 401 | Bearer 密钥不一致，检查 Secret、env 和 API Task 是否同步更新 |
| gateway 503 / API 身份不符 | 模型未就绪、adapter SHA 不符、API 仍固定旧 SHA；不要关闭校验 |
| API 到 GPU 超时 | 安全组、私网 IP、双向路由、NACL；先从 API 所在网络验证 18125 |
| score 报 README / source hash 变化 | 比较准备时的清单与当前工作区；回到原实验源码版本核算，不改预期哈希掩盖差异 |

日志与资源查看：

```bash
nvidia-smi
systemctl status liquid-ac-model.service liquid-ac-gateway.service
journalctl -u liquid-ac-model.service -n 80 --no-pager
journalctl -u liquid-ac-gateway.service -n 80 --no-pager
ss -ltnp | rg '18821|18125'
```

### 备份和回退

上线前保存完整模型 revision / 校验值、环境清单、训练数据清单、选中适配器、评估回执、summary/audit、发布 manifest 和 systemd 配置。权重没有上传到 GitHub，备份应存放在你的私有存储。

GPU 主机备份本次发布目录：

```bash
aws s3 sync "$AC_RELEASE" \
  "s3://$AC_BUCKET/runs/$AC_RUN_ID/releases/$AC_RUN_ID" --region "$AC_REGION"
```

每次发布使用新目录，保留上一版目录和两个 systemd 单元的备份。回退时将模型与网关的 `ExecStart` 一起指回上一版目录、执行 `systemctl daemon-reload` 并重启两项服务；API 的适配器 SHA 和 GPU URL 也一起恢复。重启后再次核验 health 和实际请求，不只比较配置文件。

本手册不自动停止或终止 EC2。停止可停止按需实例计算计费，但 EBS、S3、Secrets Manager、NAT / endpoints 等仍可能计费；终止且删除根盘会丢失未备份的本地权重和实验文件。

## 源码与证据索引

- [手册辅助工具](../validation/ac_control/liquid_lora/manual.py)：独立目录准备、模型验证、离线评分和发布包生成。
- [训练实现](../validation/ac_control/liquid_lora/worker.py)：LoRA 注入、原生评分、损失、梯度验证、训练和检查点选择。
- [原始数据生成器](../validation/ac_control/liquid_lora/data.py)：动作意图、表达和标签生成，原入口路径固定，不直接覆盖旧实验。
- [配对评估器](../validation/ac_control/liquid_lora/evaluate.py)：合并验证、原序 / 倒序、全答与串行。
- [离线核算](../validation/ac_control/liquid_lora/analyze.py)：精确命令匹配、调用完整性、耗时和采用门槛；手册入口停用其旧日期报告生成。
- [模型服务模板](../deployment/open_models/ac_lora_server.py) · [认证网关模板](../deployment/open_models/ac_lora_gateway.py) · [CloudFormation 接入](../deployment/ac_control_infrastructure.py)。
- [原 LoRA 实测报告](LIQUID_AC_LORA_RESULTS.md) · [演示说明及验收](AC_CONTROL_DEMO.md) · [当前部署记录](../deployment/DEPLOYED.md)。

### 本手册的本地验证记录

2026-11-03：辅助工具的 4 项测试通过，覆盖测试标签隔离、按实际检查点生成发布包、失败门槛阻止发布，以及检查点路径限制；Ruff 检查通过。37 段 Bash 命令及其中 13 段 Python 的语法检查通过，文档本地链接和独立源码包目录解析通过。

通过新入口对历史 4,862 次调用、1,324 个任务块离线复算，`summary.json` 与原实验完全一致。上述检查没有执行 AWS 创建 / 发布命令，也没有安装新的 GPU 环境或再次训练；新主机上的实际验收仍按第 4–9 节执行。
