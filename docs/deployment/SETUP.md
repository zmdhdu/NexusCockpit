# SETUP.md — NexusCockpit 环境搭建指南

> 本文档详细说明如何从零搭建 NexusCockpit 的完整开发环境。

---

## 目录

1. [前置要求](#1-前置要求)
2. [创建虚拟环境](#2-创建虚拟环境)
3. [安装 Python 依赖](#3-安装-python-依赖)
4. [启动基础设施 (Docker)](#4-启动基础设施-docker)
5. [下载 AI 模型](#5-下载-ai-模型)
6. [配置环境变量](#6-配置环境变量)
7. [初始化数据库](#7-初始化数据库)
8. [启动服务](#8-启动服务)
9. [验证部署](#9-验证部署)
10. [常见问题](#10-常见问题)

---

## 1. 前置要求

### 必需软件

| 软件 | 最低版本 | 说明 |
|------|----------|------|
| Python | 3.10+ | 推荐 3.10 或 3.11 |
| Docker | 24.0+ | Docker Desktop (Windows/Mac) 或 Docker Engine (Linux) |
| Docker Compose | 2.20+ | 随 Docker Desktop 安装 |
| Git | 2.40+ | 版本控制 |

### 可选软件

| 软件 | 用途 | 说明 |
|------|------|------|
| CUDA Toolkit 12.x | GPU 加速 ASR/TTS | 无 GPU 时使用 CPU 推理 |
| Node.js 18+ | 前端开发 | 仅前端开发需要 |

### 硬件要求

| 配置 | 最低 | 推荐 |
|------|------|------|
| CPU | 4 核 | 8 核+ |
| 内存 | 8 GB | 16 GB+ |
| 磁盘 | 20 GB | 50 GB+ (含模型文件) |
| GPU | 无 (CPU 推理) | 8GB+ 显存 (GPU 加速) |

---

## 2. 创建虚拟环境

> **重要**: 必须创建独立虚拟环境，避免与系统 Python 或其他项目冲突。

### Windows (PowerShell)

```powershell
# 进入项目目录
cd D:\path\to\NexusCockpit

# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
.\.venv\Scripts\Activate.ps1

# 如果遇到执行策略错误，先运行:
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Linux / macOS

```bash
# 进入项目目录
cd /path/to/NexusCockpit

# 创建虚拟环境
python3 -m venv .venv

# 激活虚拟环境
source .venv/bin/activate
```

### 验证

```bash
python --version   # 应显示 3.10+
which python       # 应指向 .venv 目录
pip --version      # 应指向 .venv 中的 pip
```

---

## 3. 安装 Python 依赖

### 3.1 升级 pip

```bash
pip install --upgrade pip setuptools wheel
```

### 3.2 安装 PyTorch (根据环境选择)

#### CPU 版本 (无 GPU)

```bash
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
```

#### GPU 版本 (CUDA 12.1)

```bash
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
```

#### GPU 版本 (CUDA 12.8)

```bash
# 从 https://pytorch.org 获取最新安装命令
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128
```

### 3.3 安装项目依赖

```bash
# 安装全部依赖 (含开发工具)
pip install -r requirements.txt

# 或使用 pyproject.toml (开发模式)
pip install -e ".[dev]"
```

### 3.4 验证安装

```bash
# 验证核心依赖
python -c "import fastapi; print(f'FastAPI {fastapi.__version__}')"
python -c "import torch; print(f'PyTorch {torch.__version__}, CUDA: {torch.cuda.is_available()}')"
python -c "import pymilvus; print(f'PyMilvus {pymilvus.__version__}')"
python -c "import langgraph; print(f'LangGraph OK')"
```

---

## 4. 启动基础设施 (Docker)

### 4.1 启动全部中间件

```bash
docker compose up -d
```

### 4.2 查看启动状态

```bash
docker compose ps
```

预期输出 (全部 `running`):

| 服务 | 端口 | 状态 |
|------|------|------|
| milvus | 19530 | running |
| etcd | 2379 | running |
| minio | 9000, 9001 | running |
| neo4j | 7474, 7687 | running |
| redis | 6379 | running |
| rabbitmq | 5672, 15672 | running |
| mysql | 3306 | running |
| prometheus | 9090 | running |
| grafana | 3001 | running |

### 4.3 各服务管理界面

| 服务 | 地址 | 账号/密码 |
|------|------|-----------|
| Neo4j Browser | http://localhost:7474 | neo4j / nexuscockpit |
| RabbitMQ Management | http://localhost:15672 | guest / guest |
| MinIO Console | http://localhost:9001 | minioadmin / minioadmin |
| Prometheus | http://localhost:9090 | - |
| Grafana | http://localhost:3001 | admin / admin |

### 4.4 停止/清理

```bash
# 停止
docker compose down

# 停止并清除数据 (谨慎!)
docker compose down -v
```

---

## 5. 下载 AI 模型

> 所有模型文件放置在项目的 `models/` 目录下 (相对路径)，不依赖外部路径。

### 5.1 SenseVoice ASR 模型

**路径**: `models/asr/sensevoice/`

```bash
# 使用 ModelScope 下载
pip install modelscope

# 下载到指定目录
modelscope download --model iic/SenseVoiceSmall --local_dir ./models/asr/sensevoice
```

或使用 Python 脚本:

```python
from modelscope.hub.snapshot_download import snapshot_download
snapshot_download(
    model_id="iic/SenseVoiceSmall",
    local_dir="./models/asr/sensevoice",
)
```

### 5.2 CAM++ 声纹模型

**路径**: `models/sv/cam_plus/`

```bash
# 从 ModelScope 下载
modelscope download --model iic/speech_campplus_sv_zh-cn_3dspeaker_16k --local_dir ./models/sv/cam_plus
```

### 5.3 CosyVoice TTS 模型

**路径**: `models/tts/cosyvoice/`

```bash
# 从 ModelScope 下载
modelscope download --model iic/CosyVoice-300M --local_dir ./models/tts/cosyvoice
```

> CosyVoice 模型文件较大 (约 3.5GB)，请确保磁盘空间充足。

### 5.4 本地 LLM 模型 (可选)

**路径**: `models/llm/qwen/`

仅在 `USE_LOCAL_LLM=true` 时需要。默认使用云端 API，无需下载。

```bash
# 从 HuggingFace 下载 Qwen2.5-7B-Instruct
# (需要安装 huggingface_hub)
pip install huggingface_hub

huggingface-cli download Qwen/Qwen2.5-7B-Instruct --local-dir ./models/llm/qwen
```

### 5.5 模型文件结构

下载完成后，目录结构应如下:

```
models/
├── asr/
│   └── sensevoice/          # SenseVoice ASR 模型
│       ├── model.pt
│       ├── config.yaml
│       └── ...
├── sv/
│   └── cam_plus/            # CAM++ 声纹模型
│       ├── campplus_cn_3dspeaker.bin
│       ├── configuration.json
│       └── ...
├── tts/
│   └── cosyvoice/           # CosyVoice TTS 模型
│       ├── llm.pt
│       ├── flow.pt
│       ├── hift.pt
│       ├── spk2info.pt
│       └── ...
└── llm/
    └── qwen/                # 本地 LLM (可选)
        ├── config.json
        ├── model-*.safetensors
        └── ...
```

### 5.6 从老项目迁移模型文件 (如果已有)

如果已有老项目的模型文件，可直接复制:

```powershell
# Windows PowerShell
# CAM++ 声纹模型
Copy-Item -Path "D:\old_project\iic\CAM++\*" -Destination ".\models\sv\cam_plus\" -Recurse -Force

# CosyVoice TTS 模型
Copy-Item -Path "D:\old_project\iic\CosyVoice-300M\*" -Destination ".\models\tts\cosyvoice\" -Recurse -Force
```

```bash
# Linux / macOS
cp -r /old_project/iic/CAM++/* ./models/sv/cam_plus/
cp -r /old_project/iic/CosyVoice-300M/* ./models/tts/cosyvoice/
```

---

## 6. 配置环境变量

```bash
# 复制配置模板
cp .env.example .env

# 编辑 .env，填入你的 API Key
```

### 必须配置的项

| 变量 | 说明 | 获取方式 |
|------|------|----------|
| `ARK_API_KEY` | LLM/Embedding API Key (火山方舟或硅基流动) | [console.volcengine.com/ark](https://console.volcengine.com/ark) 或 [cloud.siliconflow.cn](https://cloud.siliconflow.cn) |
| `TAVILY_API_KEY` | Tavily 搜索 API Key | [tavily.com](https://tavily.com) |

### 双模式部署开关 (本地 ⇄ 云端)

所有中间件均可通过 `.env` 的 `*_PROVIDER` 开关切换本地 Docker 或云端托管：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `VECTOR_STORE_PROVIDER` | `local` | `local`=本地 Milvus / `cloud`=Zilliz Cloud |
| `GRAPH_STORE_PROVIDER` | `local` | `local`=本地 Neo4j / `cloud`=AuraDB |
| `CACHE_PROVIDER` | `local` | `local`=本地 Redis / `cloud`=云 Redis |
| `RERANKER_PROVIDER` | `local` | `local`=本地 BGE / `cloud`=硅基流动 / `none`=跳过 |

> 切换云端时只需改 provider 为 `cloud` 并填入对应云端 AK/SK，代码无需改动。详见 `docs/deployment/dual_云端与本地部署.md`。

### 可选配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LANGFUSE_PUBLIC_KEY` | Langfuse 追踪公钥 | 空 (不启用追踪) |
| `LANGFUSE_SECRET_KEY` | Langfuse 追踪密钥 | 空 (不启用追踪) |
| `USE_LOCAL_LLM` | 是否使用本地 LLM | `false` (使用云端 API) |

### 路径配置 (通常无需修改)

所有路径默认使用项目根目录的相对路径:

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `FUNASR_MODEL_PATH` | `./models/asr/sensevoice` | ASR 模型路径 |
| `CAM_MODEL_PATH` | `./models/sv/cam_plus` | 声纹模型路径 |
| `COSYVOICE_MODEL_PATH` | `./models/tts/cosyvoice` | TTS 模型路径 |
| `LOCAL_LLM_MODEL_PATH` | `./models/llm/qwen` | 本地 LLM 路径 |
| `SPEAKER_ENROLL_DIR` | `./assets/speaker/enroll_wav` | 声纹注册音频 |
| `SPEAKER_USERS_DIR` | `./assets/speaker/users` | 用户声纹音频 |
| `FOOD_DATA_DIR` | `./data/food` | 食物知识库 |
| `KNOWLEDGE_DATA_DIR` | `./data/knowledge` | 知识文档 |
| `UPLOAD_DIR` | `./data/uploads` | 上传文件目录 |
| `TEMP_DIR` | `./data/temp` | 临时文件目录 |

---

## 7. 初始化数据库

### 7.1 初始化 Milvus 向量库

```bash
cd backend_design && python -m scripts.init_milvus
```

这将创建以下 Collection:
- `Food_List` — 食物知识库
- `User_Memory` — 用户记忆

### 7.2 初始化 Neo4j 知识图谱

```bash
cd backend_design && python -m scripts.init_neo4j
```

这将创建以下约束和索引:
- 用户节点唯一约束
- 偏好关系索引
- 技能节点

### 7.3 导入食物数据 (可选)

如果有食物数据 JSON 文件:

```bash
cd backend_design && python -m scripts.import_food_data --file ./data/food/food_list.json
```

---

## 8. 启动服务

### 8.1 开发模式 (热重载)

```bash
# 注意: 必须在 backend_design 目录下执行
cd backend_design && python -m nexus.main
```

> 也可以使用 Makefile: `make dev` (自动 cd 到 backend_design)

### 8.2 使用 uvicorn

```bash
cd backend_design && uvicorn nexus.main:app --host 0.0.0.0 --port 8000 --reload
```

### 8.3 生产模式

```bash
cd backend_design && uvicorn nexus.main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## 9. 验证部署

### 9.1 健康检查

```bash
curl http://localhost:8000/health
```

预期响应:

```json
{
    "status": "healthy",
    "services": {
        "milvus": "connected",
        "neo4j": "connected",
        "redis": "connected",
        "agent": "ready"
    }
}
```

### 9.2 测试对话

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"text": "你好", "user_id": "test"}'
```

### 9.3 测试车控

```bash
curl -X POST http://localhost:8000/vehicle/command \
  -H "Content-Type: application/json" \
  -d '{"command": "vehicle_climate", "arguments": {"op": "set_temp", "target_temp": 24}}'
```

### 9.4 查看文档

打开浏览器访问:
- Swagger UI: http://localhost:8000/docs
- Grafana: http://localhost:3001 (admin/admin)

---

## 10. 常见问题

### Q: Docker 启动失败

```bash
# 检查 Docker 是否运行
docker info

# 检查端口是否被占用
netstat -ano | findstr "19530"   # Windows
lsof -i :19530                    # Linux/Mac
```

### Q: Milvus 连接失败

```bash
# 检查 Milvus 容器状态
docker compose logs milvus

# 等待 Milvus 完全启动 (可能需要 30 秒)
docker compose ps milvus
```

### Q: 模型加载失败

```bash
# 检查模型文件是否存在
ls -la ./models/asr/sensevoice/
ls -la ./models/sv/cam_plus/
ls -la ./models/tts/cosyvoice/

# 检查路径配置
python -c "from nexus.config import get_config; c = get_config(); print(c.asr.resolved_funasr_path())"
```

### Q: GPU 不可用

```bash
# 检查 CUDA 是否可用
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"

# 如果不可用，检查 CUDA 驱动
nvidia-smi
```

### Q: 虚拟环境激活失败 (Windows PowerShell)

```powershell
# 修改执行策略
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 然后重新激活
.\.venv\Scripts\Activate.ps1
```

### Q: pip 安装超时

```bash
# 使用国内镜像源
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 或使用阿里云镜像
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple
```
