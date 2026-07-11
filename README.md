# NexusCockpit

> 企业级车载语音 Agent — Multi-Agent + GraphRAG + MCP

## 概述

NexusCockpit 是一个独立的车载语音 Agent 项目，采用 **7 层分层架构**，集成了 Multi-Agent 协同、GraphRAG 融合检索、语义缓存、MCP 协议等前沿技术。

> **项目完全独立** — 不依赖任何外部项目文件，所有路径使用相对路径，可整体迁移。

| 能力 | 技术栈 |
|------|--------|
| **Multi-Agent** | LangGraph v2.1: Supervisor + 5 Expert Agents + SubAgent 监控 + MainAgent 确认 |
| **多座舱 CS 架构** | v2.1: 3 座舱并行 + 数据中台看板 + 中间件隔离 |
| **GraphRAG** | Milvus (向量) + Neo4j (图谱) + BM25 (全文) 三路 RRF 融合 + Rerank 重排 |
| **语义缓存** | Redis Stack RediSearch KNN 向量缓存 + 副作用隔离 |
| **双模式部署** | 本地 Docker ⇄ 云端 API/AK·SK 一键切换 (Zilliz/AuraDB/云Redis/硅基流动) |
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
├── .catpaw/skills/              # 🤖 AI 开发技能 (8 个)
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
# 双模式部署: *_PROVIDER=local (本地Docker) 或 cloud (云端托管)
# 详见 docs/deployment/dual_云端与本地部署.md
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
L4  Agent 层    →  v2.0: Supervisor → 5 Expert Agents (并行) → Responder → Reviewer
L3  服务层      →  ASR / TTS / Skills / Vehicle / Intent / MCP
L2  数据层      →  GraphRAG / Memory / Vector Store / Graph Store
L1  核心层      →  Config / Logger / Exceptions / Circuit Breaker
L0  基础设施层  →  Docker Compose / Milvus / Neo4j / Redis / RabbitMQ / MySQL (双模式可切云端)
```

> 详见 [架构总览](docs/architecture/overview.md)

### Multi-Agent 工作流 (v2.0 Supervisor + 5 Experts)

```
User Input → Supervisor (意图+分派)
               ├── Vehicle Expert  (车控专家)
               ├── Nav Expert      (导航专家)
               ├── Lifestyle Expert (生活专家)
               ├── Health Expert   (健康专家)
               └── Chat Expert     (闲聊专家)
                      ↓ (并行)
            Responder (汇总+LLM流式)
               → Reviewer (质量检查+记忆存储)
               → Response
```

### GraphRAG 三路融合检索 (v2.0)

```
Query
  ├── Vector Path:  Milvus 语义搜索 → Top-K
  ├── Graph Path:   Neo4j 用户画像 + 关系遍历
  ├── BM25 Path:    全文关键词匹配召回
  └── RRF Fusion → Rerank (bge-reranker-v2-m3) → Top-5
```

### 双模式部署 (v2.0 新增)

所有中间件均可通过 `.env` 的 `*_PROVIDER` 开关一键切换本地 Docker 或云端托管：

| 组件 | local (本地) | cloud (云端) |
|------|-------------|-------------|
| 向量库 | Milvus (Docker) | Zilliz Cloud |
| 图谱 | Neo4j (Docker) | Neo4j AuraDB |
| 语义缓存 | Redis Stack (RediSearch KNN) | 云 Redis (scan 降级) |
| Reranker | 本地 BGE CrossEncoder | 硅基流动 Rerank API (免费) |
| LLM/Embedding | — | 硅基流动 / 火山方舟 (OpenAI 兼容, 改 .env 即可) |

> 详见 [双模式部署方案](docs/deployment/dual_云端与本地部署.md)

## 技术选型

| 组件 | 选型 | 理由 |
|------|------|------|
| Web 框架 | FastAPI | 异步原生、自动文档 |
| Agent 编排 | LangGraph | 有状态图、条件路由 |
| 向量库 | Milvus 2.4 | 开源、HNSW 索引 (双模式: Zilliz Cloud) |
| 图数据库 | Neo4j 5.x | Cypher、ACID (双模式: AuraDB) |
| 缓存 | Redis 7 | 语义缓存、限流 (双模式: 云 Redis) |
| Reranker | bge-reranker-v2-m3 | 三路融合后重排 (双模式: 硅基流动 API) |
| 消息队列 | RabbitMQ | AMQP 标准 |
| 配置 | Pydantic Settings | 类型安全 |
| ASR | FunASR (SenseVoice) | 多语言、端侧 |
| TTS | CosyVoice | 高质量、可克隆 |
| 追踪 | Langfuse | LLM 专用 |
| 指标 | Prometheus + Grafana | 云原生标准 |

## v2.1 多座舱 CS 架构 (规划中)

> **v2.1 设计方案**: [docs/v2.1-design.md](docs/v2.1-design.md)

v2.1 在 v2.0 单座舱基础上升级为 **多座舱 CS（Client-Server）架构**：

- **3 个座舱并行**：每个座舱独立用户、车控面板、会话、缓存
- **SubAgent 监控层**：每个座舱配备 SubAgent，不定时巡检状态，调用 LLM 判断异常
- **MainAgent 确认层**：接收 SubAgent 上报，二次确认后决定是否放行座舱执行结果
- **数据中台看板**：跨座舱统计、并发监控、告警历史、Agent 活动时间线
- **中间件看板**：展示 Redis/Milvus/Neo4j/RabbitMQ/MySQL 各座舱隔离状态
- **设置中心**：座舱注册、用户管理、中间件配置

```
座舱1 ──┐
座舱2 ──┼── API Gateway ── SubAgent 监控 ── MainAgent 确认 ── Supervisor+Experts
座舱3 ──┘                    ↓                    ↓
                         数据中台看板         中间件看板
```

前端侧栏分组：座舱1/2/3（车控面板）→ 数据中台 → 中间件 → 设置

## 文档导航

| 文档 | 说明 |
|------|------|
| [Agent.md](Agent.md) | 项目总导航 |
| **[v2.1 设计方案](docs/v2.1-design.md)** | **多座舱 CS 架构 + SubAgent 监控体系** |
| [环境搭建指南](docs/deployment/SETUP.md) | 虚拟环境、模型下载、部署 |
| [双模式部署方案](docs/deployment/dual_云端与本地部署.md) | 本地⇄云端 AK/SK 一键切换 |
| [架构总览](docs/architecture/overview.md) | 7 层架构设计 |
| [L0-L7 分层文档](docs/architecture/) | 各层详细说明 |
| [项目进展](docs/PROGRESS.md) | 开发进度与架构图 |

## License

MIT
