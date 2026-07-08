# NexusCockpit

> 企业级车载语音 Agent — Multi-Agent + GraphRAG + MCP

## 概述

NexusCockpit 是一个独立的车载语音 Agent 项目，采用 **7 层分层架构**，集成了 Multi-Agent 协同、GraphRAG 融合检索、语义缓存、MCP 协议等前沿技术。

> **项目完全独立** — 不依赖任何外部项目文件，所有路径使用相对路径，可整体迁移。

| 能力 | 技术栈 |
|------|--------|
| **Multi-Agent** | LangGraph (Planner → Executor → Responder → Reviewer) |
| **GraphRAG** | Milvus (向量检索) + Neo4j (知识图谱) + RRF 融合排序 |
| **语义缓存** | Redis 向量相似度缓存 |
| **限流** | Redis 滑动窗口限流 |
| **任务队列** | Celery + RabbitMQ 异步任务 |
| **车控总线** | Mock / HTTP / MCP stdio 三模式适配 |
| **可观测性** | Langfuse Tracing + Prometheus Metrics + Grafana |
| **API** | FastAPI REST + SSE + WebSocket |
| **ASR/TTS** | FunASR (SenseVoice) + CosyVoice |

## 项目结构

```
NexusCockpit/
├── Agent.md                     # 📋 项目总导航
├── README.md                    # 本文件
├── .env                         # 环境变量 (后端共享)
├── docker-compose.yml           # 基础设施一键部署
├── Makefile                     # 工程化命令
│
├── backend_design/              # 🔧 后端代码 (Python)
│   ├── nexus/                   #   主包 (7 层架构)
│   ├── tests/                   #   测试用例
│   ├── scripts/                 #   初始化脚本
│   ├── requirements.txt         #   Python 依赖
│   └── pyproject.toml           #   项目配置
│
├── frontend_design/             # 🎨 前端代码 (Next.js)
│   ├── src/app/                 #   页面
│   ├── src/components/          #   组件
│   ├── src/lib/                 #   API 客户端
│   └── package.json
│
├── .catpaw/skills/              # 🤖 AI 开发技能 (6 个)
├── docs/                        # 📚 文档中心
├── config/                      # 基础设施配置
├── models/                      # AI 模型文件 (需下载)
├── data/                        # 数据目录
└── assets/                      # 音频资源
```

> 详细导航请查看 [Agent.md](Agent.md)

## 快速开始

### 1. 启动基础设施

```bash
docker compose up -d
```

### 2. 安装后端环境

```bash
make install
```

### 3. 下载 AI 模型

> 模型文件较大 (CosyVoice 约 3.5GB)，请确保磁盘空间充足。
> 详细步骤请参考 [SETUP.md 第 5 节](docs/deployment/SETUP.md#5-下载-ai-模型)

```bash
pip install modelscope

# SenseVoice ASR 模型
modelscope download --model iic/SenseVoiceSmall --local_dir ./models/asr/sensevoice

# CAM++ 声纹模型
modelscope download --model iic/speech_campplus_sv_zh-cn_3dspeaker_16k --local_dir ./models/sv/cam_plus

# CosyVoice TTS 模型 (约 3.5GB)
modelscope download --model iic/CosyVoice-300M --local_dir ./models/tts/cosyvoice
```

### 4. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 ARK_API_KEY 等
```

### 5. 启动后端

```bash
make dev
```

### 6. 启动前端

```bash
make install-frontend
make dev-frontend
```

### 7. 访问

| 服务 | 地址 |
|------|------|
| 前端界面 | http://localhost:3000/dashboard |
| API 文档 (Swagger) | http://localhost:8000/docs |
| 健康检查 | http://localhost:8000/health |
| Grafana | http://localhost:3001 (admin/admin) |
| Prometheus | http://localhost:9090 |

## API 示例

### 文本对话

```bash
# 非流式
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"text": "把空调调到24度", "user_id": "test"}'

# 流式 (SSE)
curl -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"text": "今天天气怎么样", "user_id": "test", "stream": true}'
```

### 车控命令

```bash
curl -X POST http://localhost:8000/vehicle/command \
  -H "Content-Type: application/json" \
  -d '{"command": "vehicle_climate", "arguments": {"op": "set_temp", "target_temp": 24}}'
```

### WebSocket

```javascript
const ws = new WebSocket("ws://localhost:8000/ws/chat");
ws.send(JSON.stringify({text: "导航到上海虹桥", user_id: "test"}));
ws.onmessage = (event) => console.log(JSON.parse(event.data));
```

## 架构设计

### 7 层分层架构

```
L7  可观测层    →  Langfuse / Prometheus / Grafana
L6  API 层      →  FastAPI REST / SSE / WebSocket / JWT
L5  中间件层    →  Redis 语义缓存 / 限流 / Celery / 熔断器
L4  Agent 层    →  Planner → Executor → Responder → Reviewer
L3  服务层      →  ASR / TTS / Skills / Vehicle / Intent / MCP
L2  数据层      →  GraphRAG / Memory / Vector Store / Graph Store
L1  核心层      →  Config / Logger / Exceptions / Circuit Breaker
L0  基础设施层  →  Docker Compose / Milvus / Neo4j / Redis / RabbitMQ
```

> 详见 [架构总览](docs/architecture/overview.md)

### Multi-Agent 工作流

```
User Input → Planner → Executor → Responder → Reviewer → Response
                │           │          │           │
                │  意图路由   │ 技能调度  │ LLM流式   │ 质量检查
                │  记忆召回   │ RAG检索   │ 上下文压缩 │ 记忆存储
                └───────────┴──────────┴───────────┘
```

### GraphRAG 融合检索

```
Query
  ├── Vector Path: Milvus 语义搜索 → Top-K
  ├── Graph Path:  Neo4j 用户画像 + 关系遍历
  └── Fusion:      RRF 排序融合
```

## 技术选型

| 组件 | 选型 | 理由 |
|------|------|------|
| Web 框架 | FastAPI | 异步原生、自动文档 |
| Agent 编排 | LangGraph | 有状态图、条件路由 |
| 向量库 | Milvus 2.4 | 开源、HNSW 索引 |
| 图数据库 | Neo4j 5.x | Cypher、ACID |
| 缓存 | Redis 7 | 语义缓存、限流 |
| 消息队列 | RabbitMQ | AMQP 标准 |
| 配置 | Pydantic Settings | 类型安全 |
| ASR | FunASR (SenseVoice) | 多语言、端侧 |
| TTS | CosyVoice | 高质量、可克隆 |
| 追踪 | Langfuse | LLM 专用 |
| 指标 | Prometheus + Grafana | 云原生标准 |

## 文档导航

| 文档 | 说明 |
|------|------|
| [Agent.md](Agent.md) | 项目总导航 |
| [环境搭建指南](docs/deployment/SETUP.md) | 虚拟环境、模型下载、部署 |
| [架构总览](docs/architecture/overview.md) | 7 层架构设计 |
| [L0-L7 分层文档](docs/architecture/) | 各层详细说明 |

## License

MIT
