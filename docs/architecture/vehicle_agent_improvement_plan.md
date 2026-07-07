# 深度技术方案：企业级车载语音 Agent Demo

> **文档定位**：在 Demo 导向方案基础上，大幅提升技术深度和工程复杂度
> **核心目标**：展示高级 AI 应用全栈工程能力，覆盖中间件、高并发、高可用、可观测性
> **硬件环境**：NVIDIA RTX 4070 (8GB/12GB VRAM) + Win11 + i7-1400HX
> **设计原则**：完善、稳定、可靠、流畅、准确、高可用、高复用、高并发

---

## 目录

- [1. 技术调研：车端前沿技术全景](#1-技术调研车端前沿技术全景)
- [2. 整体架构设计（V2 深度版）](#2-整体架构设计v2-深度版)
- [3. 中间件层设计](#3-中间件层设计)
- [4. Agent 智能层深化](#4-agent-智能层深化)
- [5. 前端架构设计](#5-前端架构设计)
- [6. 数据层深化](#6-数据层深化)
- [7. 可观测性与运维体系](#7-可观测性与运维体系)
- [8. 安全与认证体系](#8-安全与认证体系)
- [9. 所需云服务与 API 清单](#9-所需云服务与-api-清单)
- [10. 实施路线图](#10-实施路线图)

---

## 1. 技术调研：车端前沿技术全景

### 1.1 车载智能座舱技术趋势（2024-2026）

| 技术方向 | 主流方案 | 本项目应用 | 展示价值 |
|----------|----------|-----------|----------|
| **MCP 协议** | Anthropic Model Context Protocol | 已有 ✅ → 深化多传输层 | 协议设计能力 |
| **SOA 架构** | 车载服务导向架构（SOME/IP, DDS） | 模拟 SOA 服务注册与发现 | 架构前瞻性 |
| **端云协同** | 端侧推理 + 云端大模型 | 已有 ✅ → 加 Circuit Breaker | 分布式系统设计 |
| **多 Agent 协同** | AutoGen / CrewAI / LangGraph Multi-Agent | 新增：Planner-Executor-Reviewer | Agent 架构深度 |
| **GraphRAG** | Microsoft GraphRAG + 知识图谱融合 | 新增：图谱增强 RAG | RAG 前沿实践 |
| **Semantic Cache** | Redis + 向量相似度缓存 | 新增：语义级缓存层 | 性能优化深度 |
| **流式 ASR** | WebSocket 流式语音识别 | 新增：实时流式转写 | 实时交互能力 |
| **vLLM 部署** | vLLM / TGI / SGLang 高吞吐推理 | 新增：本地 vLLM 服务 | 部署工程能力 |
| **TensorRT 加速** | ONNX → TensorRT EP | 可选：ASR/TTS 加速 | 性能调优能力 |
| **OTA 升级** | 差分升级 + A/B 分区 | 模拟：模型热更新机制 | 运维工程能力 |

### 1.2 车端通信协议对比

```
┌────────────────────────────────────────────────────────────────────┐
│                    车端通信协议演进                                   │
│                                                                    │
│  传统 CAN Bus          现代车载以太网           未来 SOA + DDS       │
│  ┌─────────┐           ┌─────────────┐          ┌─────────────┐    │
│  │CAN 2.0  │    →      │SOME/IP      │   →      │DDS + MQTT   │    │
│  │500kbps  │           │100Mbps      │          │灵活QoS      │    │
│  │广播式    │           │面向服务     │          │发布订阅     │    │
│  └─────────┘           └─────────────┘          └─────────────┘    │
│                                                                    │
│  本项目模拟策略:                                                     │
│  • MockVehicleBus → 模拟 CAN 信号                                    │
│  • HttpAdapter → 模拟 SOME/IP RESTful                               │
│  • MCPStdioAdapter → 模拟 DDS 发布订阅 (JSON-RPC over stdio)        │
│  • 【新增】MQTTAdapter → 模拟 MQTT 发布订阅                          │
│  • 【新增】WebSocketAdapter → 实时双向推送                           │
└────────────────────────────────────────────────────────────────────┘
```

### 1.3 AI Agent 框架对比与选型

| 框架 | 优势 | 劣势 | 本项目角色 |
|------|------|------|-----------|
| **LangGraph** | 状态图、条件路由、持久化 | 学习曲线陡 | 主力 Agent 编排 ✅ |
| **AutoGen** | 多 Agent 对话、代码执行 | 偏研究、生产弱 | 参考：Reviewer Agent |
| **CrewAI** | 角色分工、任务流 | 生态小 | 参考：任务分解 |
| **LlamaIndex** | RAG 生态丰富 | Agent 能力弱 | RAG 补充（可选） |
| **Dify** | 低代码、可视化 | 定制性差 | 不选（需展示代码能力） |

**选型决策**：LangGraph 为主力，结合 LangChain 生态，自研多 Agent 协同模式。

### 1.4 向量数据库对比

| 数据库 | 特点 | 本项目角色 |
|--------|------|-----------|
| **Milvus** | 分布式、高性能、生态好 | 主力向量库 ✅ |
| **Qdrant** | Rust 实现、轻量、过滤强 | 可选替代（对比展示） |
| **Weaviate** | 内置多模态、GraphQL | 不选 |
| **Chroma** | 嵌入式、超轻量 | 开发测试用 |
| **pgvector** | PostgreSQL 扩展 | 结构化数据+向量混合查询 |

**选型决策**：Milvus 主力 + Redis Vector 作为语义缓存层。

---

## 2. 整体架构设计（V2 深度版）

### 2.1 架构全景图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         接入层 (Access Layer)                            │
│                                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
│  │  Web UI  │  │ REST API │  │ WebSocket│  │  MCP     │  │ CLI     │ │
│  │ (Next.js)│  │ (FastAPI)│  │ (流式)    │  │  Server  │  │         │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬────┘ │
│       │              │              │              │             │      │
│  ┌────┴──────────────┴──────────────┴──────────────┴────────────┘      │
│  │                    Nginx 反向代理 + TLS                              │
│  │              负载均衡 + 限流 + IP 白名单                              │
│  └────────────────────────┬────────────────────────────────────────────┘
│                           │                                             │
│  ┌────────────────────────┴────────────────────────────────────────────┐
│  │              API 网关层 (FastAPI + JWT)                              │
│  │    认证 │ 鉴权 │ 限流 │ 请求追踪 │ API 版本管理                       │
│  └────────────────────────┬────────────────────────────────────────────┘
└───────────────────────────┼─────────────────────────────────────────────┘
                            │
┌───────────────────────────┴─────────────────────────────────────────────┐
│                         Agent 智能层 (Agent Layer)                       │
│                                                                         │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌────────────┐ │
│  │ Planner     │──▶│ Executor    │──▶│ Reviewer    │──▶│ Responder  │ │
│  │ Agent       │   │ Agent       │   │ Agent       │   │ Agent      │ │
│  │ (任务分解)  │   │ (技能执行)  │   │ (质量审查)  │   │ (回复生成) │ │
│  └──────┬──────┘   └──────┬──────┘   └──────┬──────┘   └──────┬─────┘ │
│         │                 │                 │                 │       │
│  ┌──────┴─────────────────┴─────────────────┴─────────────────┘       │
│  │                  LangGraph StateGraph                                │
│  │         条件路由 │ 并行节点 │ 状态持久化 │ 人机回路                   │
│  └──────────────────────────┬──────────────────────────────────────────┘
└─────────────────────────────┼───────────────────────────────────────────┘
                              │
┌─────────────────────────────┴───────────────────────────────────────────┐
│                      中间件层 (Middleware Layer)                         │
│                                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐│
│  │  Redis   │  │  Celery  │  │ RabbitMQ │  │  MinIO   │  │  Nginx   ││
│  │ 语义缓存  │  │ 异步任务  │  │ 消息队列  │  │ 对象存储  │  │ 反向代理  ││
│  │ 会话管理  │  │ 记忆提取  │  │ 事件总线  │  │ 音频文件  │  │ 负载均衡  ││
│  │ 限流计数  │  │ TTS 预生成│  │ Agent通信 │  │ 模型权重  │  │ 静态资源  ││
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘│
└─────────────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────┴───────────────────────────────────────────┐
│                      数据层 (Data Layer)                                 │
│                                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐│
│  │  Milvus  │  │  Neo4j   │  │PostgreSQL│  │  Redis   │  │  MinIO   ││
│  │ 向量记忆  │  │ 知识图谱  │  │ 结构化   │  │ 语义缓存  │  │ 音频存储  ││
│  │ RAG索引   │  │ GraphRAG │  │ 用户/日志 │  │ 会话状态  │  │ 模型权重  ││
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘│
└─────────────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────┴───────────────────────────────────────────┐
│                      模型层 (Model Layer)                                │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                    云端 API (主力)                                │  │
│  │  DeepSeek-V3 (对话) │ ARK Embedding │ Tavily (搜索)              │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                    本地推理 (4070 GPU)                            │  │
│  │  SenseVoice (ASR) │ CAM++ (声纹) │ BERT (意图)                   │  │
│  │  vLLM + Qwen3-4B (隐私模式/离线) │ Edge-TTS (轻量TTS)           │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────┴───────────────────────────────────────────┐
│                   可观测层 (Observability Layer)                         │
│                                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ Langfuse │  │Prometheus│  │  Grafana │  │  Loki    │              │
│  │ AI Trace │  │  Metrics │  │ Dashboard│  │  Logs    │              │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘              │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 与 V1 方案的核心升级

| 维度 | V1 方案 (Demo 导向) | V2 方案 (深度版) |
|------|---------------------|-----------------|
| **Agent** | 单 LangGraph 图 | **多 Agent 协同** (Planner→Executor→Reviewer→Responder) |
| **RAG** | 朴素 RAG | **GraphRAG** (知识图谱+向量融合检索 + Reranker) |
| **缓存** | 无 | **Redis 语义缓存** (Embedding 相似度匹配) |
| **异步** | async/await | **Celery + RabbitMQ** 异步任务队列 |
| **消息** | 无 | **RabbitMQ 事件总线** (Agent 间通信) |
| **存储** | Milvus + Neo4j | + **PostgreSQL** (结构化) + **MinIO** (音频) |
| **认证** | 无 | **JWT + OAuth2** 完整认证链 |
| **网关** | FastAPI 直连 | **Nginx 反向代理** + 限流 + TLS |
| **前端** | Gradio | **Next.js + TailwindCSS** 专业 Dashboard |
| **监控** | Langfuse (可选) | **Langfuse + Prometheus + Grafana + Loki** 全链路 |
| **部署** | 裸跑 | **Docker Compose** 一键编排全部服务 |

### 2.3 新增文件清单

```
Agent_ASR-master/
├── agent/                          # ★ 新增：多 Agent 模块
│   ├── __init__.py
│   ├── planner.py                  # 任务分解 Agent
│   ├── executor.py                 # 技能执行 Agent
│   ├── reviewer.py                 # 质量审查 Agent
│   ├── responder.py                # 回复生成 Agent
│   └── graph.py                    # LangGraph 多 Agent 编排
├── middleware/                     # ★ 新增：中间件层
│   ├── __init__.py
│   ├── redis_cache.py              # Redis 语义缓存
│   ├── celery_tasks.py             # Celery 异步任务
│   ├── event_bus.py                # RabbitMQ 事件总线
│   ├── rate_limiter.py             # 分布式限流
│   └── circuit_breaker.py          # 熔断器
├── core/                           # ★ 新增：核心基础设施
│   ├── __init__.py
│   ├── config.py                   # 升级版配置管理 (Pydantic Settings)
│   ├── security.py                 # JWT 认证
│   ├── database.py                 # PostgreSQL + SQLAlchemy
│   ├── storage.py                  # MinIO 对象存储
│   └── exceptions.py               # 统一异常体系
├── rag/                            # ★ 新增：升级版 RAG
│   ├── __init__.py
│   ├── graph_rag.py                # GraphRAG (图谱+向量融合)
│   ├── reranker.py                 # 交叉编码器重排序
│   ├── semantic_cache.py           # 语义缓存 (Redis+向量)
│   └── document_loader.py          # 多格式文档加载
├── api/                            # ★ 新增：API 模块化
│   ├── __init__.py
│   ├── routes/
│   │   ├── chat.py
│   │   ├── voice.py
│   │   ├── vehicle.py
│   │   ├── memory.py
│   │   ├── rag.py
│   │   └── auth.py
│   └── dependencies.py             # 依赖注入
├── web/                            # ★ 新增：前端项目
│   ├── package.json
│   ├── next.config.js
│   ├── tailwind.config.js
│   ├── src/
│   │   ├── app/                    # Next.js App Router
│   │   ├── components/             # React 组件
│   │   ├── hooks/                  # 自定义 Hooks
│   │   ├── lib/                    # 工具函数
│   │   └── styles/                 # 全局样式
│   └── Dockerfile
├── docker-compose.yml              # ★ 新增：全栈编排
├── nginx/
│   └── nginx.conf                  # ★ 新增：反向代理配置
├── monitoring/                     # ★ 新增：监控配置
│   ├── prometheus.yml
│   ├── grafana/
│   └── alertmanager.yml
├── Makefile                        # ★ 新增：一键管理命令
└── .env.example                    # ★ 升级：完整环境变量模板
```

---

## 3. 中间件层设计

### 3.1 Redis 语义缓存

**核心思想**：不仅缓存精确匹配的查询，还缓存语义相似的查询。当用户问"今天天气如何"和"今天天气怎么样"时，直接返回缓存结果。

```
用户查询
    │
    ▼
┌──────────────────┐
│ Embedding 编码   │
│ (ARK API)        │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐     命中 (cosine > 0.95)
│ Redis 向量搜索   │──────────────────────▶ 返回缓存结果
│ (RediSearch)     │
└────────┬─────────┘
         │ 未命中
         ▼
┌──────────────────┐
│ 正常 Agent 处理  │
│ (LangGraph)      │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 写入语义缓存     │
│ Key: query_vec   │
│ Val: response    │
│ TTL: 3600s       │
└──────────────────┘
```

**设计要点**：
- 缓存 Key 存 Embedding 向量（Redis Vector Set）
- 相似度阈值 0.95（可配置）
- TTL 策略：闲聊 30min，知识库 24h，车控 不缓存
- 缓存击穿保护：布隆过滤器 + 空值缓存
- 缓存失效策略：主动失效（记忆更新时）+ 被动失效（TTL）

### 3.2 Celery + RabbitMQ 异步任务队列

**异步任务类型**：

| 任务 | 队列 | 触发时机 | 延迟要求 |
|------|------|----------|----------|
| **记忆提取** | `memory_queue` | 每轮对话结束后 | 低（后台） |
| **记忆冲突裁决** | `memory_queue` | 检测到相似记忆时 | 低（后台） |
| **TTS 预生成** | `tts_queue` | LLM 流式输出时 | 中（并行） |
| **RAG 文档入库** | `ingest_queue` | 用户上传文档时 | 低（后台） |
| **Embedding 计算** | `embed_queue` | 记忆/文档写入时 | 中 |
| **审计日志写入** | `audit_queue` | 每次车控调用后 | 低（后台） |
| **健康检查上报** | `health_queue` | 定时（每 30s） | 低 |

**架构**：

```
FastAPI 请求线程
    │
    ├── 同步路径: ASR → 意图路由 → 技能执行 → LLM 生成 → TTS 播报
    │                                         │
    │                                         ├── (异步) 记忆提取 → Celery → RabbitMQ → Worker
    │                                         ├── (异步) 审计日志 → Celery → RabbitMQ → Worker
    │                                         └── (异步) TTS预生成 → Celery → RabbitMQ → Worker
    │
    └── 异步路径: 记忆提取/文档入库/批量Embedding → 直接送入 Celery
```

### 3.3 RabbitMQ 事件总线

**Agent 间通信的事件驱动模型**：

```
┌──────────┐                    ┌──────────┐
│ Planner  │─── plan_ready ───▶│ Executor │
│  Agent   │                    │  Agent   │
└──────────┘                    └────┬─────┘
                                     │
                              exec_done
                                     │
                                     ▼
┌──────────┐                    ┌──────────┐
│ Responder│◀── review_pass ───│ Reviewer │
│  Agent   │                    │  Agent   │
└──────────┘                    └──────────┘

事件类型:
  • plan_ready     → Planner 完成任务分解
  • exec_done      → Executor 完成技能执行
  • review_pass    → Reviewer 审查通过
  • review_fail    → Reviewer 审查不通过 → 回到 Executor
  • response_ready → Responder 生成回复
```

**设计要点**：
- Topic Exchange：按事件类型路由
- 每个 Agent 订阅自己关心的事件队列
- 支持事件回放（Dead Letter Queue）
- 与 LangGraph 状态图互补：LangGraph 管 DAG 流程，RabbitMQ 管跨 Agent 异步通信

### 3.4 熔断器 (Circuit Breaker)

**端云混合中的容错设计**：

```
                    ┌─────────────────────────┐
                    │    Circuit Breaker      │
                    │                         │
  请求 ────────────▶│  State: CLOSED          │──── 云端 LLM API
                    │  failure_count: 0/5     │
                    └─────────────────────────┘
                              │
                     连续失败 5 次
                              │
                              ▼
                    ┌─────────────────────────┐
                    │    Circuit Breaker      │
                    │                         │
  请求 ────────────▶│  State: OPEN            │──── ✖ 拒绝请求
                    │  降级: 本地 Qwen 推理   │──── ▶ 本地模型
                    └─────────────────────────┘
                              │
                     30s 后半开
                              │
                              ▼
                    ┌─────────────────────────┐
                    │    Circuit Breaker      │
                    │                         │
  请求 ────────────▶│  State: HALF_OPEN       │──── 试探性请求
                    │  成功 → CLOSED          │
                    │  失败 → OPEN            │
                    └─────────────────────────┘
```

### 3.5 分布式限流

```
多层限流策略:

  Layer 1: Nginx     → IP 级别限流 (req/s)
  Layer 2: API GW    → 用户级别限流 (JWT sub)
  Layer 3: Redis     → 资源级别限流 (LLM tokens/min, 车控 calls/min)
  Layer 4: MCP GW    → 工具级别限流 (已有 ✅)

  算法: 令牌桶 (Token Bucket) + 滑动窗口
  存储: Redis (分布式共享)
  超限: 429 Too Many Requests + Retry-After
```

---

## 4. Agent 智能层深化

### 4.1 多 Agent 协同架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                    LangGraph Multi-Agent Graph                      │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    Planner Agent                             │   │
│  │                                                             │   │
│  │  职责: 理解用户意图，分解为子任务序列                        │   │
│  │  输入: user_input + memories + intent                       │   │
│  │  输出: List[SubTask] (有序任务列表)                         │   │
│  │  工具: LLM (Function Calling) + 意图路由结果                │   │
│  │  示例: "导航到公司并把空调调到24度"                          │   │
│  │        → [SubTask(navigation, "公司"),                      │   │
│  │           SubTask(climate, 24)]                             │   │
│  └──────────────────────────┬──────────────────────────────────┘   │
│                             │                                       │
│                             ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    Executor Agent                            │   │
│  │                                                             │   │
│  │  职责: 按序执行子任务，调用技能和 MCP                        │   │
│  │  输入: List[SubTask]                                        │   │
│  │  输出: List[TaskResult] (每任务执行结果)                    │   │
│  │  工具: SkillOrchestrator + MCPGateway + RAG + WebSearch     │   │
│  │  并行: 无依赖的子任务可并行执行                              │   │
│  │  容错: 单任务失败不阻断整体，记录错误继续                    │   │
│  └──────────────────────────┬──────────────────────────────────┘   │
│                             │                                       │
│                             ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    Reviewer Agent                            │   │
│  │                                                             │   │
│  │  职责: 审查执行结果质量，决定是否需要修正                    │   │
│  │  输入: List[TaskResult] + user_input                        │   │
│  │  输出: ReviewDecision (pass / retry / clarify)              │   │
│  │  工具: LLM (少量样本提示)                                   │   │
│  │  规则:                                                      │   │
│  │    - 所有任务成功 → pass                                    │   │
│  │    - 部分失败但非关键 → pass + 标注                         │   │
│  │    - 关键任务失败 → retry (最多 1 次)                       │   │
│  │    - 意图不明确 → clarify (向用户提问)                      │   │
│  └──────────────────────────┬──────────────────────────────────┘   │
│                             │                                       │
│                    pass / retry / clarify                           │
│                             │                                       │
│              ┌──────────────┼──────────────┐                       │
│              ▼              ▼              ▼                       │
│         回到 Executor    回到 Executor   向用户提问                  │
│                             │                                       │
│                             ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    Responder Agent                           │   │
│  │                                                             │   │
│  │  职责: 综合所有结果，生成自然语言回复                        │   │
│  │  输入: List[TaskResult] + memories + context                │   │
│  │  输出: 自然语言回复 (流式)                                  │   │
│  │  工具: LLM (流式生成) + 记忆召回 + 上下文压缩               │   │
│  │  后处理: 记忆提取 (异步 Celery) → 冲突裁决 → 双库写入       │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.2 GraphRAG：图谱增强检索

**与朴素 RAG 的区别**：

```
朴素 RAG:
  Query → Embedding → Milvus TopK → LLM 生成
  问题: 检索到碎片化文本块，缺乏全局上下文

GraphRAG (本项目实现):
  Query → 两路并行检索
    ├── 向量检索: Milvus TopK (语义相似)
    └── 图谱检索: Neo4j Cypher (关系推理)
         │
         ▼
  融合排序 (Reranker)
    ├── 向量分数 × 0.4
    ├── 图谱深度分数 × 0.3
    └── 关键词 BM25 分数 × 0.3
         │
         ▼
  上下文组装
    ├── TopK 文本块
    ├── 图谱关系子图 (三元组)
    └── 实体摘要
         │
         ▼
  LLM 生成 (带图谱上下文的 Prompt)
```

**GraphRAG 的 Prompt 工程**：

```
你是一个车载语音助手。基于以下多源上下文回答用户问题。

【向量检索结果】
{vector_chunks}

【知识图谱关系】
- (用户) -[LIKES]-> (辣)
- (用户) -[DISLIKES]-> (甜食)
- (用户) -[DRIVES]-> (上海)

【实体摘要】
- 辣: 川菜、湘菜等辛辣食物
- 上海: 中国东部沿海城市

【用户问题】
{query}

请综合以上信息，简洁回答，不超过50字。
```

### 4.3 ReAct 推理模式

在 Planner Agent 中嵌入 ReAct (Reasoning + Acting) 循环：

```
用户: "我到公司了，帮我关窗并提醒我下午3点开会"

Thought 1: 用户到公司了，需要关窗。还要设置一个下午3点的提醒。
Action 1: vehicle_window(op=close, position=all)
Observation 1: ✅ 已关闭所有车窗

Thought 2: 车窗已关。现在需要设置提醒。当前时间是 14:30。
Action 2: set_reminder(time=15:00, content="开会")
Observation 2: ✅ 已设置提醒

Thought 3: 两个任务都完成了，可以回复用户。
Final Answer: 好的，车窗已全部关闭，下午3点的开会提醒也设好了！
```

### 4.4 人机回路 (Human-in-the-Loop)

在 LangGraph 中实现中断与恢复：

```
用户: "帮我导航到..."
                    │
                    ▼
            ┌──────────────┐
            │ Planner Agent│
            └──────┬───────┘
                   │
                   ▼
            ┌──────────────┐
            │ 目的地不明确  │
            │ → 中断        │
            └──────┬───────┘
                   │
                   ▼
            ┌──────────────┐
            │ 向用户提问    │
            │ "您想去哪里？"│
            └──────┬───────┘
                   │
                   ▼
            用户: "上海虹桥火车站"
                   │
                   ▼
            ┌──────────────┐
            │ 恢复执行      │
            │ → 导航到目的地│
            └──────────────┘
```

---

## 5. 前端架构设计

### 5.1 技术选型（基于 fronted-design skill 原则）

遵循 `fronted-design` SKILL.md 的设计原则：

1. **明确页面目标**：展示 Agent 全链路能力，支持语音/文本/车控交互
2. **设计结构层级**：Dashboard 布局，左侧导航 + 主内容区
3. **定义视觉规则**：深色科技风，蓝紫主色，卡片式信息密度
4. **补全交互细节**：loading / empty / error / streaming 状态
5. **响应式 + 可访问性**：适配桌面/平板，ARIA 标签

| 维度 | 选型 | 理由 |
|------|------|------|
| **框架** | Next.js 14 (App Router) | SSR + API Routes + 文件路由 |
| **样式** | TailwindCSS + shadcn/ui | 原子化 CSS + 高质量组件 |
| **状态** | Zustand | 轻量、无 Provider、支持中间件 |
| **请求** | TanStack Query | 缓存、重试、乐观更新 |
| **实时** | WebSocket + SSE | 流式对话 + 实时状态推送 |
| **图表** | Recharts | 延迟/Token/调用次数可视化 |
| **音频** | Web Audio API + MediaRecorder | 浏览器内录音 + 可视化 |
| **动画** | Framer Motion | 页面过渡 + 微交互 |

### 5.2 页面结构

```
┌─────────────────────────────────────────────────────────────────────┐
│  顶部导航栏 (Header)                                                 │
│  [Logo] M-RAG-Voice    [Tab: 对话|车控|记忆|RAG|监控|架构]  [用户▾] │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────┐  ┌──────────────────────────────────────────────┐ │
│  │             │  │                                              │ │
│  │  左侧面板    │  │            主内容区                          │ │
│  │             │  │                                              │ │
│  │  ┌───────┐  │  │  根据选中的 Tab 显示不同内容:                 │ │
│  │  │用户卡片│  │  │                                              │ │
│  │  │头像+ID│  │  │  📌 对话 Tab:                                 │ │
│  │  │声纹状态│  │  │  ┌──────────────────────────────────────┐   │ │
│  │  └───────┘  │  │  │                                      │   │ │
│  │             │  │  │  对话历史 (流式渲染)                  │   │ │
│  │  ┌───────┐  │  │  │                                      │   │ │
│  │  │快捷操作│  │  │  │  [用户] 把空调调到24度               │   │ │
│  │  │• 清空  │  │  │  │  [助手] ✅ 已将空调设置为24度         │   │ │
│  │  │• 导出  │  │  │  │                                      │   │ │
│  │  │• 设置  │  │  │  │  [用户] 我以后不吃辣了               │   │ │
│  │  └───────┘  │  │  │  [助手] 好的，已更新您的口味偏好      │   │ │
│  │             │  │  │                                      │   │ │
│  │  ┌───────┐  │  │  └──────────────────────────────────────┘   │ │
│  │  │模式切换│  │  │                                              │ │
│  │  │○ 云端  │  │  │  ┌──────────────────────────────────────┐   │ │
│  │  │○ 隐私  │  │  │  │ [输入框]                    [🎤][发送]│   │ │
│  │  │○ RAG   │  │  │  └──────────────────────────────────────┘   │ │
│  │  └───────┘  │  │                                              │ │
│  │             │  │  📌 车控 Tab:                                 │ │
│  │  ┌───────┐  │  │  车辆 3D 模型 + 控制面板                      │ │
│  │  │延迟统计│  │  │                                              │ │
│  │  │ P50: 2s│  │  │  📌 记忆 Tab:                                │ │
│  │  │ P95: 4s│  │  │  时间线 + 图谱可视化                         │ │
│  │  └───────┘  │  │                                              │ │
│  │             │  │  📌 监控 Tab:                                 │ │
│  │             │  │  实时图表 (延迟/Token/QPS/错误率)             │ │
│  └─────────────┘  └──────────────────────────────────────────────┘ │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│  底部状态栏 (Footer)                                                 │
│  [● 已连接] [云端: DeepSeek-V3] [GPU: 4070 6.2GB/12GB] [v1.0.0]    │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.3 组件设计

```
src/
├── app/
│   ├── layout.tsx                 # 根布局 (Header + Sidebar + Main)
│   ├── page.tsx                   # 首页 → 重定向到 /chat
│   ├── chat/page.tsx              # 对话页
│   ├── vehicle/page.tsx           # 车控页
│   ├── memory/page.tsx            # 记忆页
│   ├── rag/page.tsx               # RAG 知识库页
│   ├── monitoring/page.tsx        # 监控页
│   └── architecture/page.tsx      # 架构展示页
├── components/
│   ├── ui/                        # shadcn/ui 基础组件
│   │   ├── button.tsx
│   │   ├── card.tsx
│   │   ├── dialog.tsx
│   │   ├── input.tsx
│   │   ├── badge.tsx
│   │   └── ...
│   ├── chat/
│   │   ├── ChatMessage.tsx        # 消息气泡 (支持流式渲染)
│   │   ├── ChatInput.tsx          # 输入框 + 录音按钮
│   │   ├── VoiceRecorder.tsx      # 语音录制组件
│   │   ├── IntentBadge.tsx        # 意图标签
│   │   └── LatencyTag.tsx         # 延迟标签
│   ├── vehicle/
│   │   ├── VehicleModel.tsx       # 车辆 3D 模型 (Three.js)
│   │   ├── ClimateControl.tsx     # 空调控制面板
│   │   ├── WindowControl.tsx      # 车窗控制
│   │   └── StatusPanel.tsx        # 车辆状态仪表盘
│   ├── memory/
│   │   ├── MemoryTimeline.tsx     # 记忆时间线
│   │   ├── KnowledgeGraph.tsx     # 图谱可视化 (D3.js / react-force-graph)
│   │   └── ConflictResolver.tsx   # 冲突裁决可视化
│   ├── monitoring/
│   │   ├── LatencyChart.tsx       # 延迟折线图
│   │   ├── TokenUsageChart.tsx    # Token 用量
│   │   ├── AgentTraceView.tsx     # Langfuse Trace 可视化
│   │   └── SystemHealth.tsx       # 系统健康状态
│   └── layout/
│       ├── Header.tsx
│       ├── Sidebar.tsx
│       ├── Footer.tsx
│       └── ThemeProvider.tsx
├── hooks/
│   ├── useChat.ts                 # 对话逻辑 (WebSocket + TanStack Query)
│   ├── useVoiceRecorder.ts        # 录音逻辑
│   ├── useVehicleControl.ts       # 车控调用
│   └── useStreamingResponse.ts    # 流式响应处理
├── lib/
│   ├── api.ts                     # API 客户端 (axios + interceptor)
│   ├── ws.ts                      # WebSocket 客户端
│   ├── auth.ts                    # JWT 认证
│   └── utils.ts                   # 工具函数
└── stores/
    ├── chatStore.ts               # 对话状态
    ├── userStore.ts               # 用户状态
    └── settingsStore.ts           # 设置状态 (模式切换等)
```

### 5.4 视觉设计规范

```
颜色系统 (深色科技风):
  --bg-primary:    #0a0a0f     (主背景, 近黑)
  --bg-secondary:  #12121a     (卡片背景)
  --bg-tertiary:   #1a1a2e     (悬浮元素)
  --border:        #2a2a3e     (边框)
  --text-primary:  #e4e4e7     (主文字)
  --text-secondary:#a1a1aa     (次要文字)
  --accent-blue:   #3b82f6     (主强调色)
  --accent-purple: #8b5cf6     (次强调色)
  --accent-green:  #10b981     (成功)
  --accent-red:    #ef4444     (错误)
  --accent-yellow: #f59e0b     (警告)

字体:
  --font-sans:     'Inter', 'Noto Sans SC', sans-serif
  --font-mono:     'JetBrains Mono', monospace

间距 (8px 网格):
  --space-1:  4px
  --space-2:  8px
  --space-3:  12px
  --space-4:  16px
  --space-6:  24px
  --space-8:  32px

圆角:
  --radius-sm: 6px
  --radius-md: 8px
  --radius-lg: 12px

动画:
  --transition-fast:   150ms ease
  --transition-normal: 250ms ease
  --transition-slow:   400ms ease

状态反馈:
  - Loading: Skeleton + Spinner + Progress Bar
  - Empty:   插图 + 引导文案 + CTA 按钮
  - Error:   错误图标 + 描述 + 重试按钮
  - Streaming: 打字机效果 + 光标闪烁
```

---

## 6. 数据层深化

### 6.1 多数据库分工

```
┌─────────────────────────────────────────────────────────────────┐
│                        数据层架构                                 │
│                                                                 │
│  ┌──────────────┐  用途: 向量记忆、RAG 索引                     │
│  │   Milvus     │  数据: Embedding (1024d) + text + metadata   │
│  │   (向量库)    │  查询: ANN 搜索 (HNSW/IVF)                   │
│  └──────────────┘  端口: 19530                                 │
│                                                                 │
│  ┌──────────────┐  用途: 知识图谱、GraphRAG                     │
│  │   Neo4j      │  数据: (User)-[RELATION]->(Entity)           │
│  │   (图数据库)  │  查询: Cypher (多跳关系推理)                  │
│  └──────────────┘  端口: 7687                                  │
│                                                                 │
│  ┌──────────────┐  用途: 用户、会话、审计日志、配置              │
│  │ PostgreSQL   │  数据: 关系型结构化数据                        │
│  │  (关系数据库) │  查询: SQL (事务 + JOIN + 聚合)              │
│  └──────────────┘  端口: 5432                                  │
│                                                                 │
│  ┌──────────────┐  用途: 语义缓存、会话状态、限流计数            │
│  │   Redis      │  数据: Key-Value + Vector Set                │
│  │  (缓存+消息)  │  查询: GET/SET + RediSearch (向量搜索)       │
│  └──────────────┘  端口: 6379                                  │
│                                                                 │
│  ┌──────────────┐  用途: 音频文件、模型权重、文档                │
│  │   MinIO      │  数据: 对象存储 (S3 兼容)                     │
│  │  (对象存储)   │  查询: S3 API (PUT/GET/LIST)                │
│  └──────────────┘  端口: 9000                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 PostgreSQL 表设计

```sql
-- 用户表
CREATE TABLE users (
    id          SERIAL PRIMARY KEY,
    username    VARCHAR(64) UNIQUE NOT NULL,
    display_name VARCHAR(128),
    voice_print_id VARCHAR(128),          -- 声纹 ID
    role        VARCHAR(16) DEFAULT 'user', -- user / admin
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
);

-- 会话表
CREATE TABLE sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     INTEGER REFERENCES users(id),
    started_at  TIMESTAMP DEFAULT NOW(),
    ended_at    TIMESTAMP,
    metadata    JSONB                          -- 会话元数据
);

-- 对话记录表
CREATE TABLE conversations (
    id          BIGSERIAL PRIMARY KEY,
    session_id  UUID REFERENCES sessions(id),
    user_id     INTEGER REFERENCES users(id),
    role        VARCHAR(16) NOT NULL,           -- user / assistant / system
    content     TEXT NOT NULL,
    intent      JSONB,                           -- 意图识别结果
    latency_ms  REAL,                            -- 响应延迟
    tokens_used INTEGER,                         -- Token 消耗
    model       VARCHAR(64),                     -- 使用的模型
    created_at  TIMESTAMP DEFAULT NOW()
);

-- 车控审计日志
CREATE TABLE vehicle_audit_logs (
    id          BIGSERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id),
    tool_name   VARCHAR(64) NOT NULL,
    arguments   JSONB NOT NULL,
    result      JSONB NOT NULL,
    success     BOOLEAN NOT NULL,
    latency_ms  REAL,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- RAG 文档管理
CREATE TABLE rag_documents (
    id          SERIAL PRIMARY KEY,
    source      VARCHAR(256),                   -- 文件名/URL/手动
    content     TEXT NOT NULL,
    chunk_count INTEGER,                        -- 分块数
    metadata    JSONB,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- 系统配置表
CREATE TABLE system_config (
    key         VARCHAR(128) PRIMARY KEY,
    value       JSONB NOT NULL,
    description TEXT,
    updated_at  TIMESTAMP DEFAULT NOW()
);
```

### 6.3 Redis 数据结构设计

```
Redis 数据结构:

1. 语义缓存 (RediSearch Vector Index)
   Key:  sem_cache:{md5(query)}
   Val:  {query, embedding(1024f), response, timestamp, user_id}
   Index: FT.CREATE sem_cache ON JSON PREFIX 1 sem_cache:
          SCHEMA $.embedding VECTOR HNSW 6 TYPE FLOAT32 DIM 1024
          DISTANCE_METRIC COSINE

2. 会话状态 (Hash)
   Key:  session:{session_id}
   Fields: user_id, started_at, context_summary, turn_count, mode
   TTL:   3600s

3. 限流计数 (Sliding Window)
   Key:  ratelimit:{user_id}:{resource}
   Val:  Sorted Set (timestamp as score)
   TTL:  60s

4. 在线用户 (Set)
   Key:  online_users
   Val:  Set of user_ids

5. Agent 状态 (Hash)
   Key:  agent_state:{session_id}
   Fields: current_node, planner_output, executor_output, reviewer_output
   TTL:   300s

6. 发布订阅 (Channel)
   Channel: agent_events:{session_id}
   Msg:    {type, agent, data, timestamp}
```

---

## 7. 可观测性与运维体系

### 7.1 全链路监控架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     可观测性三层架构                              │
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │  Metrics    │  │   Logs      │  │   Traces    │            │
│  │ (Prometheus)│  │   (Loki)    │  │ (Langfuse)  │            │
│  │             │  │             │  │             │            │
│  │ • QPS       │  │ • 应用日志  │  │ • Agent     │            │
│  │ • 延迟分布   │  │ • 错误堆栈  │  │   Trace     │            │
│  │ • 错误率     │  │ • 请求日志  │  │ • LLM Call  │            │
│  │ • GPU 利用率 │  │ • 审计日志  │  │ • Skill     │            │
│  │ • 内存占用   │  │ • 慢查询    │  │   Span      │            │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘            │
│         │                │                │                    │
│  ┌──────┴────────────────┴────────────────┴──────┐            │
│  │              Grafana 统一仪表盘                  │            │
│  │                                                │            │
│  │  • 实时延迟 P50/P95/P99                        │            │
│  │  • Agent 执行链路 Trace                        │            │
│  │  • LLM Token 消耗趋势                          │            │
│  │  • 车控调用成功率                              │            │
│  │  • 缓存命中率                                  │            │
│  │  • 系统资源利用率                               │            │
│  └────────────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────────┘
```

### 7.2 Langfuse Trace 结构

```
Trace: agent_turn (user_id, session_id)
├── Span: recall_memory (input, output, latency)
├── Span: intent_route (input, output, latency)
│   └── Generation: llm_function_call (model, prompt, tokens, cost)
├── Span: skill_dispatch (input, output, latency)
│   ├── Span: web_search (input, output, latency)
│   └── Span: vehicle_control (input, output, latency)
│       └── Span: mcp_gateway (input, output, latency)
├── Span: rag_retrieve (input, output, latency)
│   ├── Span: vector_search (input, output, latency)
│   └── Span: graph_search (input, output, latency)
├── Generation: llm_generate (model, prompt, tokens, cost)
└── Span: post_process (input, output, latency)
    └── Span: memory_extract (input, output, latency)
        └── Generation: llm_extract (model, prompt, tokens, cost)
```

### 7.3 Prometheus 指标定义

```python
# 核心指标
agent_request_total = Counter('agent_request_total', 'Total agent requests', ['user_id', 'intent'])
agent_request_duration = Histogram('agent_request_duration_seconds', 'Agent request duration',
                                    buckets=[0.5, 1, 2, 3, 5, 8, 10, 15])
agent_llm_tokens = Counter('agent_llm_tokens_total', 'LLM tokens used', ['model', 'type'])
agent_cache_hits = Counter('agent_cache_hits_total', 'Cache hits', ['cache_type'])
agent_cache_misses = Counter('agent_cache_misses_total', 'Cache misses', ['cache_type'])
agent_vehicle_calls = Counter('agent_vehicle_calls_total', 'Vehicle control calls', ['tool', 'success'])
agent_active_sessions = Gauge('agent_active_sessions', 'Active sessions')
agent_gpu_memory = Gauge('agent_gpu_memory_bytes', 'GPU memory usage')
agent_queue_size = Gauge('agent_queue_size', 'Celery queue size', ['queue_name'])
```

### 7.4 告警规则

```yaml
# alertmanager.yml 规则示例
groups:
  - name: agent_alerts
    rules:
      - alert: HighLatency
        expr: histogram_quantile(0.95, agent_request_duration_seconds_bucket) > 10
        for: 5m
        labels: { severity: warning }
        annotations: { summary: "P95 延迟超过 10s" }

      - alert: HighErrorRate
        expr: rate(agent_request_total{status="error"}[5m]) / rate(agent_request_total[5m]) > 0.1
        for: 2m
        labels: { severity: critical }
        annotations: { summary: "错误率超过 10%" }

      - alert: GPUMemoryHigh
        expr: agent_gpu_memory_bytes / (12 * 1024 * 1024 * 1024) > 0.9
        for: 5m
        labels: { severity: warning }
        annotations: { summary: "GPU 显存使用超过 90%" }

      - alert: QueueBacklog
        expr: agent_queue_size > 100
        for: 5m
        labels: { severity: warning }
        annotations: { summary: "Celery 队列积压超过 100" }
```

---

## 8. 安全与认证体系

### 8.1 认证链路

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  用户    │────▶│  登录    │────▶│ JWT 签发 │────▶│ 存储     │
│          │     │ (用户名  │     │ (access  │     │ (httpOnly│
│          │     │  +密码)  │     │  +refresh│     │  cookie) │
│          │     │          │     │  token)  │     │          │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
                                                        │
                                                        │
┌──────────┐     ┌──────────┐     ┌──────────┐          │
│  API     │◀────│ JWT 验证 │◀────│ 请求携带 │◀─────────┘
│  资源    │     │ (中间件) │     │ Bearer   │
│          │     │          │     │  Token   │
└──────────┘     └──────────┘     └──────────┘
```

### 8.2 安全措施清单

| 安全层 | 措施 | 实现 |
|--------|------|------|
| **传输安全** | HTTPS/TLS | Nginx + Let's Encrypt |
| **认证** | JWT + Refresh Token | `python-jose` + `passlib` |
| **授权** | RBAC 角色权限 | `FastAPI Depends` |
| **输入验证** | Pydantic Schema | 已有 ✅ |
| **SQL 注入** | ORM 参数化查询 | SQLAlchemy |
| **Cypher 注入** | 参数化 Cypher | Neo4j Driver 参数化 |
| **XSS** | CSP + 输入转义 | Next.js 默认 |
| **CSRF** | SameSite Cookie | Next.js |
| **限流** | 多层限流 | Nginx + Redis |
| **审计** | 全操作日志 | PostgreSQL + Celery |
| **密钥管理** | .env + Vault(可选) | python-dotenv |
| **依赖安全** | pip-audit | CI/CD |

---

## 9. 所需云服务与 API 清单

### 9.1 必需服务

| 服务 | 用途 | 获取方式 | 费用 |
|------|------|----------|------|
| **火山引擎 ARK API** | LLM (DeepSeek-V3) + Embedding | [console.volcengine.com](https://console.volcengine.com/ark) | 按 Token 计费，有免费额度 |
| **Tavily Search API** | 联网搜索 | [tavily.com](https://tavily.com) | 免费额度 1000次/月 |
| **Milvus** | 向量数据库 | Docker 本地 / [Zilliz Cloud](https://cloud.zilliz.com/) | 本地免费 / Cloud 有免费层 |
| **Neo4j** | 知识图谱 | Docker 本地 / [Neo4j Aura](https://neo4j.com/aura/) | 本地免费 / Aura 有免费层 |

### 9.2 推荐服务（提升完整度）

| 服务 | 用途 | 获取方式 | 费用 |
|------|------|----------|------|
| **Langfuse Cloud** | AI Trace 可观测 | [langfuse.com](https://langfuse.com) | 免费层足够 |
| **Redis Cloud** | 语义缓存 + 会话 | [redis.io/cloud](https://redis.io/cloud/) | 免费 30MB 或本地 Docker |
| **PostgreSQL** | 结构化数据 | Docker 本地 / [Supabase](https://supabase.com) | 本地免费 / Supabase 免费 |
| **MinIO** | 对象存储 | Docker 本地 | 免费 |
| **RabbitMQ** | 消息队列 | Docker 本地 / [CloudAMQP](https://www.cloudamqp.com/) | 本地免费 / Cloud 有免费层 |

### 9.3 可选服务（进一步展示）

| 服务 | 用途 | 获取方式 | 费用 |
|------|------|----------|------|
| **vLLM** | 本地 LLM 高吞吐推理 | `pip install vllm` + 本地 GPU | 免费 |
| **Cloudflare** | CDN + DNS + DDoS | [cloudflare.com](https://cloudflare.com) | 免费层 |
| **GitHub Actions** | CI/CD | GitHub 自带 | 免费 |
| **Docker Hub** | 镜像托管 | [hub.docker.com](https://hub.docker.com) | 免费 |
| **SwanLab** | 训练实验追踪 | [swanlab.cn](https://swanlab.cn) | 免费层 |
| **阿里云 OSS** | 备用对象存储 | [aliyun.com](https://aliyun.com) | 有免费额度 |

### 9.4 API Key 配置模板 (.env 完整版)

```env
# ==================== LLM API ====================
# 火山引擎 ARK (主力 LLM + Embedding)
ARK_API_KEY=your_ark_api_key
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3

# OpenAI 兼容 (备用)
OPENAI_API_KEY=your_openai_api_key
OPENAI_BASE_URL=https://api.openai.com/v1

# ==================== 搜索 ====================
TAVILY_API_KEY=your_tavily_api_key

# ==================== 数据库 ====================
# Milvus
MILVUS_URI=http://127.0.0.1:19530
MILVUS_TOKEN=

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password

# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_pg_password
POSTGRES_DB=agent_asr

# ==================== 缓存与消息 ====================
# Redis
REDIS_URL=redis://localhost:6379/0

# RabbitMQ
RABBITMQ_URL=amqp://guest:guest@localhost:5672//

# ==================== 对象存储 ====================
# MinIO
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=agent-audio

# ==================== 可观测性 ====================
# Langfuse
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-xxx
LANGFUSE_SECRET_KEY=sk-lf-xxx
LANGFUSE_HOST=https://cloud.langfuse.com

# ==================== 认证 ====================
JWT_SECRET_KEY=your-jwt-secret-key-change-this
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# ==================== 本地模型 ====================
LLM_MODEL_PATH=D:\Qwen
ASR_MODEL_PATH=D:\ASR-LLM-TTS-master\ASR-LLM-TTS-master\ASR
CAM_MODEL_PATH=iic/CAM++
COSYVOICE_MODEL_PATH=iic/CosyVoice-300M

# ==================== 模型配置 ====================
LLM_MODEL=deepseek-ai/DeepSeek-V3
EMBEDDING_MODEL=Qwen/Qwen3-Embedding-4B

# ==================== 服务配置 ====================
API_HOST=0.0.0.0
API_PORT=8000
WEBUI_HOST=0.0.0.0
WEBUI_PORT=3000

# ==================== 流水线 ====================
PIPELINE_MODE=orchestrator
VEHICLE_ADAPTER=mock
PRIVACY_MODE=false

# ==================== Celery ====================
CELERY_BROKER_URL=amqp://guest:guest@localhost:5672//
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# ==================== 限流 ====================
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_LLM_TOKENS_PER_MINUTE=10000

# ==================== 语义缓存 ====================
SEMANTIC_CACHE_ENABLED=true
SEMANTIC_CACHE_THRESHOLD=0.95
SEMANTIC_CACHE_TTL=3600
```

### 9.5 一键启动所有服务 (docker-compose.yml 架构)

```yaml
# docker-compose.yml 服务拓扑
version: '3.8'

services:
  # ===== 基础设施 =====
  milvus:        # 向量数据库
  neo4j:         # 知识图谱
  postgres:      # 关系数据库
  redis:         # 缓存 + 消息
  rabbitmq:      # 消息队列
  minio:         # 对象存储

  # ===== 中间件 =====
  celery-worker: # 异步任务 Worker
  celery-beat:   # 定时任务调度

  # ===== 应用 =====
  api:           # FastAPI 后端
  web:           # Next.js 前端
  nginx:         # 反向代理

  # ===== 监控 =====
  prometheus:    # 指标采集
  grafana:       # 可视化面板
  loki:          # 日志聚合

  # ===== 可选 =====
  vllm:          # 本地 LLM 服务 (可选)
  mcp-server:    # 独立 MCP 车控服务
```

---

## 10. 实施路线图

### 10.1 分阶段实施

```
Phase 1: 基础设施搭建 (1-2 天)
├── 编写 docker-compose.yml (全部服务)
├── 升级 config.py → Pydantic Settings
├── 搭建 PostgreSQL + SQLAlchemy ORM
├── 搭建 Redis 连接池
├── 搭建 MinIO 对象存储
└── 编写 Makefile 一键管理命令

Phase 2: 中间件层 (2-3 天)
├── Redis 语义缓存 (sem_cache.py)
├── Celery 异步任务 (celery_tasks.py)
│   ├── 记忆提取异步化
│   ├── 审计日志异步写入
│   └── TTS 预生成
├── RabbitMQ 事件总线 (event_bus.py)
├── 熔断器 (circuit_breaker.py)
└── 分布式限流 (rate_limiter.py)

Phase 3: Agent 深化 (2-3 天)
├── 多 Agent 架构 (agent/)
│   ├── Planner Agent (任务分解 + ReAct)
│   ├── Executor Agent (并行执行 + 容错)
│   ├── Reviewer Agent (质量审查)
│   └── Responder Agent (流式生成)
├── GraphRAG (rag/graph_rag.py)
│   ├── 向量 + 图谱融合检索
│   ├── Reranker 重排序
│   └── 语义缓存集成
└── LangGraph 多 Agent 状态图

Phase 4: API 层升级 (1-2 天)
├── API 模块化 (api/routes/)
├── JWT 认证中间件
├── 依赖注入体系
├── 统一异常处理
└── OpenAPI 文档完善

Phase 5: 前端开发 (3-4 天)
├── Next.js 项目初始化 + TailwindCSS
├── shadcn/ui 组件库集成
├── 对话页 (流式渲染 + 录音)
├── 车控页 (控制面板 + 3D 模型)
├── 记忆页 (时间线 + 图谱可视化)
├── 监控页 (实时图表)
├── 架构展示页
└── WebSocket 实时通信

Phase 6: 可观测性 (1-2 天)
├── Prometheus 指标埋点
├── Grafana Dashboard 配置
├── Loki 日志聚合
├── Langfuse Trace 完善
└── 告警规则配置

Phase 7: 部署与测试 (1-2 天)
├── Docker 镜像构建 (前端 + 后端)
├── docker-compose 一键启动
├── Nginx 反向代理配置
├── 健康检查端点
├── 压力测试 (locust/wrk)
└── 文档完善
```

### 10.2 优先级排序

```
最高优先级 (核心展示价值):
  1. 多 Agent 协同 (Planner→Executor→Reviewer→Responder)
  2. GraphRAG (向量+图谱融合)
  3. Redis 语义缓存
  4. Next.js 前端 Dashboard
  5. Docker Compose 一键编排

中优先级 (工程完整度):
  6. Celery 异步任务队列
  7. JWT 认证体系
  8. PostgreSQL 结构化数据
  9. Prometheus + Grafana 监控
  10. Nginx 反向代理

低优先级 (锦上添花):
  11. RabbitMQ 事件总线
  12. 熔断器
  13. MinIO 对象存储
  14. Loki 日志聚合
  15. vLLM 本地推理服务
```

### 10.3 技术展示价值矩阵

| 技术点 | 面试解说价值 | 实现难度 | 展示优先级 |
|--------|-------------|----------|-----------|
| 多 Agent 协同 | ⭐⭐⭐⭐⭐ Agent 架构深度 | 高 | 🔴 最高 |
| GraphRAG | ⭐⭐⭐⭐⭐ RAG 前沿实践 | 中高 | 🔴 最高 |
| 语义缓存 | ⭐⭐⭐⭐ 性能优化思维 | 中 | 🔴 最高 |
| Docker Compose | ⭐⭐⭐⭐ DevOps 能力 | 中 | 🔴 最高 |
| Next.js Dashboard | ⭐⭐⭐⭐ 全栈能力 | 中 | 🔴 最高 |
| Celery 异步 | ⭐⭐⭐ 工程化 | 中 | 🟡 高 |
| JWT 认证 | ⭐⭐⭐ 安全意识 | 低 | 🟡 高 |
| LangGraph HIL | ⭐⭐⭐⭐ Agent 交互设计 | 中 | 🟡 高 |
| 熔断器 | ⭐⭐⭐⭐ 分布式系统 | 中 | 🟡 高 |
| Prometheus | ⭐⭐⭐ 运维能力 | 低 | 🟢 中 |
| RabbitMQ | ⭐⭐⭐ 消息中间件 | 中 | 🟢 中 |
| ReAct 推理 | ⭐⭐⭐⭐⭐ AI 深度 | 中 | 🔴 最高 |

---

## 附录 A：技术栈全景对照表

| 层级 | 技术 | 版本 | 用途 |
|------|------|------|------|
| **前端** | Next.js | 14+ | SSR React 框架 |
| | TailwindCSS | 3.4 | 原子化 CSS |
| | shadcn/ui | latest | 高质量组件库 |
| | Zustand | 4+ | 状态管理 |
| | TanStack Query | 5+ | 数据请求 |
| | Framer Motion | 11+ | 动画 |
| | Recharts | 2+ | 图表 |
| **API** | FastAPI | 0.110+ | RESTful API |
| | Pydantic | 2+ | 数据验证 |
| | python-jose | 3+ | JWT |
| | uvicorn | 0.30+ | ASGI Server |
| **Agent** | LangGraph | 0.2+ | 状态图 Agent |
| | LangChain | 0.2+ | RAG 工具链 |
| **中间件** | Redis | 7+ | 缓存 + 向量 |
| | Celery | 5+ | 异步任务 |
| | RabbitMQ | 3.12+ | 消息队列 |
| | Nginx | 1.24+ | 反向代理 |
| **数据库** | Milvus | 2.4+ | 向量库 |
| | Neo4j | 5+ | 图数据库 |
| | PostgreSQL | 16+ | 关系数据库 |
| | MinIO | latest | 对象存储 |
| **AI 模型** | SenseVoice | - | ASR |
| | CAM++ | - | 声纹识别 |
| | DeepSeek-V3 | - | LLM (API) |
| | Qwen3-4B | - | 本地 LLM |
| | BERT (rbt3) | - | 意图分类 |
| **监控** | Langfuse | 3+ | AI Trace |
| | Prometheus | 2.50+ | 指标采集 |
| | Grafana | 11+ | 可视化 |
| | Loki | 3+ | 日志聚合 |
| **部署** | Docker | 24+ | 容器化 |
| | Docker Compose | 2.20+ | 编排 |

## 附录 B：与现有代码的兼容性

| 现有文件 | 改动程度 | 说明 |
|----------|----------|------|
| `SenseVoice_Agent_Brain.py` | 中等改 | 拆分为多 Agent，保留核心逻辑 |
| `SenseVoice_Agent_Main.py` | 小改 | 接入新的 Agent 编排 |
| `Local_Model.py` | 不改 | 保持模型加载逻辑 |
| `SpeakerManager.py` | 不改 | 保持声纹管理 |
| `Milvus.py` | 小改 | 增加语义缓存查询接口 |
| `Knowledge_Grpah.py` | 小改 | 增加 GraphRAG 查询接口 |
| `intent_router_service.py` | 不改 | Planner Agent 调用 |
| `intent_router_bert.py` | 不改 | 保持 BERT 分类 |
| `skills.py` | 不改 | Executor Agent 调用 |
| `orchestrator.py` | 不改 | Executor Agent 调用 |
| `mcp_gateway.py` | 小改 | 增加审计日志写入 PostgreSQL |
| `vehicle_bus.py` | 不改 | 保持多适配器 |
| `vehicle_mcp_server.py` | 不改 | 保持独立 MCP Server |
| `langfuse_monitor.py` | 小改 | 完善 Trace 结构 |
| `three_layer_pipeline.py` | 中等改 | 升级为多 Agent 流水线 |
| `config.py` | 大改 | 升级为 Pydantic Settings |
| `rag_engine.py` | 大改 | 升级为 GraphRAG |
| `langgraph_agent.py` | 大改 | 升级为多 Agent 图 |
| `api_server.py` | 大改 | 模块化拆分 |
| `demo_webui.py` | 替换 | 由 Next.js 前端替代 |
| `privacy_llm.py` | 小改 | 支持 vLLM 后端 |

---

> **核心原则**：每一层都能独立展示一个技术能力点，整体组合体现全栈工程深度。不是为了用而用，而是每个中间件都解决一个实际问题。
