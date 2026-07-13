---
name: tech-stack-guide
description: 帮助新人系统学习 NexusCockpit 项目技术栈的导航技能。提供每个技术的通俗解释、在项目中的具体位置、学习资源推荐、动手实验路径，覆盖 Python/Go/TypeScript 三语言栈及 AI/数据库/监控/部署全链路。
---

## 权威入口

- `.catpaw/skills/tech-stack-guide/SKILL.md`

## 适用场景

- 新人入职首次了解项目技术栈。
- 需要快速定位某个技术在项目中的使用位置。
- 需要学习某个不熟悉的技术（如 LangGraph、GraphRAG、Milvus 等）。
- 需要为某个技术栈编写学习笔记或培训材料。
- 技术选型时需要了解项目中已有的技术实践。

## 非适用场景

- 不用于代码质量审查（使用 `code-review`）。
- 不用于生成代码注释（使用 `code-doc` 或 `beginner-code-comment`）。
- 不用于架构设计决策（参考 `docs/architecture/` 文档）。

## 技术栈全景图

```
┌─────────────────────────────────────────────────────────────┐
│                      NexusCockpit 技术栈                      │
├──────────┬──────────────────────────────────────────────────┤
│  前端     │ Next.js 14 │ TypeScript │ Tailwind CSS │ Zustand │
│          │ SSE 流式   │ Web Speech API │ lucide-react       │
├──────────┼──────────────────────────────────────────────────┤
│  Go 网关  │ Go │ Gin │ gorilla/websocket │ JWT │ Redis Lua  │
├──────────┼──────────────────────────────────────────────────┤
│  Python   │ FastAPI │ LangGraph │ Celery │ pydantic-settings│
│  AI 服务  │ httpx │ structlog │ prometheus-client            │
├──────────┼──────────────────────────────────────────────────┤
│  AI/ML    │ LLM API (OpenAI 兼容) │ Embedding │ Reranker     │
│          │ GraphRAG │ ASR (SenseVoice) │ TTS (CosyVoice)    │
│          │ 声纹 (CAM++) │ LangGraph Multi-Agent              │
├──────────┼──────────────────────────────────────────────────┤
│  数据存储  │ Milvus (向量) │ Neo4j (图谱) │ MySQL (关系)      │
│          │ Redis (缓存/限流/指标) │ RabbitMQ (消息队列)      │
├──────────┼──────────────────────────────────────────────────┤
│  监控运维  │ Prometheus │ Grafana │ Loki │ Docker Compose    │
│          │ Nginx │ GitHub Actions                              │
└──────────┴──────────────────────────────────────────────────┘
```

## 技术学习卡片

### 🟢 前端技术栈

#### Next.js 14 (App Router)

| 项目 | 说明 |
|------|------|
| **是什么** | React 全栈框架，支持 SSR/SSG/ISR，v14 使用 App Router |
| **为什么选它** | 文件即路由、内置 API 代理、图片优化、代码分割 |
| **项目位置** | `frontend_design/src/app/` 下每个文件夹是一个路由 |
| **学习要点** | `layout.tsx`（根布局）、`page.tsx`（页面）、`loading.tsx`（加载态） |
| **推荐资源** | [Next.js 官方文档](https://nextjs.org/docs)、[App Router 指南](https://nextjs.org/docs/app) |
| **动手实验** | 在 `src/app/` 下新建 `demo/page.tsx`，访问 `localhost:3000/demo` |

#### TypeScript

| 项目 | 说明 |
|------|------|
| **是什么** | JavaScript 的超集，添加静态类型系统 |
| **为什么选它** | 编译时类型检查、IDE 智能提示、重构更安全 |
| **项目位置** | `frontend_design/src/types/index.ts` 集中定义所有类型 |
| **学习要点** | `interface`/`type`、泛型、联合类型、`as` 断言 |
| **推荐资源** | [TypeScript 中文文档](https://www.typescriptlang.org/zh/) |
| **动手实验** | 在 `types/index.ts` 中定义一个新的接口，然后在组件中使用 |

#### Tailwind CSS

| 项目 | 说明 |
|------|------|
| **是什么** | 原子化 CSS 框架，用类名直接写样式 |
| **为什么选它** | 无需切换 CSS 文件、一致的设计系统、包体小 |
| **项目位置** | `frontend_design/tailwind.config.ts` 配置 |
| **学习要点** | `flex`/`grid` 布局、`p-4`/`gap-2` 间距、`text-sm` 字体、`hover:` 变体 |
| **推荐资源** | [Tailwind CSS 交互教程](https://tailwindcss.com/docs) |
| **动手实验** | 用 Tailwind 类名写一个响应式卡片组件 |

#### Zustand

| 项目 | 说明 |
|------|------|
| **是什么** | 轻量级 React 状态管理库，比 Redux 简单 |
| **为什么选它** | API 简洁、支持 TypeScript、中间件生态（persist/devtools） |
| **项目位置** | `frontend_design/src/stores/chat-store.ts`、`auth-store.ts` |
| **学习要点** | `create()` 创建 store、`persist` 持久化、`selector` 选择性订阅 |
| **推荐资源** | [Zustand GitHub](https://github.com/pmndrs/zustand) |
| **动手实验** | 创建一个 `useSettingsStore`，管理主题/语言设置 |

#### SSE 流式通信

| 项目 | 说明 |
|------|------|
| **是什么** | Server-Sent Events，服务器单向推送 |
| **为什么选它** | 比 WebSocket 简单、基于 HTTP、自动重连 |
| **项目位置** | 前端 `src/lib/api.ts` → `streamMessage()`；后端 `nexus/api/routes/chat.py` → `chat_stream()` |
| **学习要点** | `fetch` + `ReadableStream` 读取、`TextDecoder` 解码、`data: ` 前缀解析 |
| **推荐资源** | [MDN SSE 文档](https://developer.mozilla.org/zh-CN/docs/Web/API/Server-sent_events) |
| **动手实验** | 在 `api.ts` 中阅读 `streamMessage` 函数，画出数据流图 |

### 🔵 Go 网关技术栈

#### Go + Gin

| 项目 | 说明 |
|------|------|
| **是什么** | Go 语言 + Gin Web 框架 |
| **为什么选它** | 高并发、低内存、编译为单二进制、适合网关场景 |
| **项目位置** | `backend_design/nexus_gate/cmd/main.go`（入口）、`internal/router/router.go`（路由） |
| **学习要点** | `gin.Engine`、路由组 `Group()`、中间件链、`c.JSON()` 响应 |
| **推荐资源** | [Gin 官方文档](https://gin-gonic.com/docs/)、[Go 语言之旅](https://tour.go-zh.org/) |
| **动手实验** | 在 `handlers.go` 中新增一个 `GetCustomData` 处理器，在 `router.go` 中注册路由 |

#### JWT 鉴权

| 项目 | 说明 |
|------|------|
| **是什么** | JSON Web Token，无状态身份认证令牌 |
| **为什么选它** | 无需服务端存储、跨服务传递、自带过期时间 |
| **项目位置** | `nexus_gate/internal/auth/jwt.go`（Go 端）、`nexus/core/auth.py`（Python 端） |
| **学习要点** | Header.Payload.Signature 三段式、`HS256` 签名、Claims 自定义字段、RBAC 角色 |
| **推荐资源** | [JWT.io](https://jwt.io/)、[JWT 最佳实践](https://datatracker.ietf.org/doc/html/rfc7519) |
| **动手实验** | 在 `jwt.go` 中阅读 `GenerateToken` 和 `ParseToken`，理解签名和验证流程 |

#### Redis Lua 限流

| 项目 | 说明 |
|------|------|
| **是什么** | 用 Redis + Lua 脚本实现原子化限流 |
| **为什么选它** | Lua 脚本在 Redis 中原子执行、避免竞态条件 |
| **项目位置** | `nexus_gate/internal/ratelimit/ratelimit.go` |
| **学习要点** | 令牌桶算法、High/Normal/Low 三级优先级、`EVALSHA` 执行脚本 |
| **推荐资源** | [Redis Lua 脚本](https://redis.io/docs/manual/programmability/lua/) |
| **动手实验** | 阅读 `ratelimit.go` 中的 Lua 脚本，理解令牌桶的添加和消费逻辑 |

#### WebSocket Hub

| 项目 | 说明 |
|------|------|
| **是什么** | Go 管理千级 WebSocket 连接的中心枢纽 |
| **为什么选它** | 统一管理连接生命周期、广播消息、座舱级隔离 |
| **项目位置** | `nexus_gate/internal/ws/hub.go` |
| **学习要点** | `Hub.Run()` 事件循环、`register`/`unregister`/`broadcast` 通道、`readPump`/`writePump` |
| **推荐资源** | [gorilla/websocket](https://github.com/gorilla/websocket) |
| **动手实验** | 画出 Hub 的连接管理流程图，标注 register/unregister/broadcast 三个通道 |

### 🟡 Python AI 服务技术栈

#### FastAPI

| 项目 | 说明 |
|------|------|
| **是什么** | 现代 Python Web 框架，支持异步、自动文档 |
| **为什么选它** | 原生 async、Pydantic 类型校验、自动 OpenAPI 文档 |
| **项目位置** | `backend_design/nexus/main.py`（入口）、`nexus/api/routes/`（路由） |
| **学习要点** | `lifespan` 上下文管理、`@router.post()` 路由装饰器、`Depends` 依赖注入 |
| **推荐资源** | [FastAPI 官方文档](https://fastapi.tiangolo.com/zh/) |
| **动手实验** | 在 `api/routes/` 下新建一个路由文件，实现一个简单的 CRUD 端点 |

#### LangGraph (Multi-Agent)

| 项目 | 说明 |
|------|------|
| **是什么** | LangChain 的图式 Agent 编排框架 |
| **为什么选它** | 支持条件路由、并行节点、状态共享、检查点恢复 |
| **项目位置** | `backend_design/nexus/agent/supervisor_graph.py` |
| **学习要点** | `StateGraph` 状态图、`add_node` 添加节点、`add_conditional_edges` 条件路由、`SupervisorState` 共享状态 |
| **推荐资源** | [LangGraph 文档](https://langchain-ai.github.io/langgraph/) |
| **动手实验** | 画出 Supervisor → Experts → Responder → Reviewer 的图结构，标注条件路由 |

#### GraphRAG (三路检索 + Rerank)

| 项目 | 说明 |
|------|------|
| **是什么** | 图增强检索增强生成，融合三种检索方式 |
| **为什么选它** | 单一向量检索不够精确，融合图谱关系和关键词提高召回率 |
| **三路检索** | ① 向量语义搜索 (Milvus) ② 图谱关系遍历 (Neo4j) ③ 关键词匹配 (BM25) |
| **融合算法** | RRF (Reciprocal Rank Fusion) — 排名倒数加权求和 |
| **二次排序** | Reranker (BGE CrossEncoder) — 对召回结果精细排序 |
| **项目位置** | `backend_design/nexus/rag/retriever.py`（检索器）、`reranker.py`（重排器） |
| **推荐资源** | [RAG 综述论文](https://arxiv.org/abs/2312.10997)、[RRF 算法说明](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf) |

#### Celery 异步任务队列

| 项目 | 说明 |
|------|------|
| **是什么** | Python 分布式任务队列框架 |
| **为什么选它** | 将耗时操作（记忆存储、缓存清理）从主请求剥离 |
| **架构** | Broker (RabbitMQ) → Worker (Celery) → Backend (Redis) |
| **项目位置** | `backend_design/nexus/middleware/task_queue.py` |
| **学习要点** | `@celery_app.task` 装饰器、`task_time_limit` 超时、`worker_prefetch_multiplier` 预取 |
| **推荐资源** | [Celery 官方文档](https://docs.celeryq.dev/) |
| **动手实验** | 阅读 `task_store_memory` 函数，理解同步 Worker 中如何桥接异步代码 |

### 🟠 数据存储技术栈

#### Milvus (向量数据库)

| 项目 | 说明 |
|------|------|
| **是什么** | 开源向量数据库，专为 AI 应用设计 |
| **为什么选它** | 十亿级向量毫秒搜索、HNSW 索引、水平扩展 |
| **项目位置** | `backend_design/nexus/rag/vector_store.py` |
| **学习要点** | Collection/Schema、HNSW 索引参数 (`ef`/`M`)、`IP` 内积相似度 |
| **推荐资源** | [Milvus 官方文档](https://milvus.io/docs) |

#### Neo4j (图数据库)

| 项目 | 说明 |
|------|------|
| **是什么** | 原生图数据库，用节点和关系存储数据 |
| **为什么选它** | 高效遍历关系、Cypher 查询语言直观 |
| **项目位置** | `backend_design/nexus/rag/graph_store.py` |
| **学习要点** | `MERGE` 幂等写入、`MATCH` 查询、`coalesce()` 处理空值 |
| **推荐资源** | [Neo4j Cypher Manual](https://neo4j.com/docs/cypher-manual/current/) |

#### Redis (多用途缓存)

| 项目 | 说明 |
|------|------|
| **是什么** | 内存键值数据库 |
| **项目中的角色** | ① 语义缓存 ② 限流计数 ③ Celery Backend ④ 指标暂存 ⑤ 会话存储 |
| **项目位置** | `nexus/middleware/redis_cache.py`（缓存）、`ratelimit.go`（限流） |
| **学习要点** | RediSearch KNN 向量搜索、Lua 原子脚本、TTL 过期 |
| **推荐资源** | [Redis 官方文档](https://redis.io/docs/) |

### 🟣 监控运维技术栈

#### Prometheus + Grafana

| 项目 | 说明 |
|------|------|
| **是什么** | 指标采集 + 可视化面板 |
| **项目位置** | `nexus/observability/metrics.py`（指标定义）、`config/prometheus/`（采集配置）、`config/grafana/`（面板配置） |
| **学习要点** | Counter/Histogram/Gauge 四种指标类型、PromQL 查询语言 |
| **推荐资源** | [Prometheus 文档](https://prometheus.io/docs/)、[Grafana 文档](https://grafana.com/docs/) |

#### Docker Compose

| 项目 | 说明 |
|------|------|
| **是什么** | 多容器 Docker 编排工具 |
| **项目位置** | `docker-compose.yml`（基础设施编排） |
| **学习要点** | `services` 定义、`depends_on` 依赖、`volumes` 持久化、`healthcheck` 健康检查 |
| **推荐资源** | [Docker Compose 文档](https://docs.docker.com/compose/) |

## 学习路径推荐

### 路径 A: 全栈学习（12-16 小时）
按 `docs/learning-roadmap.md` 的 6 个阶段逐步学习。

### 路径 B: 前端专项（4-6 小时）
1. Next.js App Router 基础 → 2. 阅读 `layout.tsx` + `sidebar.tsx` → 3. TypeScript 类型 → 4. Zustand 状态 → 5. SSE 流式 → 6. 动手改 ChatWindow

### 路径 C: 后端 AI 专项（6-8 小时）
1. FastAPI 基础 → 2. 阅读 `main.py` lifespan → 3. LangGraph 概念 → 4. 阅读 `supervisor_graph.py` → 5. GraphRAG 检索 → 6. 动手加一个 Expert

### 路径 D: Go 网关专项（2-4 小时）
1. Go 基础语法 → 2. Gin 框架 → 3. 阅读 `router.go` → 4. JWT 鉴权 → 5. 限流 Lua → 6. WebSocket Hub

### 路径 E: 运维部署专项（2-3 小时）
1. Docker 基础 → 2. 阅读 `docker-compose.yml` → 3. Prometheus 指标 → 4. Grafana 面板 → 5. Nginx 代理

## 常见陷阱

- 试图一次学完所有技术，建议按路径分专项学习。
- 只看代码不动手，建议每个技术至少做一个 mini 实验。
- 忽略 `.env` 配置，很多技术需要 API Key 才能实际运行。
- 跳过基础直接看高级代码（如不看 FastAPI 基础直接看 LangGraph）。
- 只关注 Python 端，忽略 Go 网关和前端的协同关系。
