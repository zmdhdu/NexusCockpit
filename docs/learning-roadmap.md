# NexusCockpit 项目学习路线图

> 面向编程新手小白的全栈学习指南。按此路线图逐步学习，预计 **12-16 小时**可全面掌握项目架构与细节。

---

## 学习总览

```
阶段 1: 项目全局认知          (1-2h)  ← 先看大图，理解"是什么"
  ↓
阶段 2: 后端核心层 (L1-L3)     (3-4h)  ← Python 服务入口 → 配置 → 数据层 → 服务层
  ↓
阶段 3: Agent 与 RAG (L4+L2)   (3-4h)  ← 核心智能: 多Agent编排 + GraphRAG检索
  ↓
阶段 4: 前端架构 (Next.js)     (2-3h)  ← 页面 → 组件 → 状态管理 → API通信
  ↓
阶段 5: Go 并发网关            (1-2h)  ← JWT鉴权 + 限流 + WebSocket + 反向代理
  ↓
阶段 6: 基础设施与运维          (1-2h)  ← Docker编排 + Prometheus监控 + 部署
```

---

## 阶段 1: 项目全局认知 (1-2 小时)

> **目标**: 理解项目是做什么的、用了哪些技术、整体架构长什么样。

### 1.1 阅读项目说明 (30 分钟)

| 顺序 | 文件 | 学到什么 |
|------|------|----------|
| ① | `README.md` | 项目概述、技术栈速览、快速启动命令 |
| ② | `Agent.md` | 项目总导航、目录结构全貌、修改代码时的查找路径 |
| ③ | `docs/architecture/overview.md` | 7 层架构总览与数据流设计（先理解整体架构方向） |

### 1.2 理解 7 层架构 (30 分钟)

```
L7  可观测层    →  Langfuse / Prometheus / Grafana         ← 监控和追踪
L6  API 层      →  FastAPI REST / SSE / WebSocket / JWT     ← 对外接口
L5  中间件层    →  Redis 语义缓存 / 限流 / Celery           ← 性能优化
L4  Agent 层    →  Supervisor → 5 Expert Agents → Responder ← AI大脑
L3  服务层      →  ASR / TTS / Skills / Vehicle / Intent    ← 具体能力
L2  数据层      →  GraphRAG / Memory / Vector / Graph       ← 知识和记忆
L1  核心层      →  Config / Logger / Exceptions             ← 基础设施
L0  基础设施层  →  Docker / Milvus / Neo4j / Redis / MySQL  ← 底层依赖
```

**关键概念**:
- **Multi-Agent**: 不是单个 AI，而是 1 个调度者(Supervisor) + 5 个专家(车控/导航/生活/健康/闲聊)协同工作
- **GraphRAG**: 同时用 3 种方式搜索知识（向量语义 + 图谱关系 + 关键词），再融合排序
- **座舱控制 + 运营总览**: 座舱控制台提供车控与语音交互，运营总览看板提供系统监控与数据分析

### 1.3 画出数据流 (30 分钟)

试着用纸笔画出这个流程:
```
用户说话 → [Go网关: JWT验证+限流] → [FastAPI: 路由分发]
  → [语义缓存: 查Redis看有没有相似问题]
  → [Supervisor: 记忆召回 + 意图路由]
  → [Expert并行: 车控/导航/生活/健康/闲聊 同时工作]
  → [Responder: 汇总结果 + LLM生成回复]
  → [Reviewer: 质量检查 + 存记忆]
  → [SSE流式返回前端]
```

### ✅ 阶段 1 检查点
- [ ] 能用一句话描述项目是做什么的
- [ ] 能说出 7 层架构每层的作用
- [ ] 知道 Multi-Agent 的基本流程
- [ ] 知道前端和后端分别用什么技术

---

## 阶段 2: 后端核心层 L1-L3 (3-4 小时)

> **目标**: 理解 Python 后端的启动流程、配置管理、数据层和服务层。

### 2.1 服务入口与配置 (1 小时)

| 顺序 | 文件 | 学到什么 | 重点 |
|------|------|----------|------|
| ① | `backend_design/nexus/main.py` | FastAPI 启动流程 | `lifespan()` 函数中 10 个初始化步骤的顺序 |
| ② | `backend_design/nexus/config.py` | 配置中心 | Pydantic Settings 如何从 .env 读取配置；双模式开关 `*_PROVIDER` |
| ③ | `.env.example` | 所有环境变量 | 每个变量的作用和默认值 |
| ④ | `backend_design/nexus/core/logger.py` | 结构化日志 | 为什么用 structlog 而不是 print |

**学习要点**:
- `main.py` 的 `lifespan()` 是理解整个后端的"地图"——它按顺序初始化了所有组件
- `config.py` 用了**工厂模式**: 每个子系统(LLM/Milvus/Redis...)都有独立的配置类，最后聚合到 `AppConfig`
- **双模式部署**: `local` 用 Docker 本地中间件，`cloud` 用云端托管服务，代码不用改

### 2.2 数据层 L2 — GraphRAG 与记忆 (1.5 小时)

| 顺序 | 文件 | 学到什么 | 重点 |
|------|------|----------|------|
| ① | `nexus/rag/embedding.py` | 文本向量化 | 如何调用 OpenAI 兼容 API 把文字变成数字向量 |
| ② | `nexus/rag/vector_store.py` | Milvus 向量存储 | HNSW 索引、collection 创建、相似度搜索 |
| ③ | `nexus/rag/zilliz_vector_store.py` | Zilliz 云端向量库 | 工厂模式如何切换本地/云端 |
| ④ | `nexus/rag/graph_store.py` | Neo4j 图谱存储 | Cypher 查询语言、用户画像存储 |
| ⑤ | `nexus/rag/retriever.py` | GraphRAG 检索器 | **核心**: 三路召回(向量+图谱+BM25) + RRF 融合 + Rerank |
| ⑥ | `nexus/rag/reranker.py` | 本地 BGE 重排器 | CrossEncoder 如何对召回结果二次排序 |
| ⑦ | `nexus/rag/unified_retriever.py` | 统一检索路由 | 根据 query_type 分发到不同知识库 |
| ⑧ | `nexus/rag/cherry_kb.py` | Cherry 知识库 | 车手册/故障码/FAQ 的管理 |
| ⑨ | `nexus/memory/manager.py` | 记忆管理器 | 短期/长期记忆、记忆召回与存储 |
| ⑩ | `nexus/memory/compressor.py` | 上下文压缩器 | 4 级渐进式压缩策略 |

**关键设计模式**:
- **工厂模式**: `vector_factory.py`、`graph_factory.py`、`reranker_factory.py` 根据 `*_PROVIDER` 创建不同实现
- **策略模式**: Rerank 支持 local(本地BGE) / cloud(硅基流动API) / none(跳过)
- **RRF 融合**: Reciprocal Rank Fusion — 把三个检索器的排名倒数加权求和

### 2.3 服务层 L3 (1 小时)

| 顺序 | 文件 | 学到什么 | 重点 |
|------|------|----------|------|
| ① | `nexus/intent/router.py` | 意图路由 | 如何判断用户输入交给哪个专家处理 |
| ② | `nexus/intent/heuristic.py` | 启发式意图识别 | 关键词匹配 + 规则引擎 |
| ③ | `nexus/skills/registry.py` | 技能注册中心 | 装饰器自动发现 + 技能元数据管理 |
| ④ | `nexus/skills/orchestrator.py` | 技能编排器 | 如何协调多个技能的执行 |
| ⑤ | `nexus/skills/vehicle/navigation.py` | 导航技能 | 一个具体技能长什么样 |
| ⑥ | `nexus/vehicle/factory.py` | 车控适配工厂 | mock/http/mcp 三种模式切换 |
| ⑦ | `nexus/vehicle/mock.py` | Mock 车控 | 开发模式下的模拟车辆响应 |
| ⑧ | `nexus/asr/engine.py` | 语音识别引擎 | FunASR SenseVoice 模型加载 |
| ⑨ | `nexus/tts/engine.py` | 语音合成引擎 | CosyVoice 模型加载 |

### ✅ 阶段 2 检查点
- [ ] 能描述 `main.py` 启动时 10 个初始化步骤的顺序和作用
- [ ] 理解 Pydantic Settings 如何从 `.env` 加载配置
- [ ] 能解释 GraphRAG 三路召回 + RRF 融合 + Rerank 的流程
- [ ] 知道工厂模式在双模式部署中的作用
- [ ] 理解记忆系统的短期/长期记忆机制

---

## 阶段 3: Agent 层与 RAG 深入 (3-4 小时)

> **目标**: 深入理解 Multi-Agent 工作流、SubAgent 监控、MainAgent 确认层。

### 3.1 Multi-Agent 编排核心 (1.5 小时)

| 顺序 | 文件 | 学到什么 | 重点 |
|------|------|----------|------|
| ① | `nexus/agent/supervisor_graph.py` | **Agent 编排核心** | LangGraph StateGraph 图结构、Supervisor 节点、并行专家节点 |
| ② | `nexus/models/state.py` | Agent 状态定义 | `SupervisorState` TypedDict 的所有字段 |
| ③ | `nexus/agent/experts/base.py` | 专家基类 | 所有专家共享的接口和逻辑 |
| ④ | `nexus/agent/experts/vehicle_expert.py` | 车控专家 | 如何调用技能、执行车控 |
| ⑤ | `nexus/agent/experts/nav_expert.py` | 导航专家 | 导航意图处理 |
| ⑥ | `nexus/agent/experts/chat_expert.py` | 闲聊专家 | 纯对话场景处理 |
| ⑦ | `nexus/agent/responder.py` | 回复汇总器 | 如何把多专家结果合并成一条回复 + LLM 流式生成 |
| ⑧ | `nexus/agent/reviewer.py` | 质量审查器 | 回复质量检查 + 记忆存储触发 |

**LangGraph 关键概念**:
```python
# 图结构示意 (不是实际代码，用于理解)
graph = StateGraph(SupervisorState)
graph.add_node("supervisor", supervisor_node)     # 调度节点
graph.add_node("vehicle_expert", vehicle_node)     # 车控专家
graph.add_node("nav_expert", nav_node)             # 导航专家
graph.add_node("responder", responder_node)       # 回复汇总
graph.add_node("reviewer", reviewer_node)         # 质量审查

# 条件路由: Supervisor 决定激活哪些专家
graph.add_conditional_edges("supervisor", route_experts)
# 专家完成后都汇聚到 Responder
graph.add_edge("vehicle_expert", "responder")
graph.add_edge("nav_expert", "responder")
graph.add_edge("responder", "reviewer")
graph.add_edge("reviewer", END)
```

### 3.2 座舱管理与运营总览 (1 小时)

| 顺序 | 文件 | 学到什么 | 重点 |
|------|------|----------|------|
| ① | `nexus/core/cockpit_manager.py` | 座舱管理器 | 座舱注册/查询/状态管理 |
| ② | `nexus/core/tenant_context.py` | 多租户上下文 | 请求级 cockpit_id 隔离机制 |
| ③ | `nexus/core/db_manager.py` | 异步数据库管理器 | MySQL 连接池 + 日志持久化 |
| ④ | `nexus/core/voiceprint.py` | 声纹识别 | CAM++ 模型 + 说话人验证 |
| ⑤ | `nexus/core/personalization.py` | 个性化服务 | 声纹+偏好匹配+Prompt 注入 |
| ⑥ | `nexus/models/cockpit.py` | 座舱数据模型 | Cockpit/AlertRecord/AgentActivity 等类型定义 |

**架构理解**:
```
座舱控制台 ──┐
语音助手   ──┼── Go网关 ──→ Python AI服务
运营总览   ──┘              Supervisor+5专家
```

### 3.3 API 层 L6 (1 小时)

| 顺序 | 文件 | 学到什么 | 重点 |
|------|------|----------|------|
| ① | `nexus/api/routes/chat.py` | 对话接口 | SSE 流式响应的实现 |
| ② | `nexus/api/routes/auth.py` | 认证接口 | JWT Token 签发与验证 |
| ③ | `nexus/api/routes/cockpit.py` | 座舱接口 | 座舱路由 `/cockpit/{id}/*` |
| ④ | `nexus/api/routes/dataplatform.py` | 数据中台 | 跨座舱统计、并发监控、告警历史 |
| ⑤ | `nexus/api/routes/middleware_status.py` | 中间件状态 | Redis/Milvus/Neo4j 等连通性检查 |
| ⑥ | `nexus/api/routes/settings.py` | 设置中心 | 座舱CRUD、用户管理、声纹注册 |
| ⑦ | `nexus/api/routes/health.py` | 健康检查 | 版本号、各组件连接状态 |
| ⑧ | `nexus/api/websocket.py` | WebSocket | 实时双向通信 |

### ✅ 阶段 3 检查点
- [ ] 能描述 Supervisor → Experts → Responder → Reviewer 的工作流
- [ ] 理解 LangGraph 的 StateGraph、条件路由、并行节点
- [ ] 知道 SubAgent 监控和 MainAgent 确认的作用
- [ ] 理解多租户隔离机制（Redis DB / Milvus 前缀 / MySQL 行级）
- [ ] 能解释 SSE 流式响应的实现原理

---

## 阶段 4: 前端架构 (2-3 小时)

> **目标**: 理解 Next.js 前端的页面结构、组件设计、状态管理和 API 通信。

### 4.1 前端入口与路由 (30 分钟)

| 顺序 | 文件 | 学到什么 | 重点 |
|------|------|----------|------|
| ① | `frontend_design/src/app/layout.tsx` | 全局布局 | 根布局、Sidebar 挂载 |
| ② | `frontend_design/src/app/page.tsx` | 首页 | 重定向到 /cockpit |
| ③ | `frontend_design/next.config.js` | Next.js 配置 | API 代理重写规则 |
| ④ | `frontend_design/.env.local` | 前端环境变量 | `NEXT_PUBLIC_API_URL` 指向 Go 网关 |

**Next.js App Router 理解**:
- `src/app/` 下每个文件夹就是一个路由
- `cockpit/` → 座舱控制页、`chat/` → 聊天页、`dashboard/` → 运营总览
- `admin/` → 管理设置、`middleware/` → 中间件监控、`dataplatform/` → 数据中台

### 4.2 核心组件 (1 小时)

| 顺序 | 文件 | 学到什么 | 重点 |
|------|------|----------|------|
| ① | `src/components/layout/sidebar.tsx` | 侧边栏导航 | 菜单分组、RBAC 角色控制 |
| ② | `src/components/chat/chat-window.tsx` | 聊天窗口 | SSE 流式接收、消息渲染、AbortController 取消 |
| ③ | `src/components/vehicle/voice-assistant-bar.tsx` | 语音助手条 | 语音输入 + TTS 播报 + 流式取消 |
| ④ | `src/components/vehicle/vehicle-panel.tsx` | 车控面板 | 车辆状态展示、车控指令发送 |
| ⑤ | `src/components/vehicle/vehicle-3d.tsx` | 3D 车辆模型 | 3D 可视化展示 |

### 4.3 状态管理与 API 通信 (1 小时)

| 顺序 | 文件 | 学到什么 | 重点 |
|------|------|----------|------|
| ① | `src/stores/chat-store.ts` | 聊天状态 | Zustand + persist 持久化、座舱切换清空消息 |
| ② | `src/stores/auth-store.ts` | 认证状态 | JWT Token 管理、RBAC 角色控制 |
| ③ | `src/lib/api.ts` | API 客户端 | **核心**: axios 实例、JWT 自动附加、SSE 流式读取、401 自动刷新 |
| ④ | `src/lib/tts.ts` | TTS 工具 | 浏览器 Web Speech API 语音播报 |
| ⑤ | `src/lib/vehicle-events.ts` | 车辆事件 | 车控事件订阅与分发 |
| ⑥ | `src/hooks/use-speech-recognition.ts` | 语音识别 Hook | 浏览器 SpeechRecognition API 封装 |
| ⑦ | `src/types/index.ts` | TypeScript 类型 | 所有接口类型定义 |

**前端核心技术**:
- **Zustand**: 比 Redux 更简单的全局状态管理，用 `create()` 创建 store
- **SSE 流式**: 用原生 `fetch` + `ReadableStream` 逐块读取后端 SSE 事件
- **AbortController**: 用户切换对话时取消正在进行的流式请求
- **JWT 自动管理**: 请求拦截器自动附加 Token，401 时自动刷新

### ✅ 阶段 4 检查点
- [ ] 能描述前端页面路由结构
- [ ] 理解 Zustand 状态管理的工作原理
- [ ] 能解释 SSE 流式请求的完整流程（从发送到逐块接收）
- [ ] 知道 JWT Token 的自动获取、附加、刷新机制
- [ ] 理解座舱切换时状态隔离的实现

---

## 阶段 5: Go 并发网关 (1-2 小时)

> **目标**: 理解 Go 网关的路由分发、JWT 鉴权、限流和 WebSocket Hub。

### 5.1 Go 网关核心 (1.5 小时)

| 顺序 | 文件 | 学到什么 | 重点 |
|------|------|----------|------|
| ① | `nexus_gate/cmd/main.go` | Go 网关入口 | Gin 启动、反向代理初始化 |
| ② | `nexus_gate/internal/router/router.go` | **路由分发核心** | Go原生处理 vs 转发Python 的分类策略 |
| ③ | `nexus_gate/internal/auth/jwt.go` | JWT 鉴权 | Token 生成、解析、座舱访问权限校验 |
| ④ | `nexus_gate/internal/ratelimit/ratelimit.go` | 优先级限流 | 令牌桶算法、高/中/低三级优先级 |
| ⑤ | `nexus_gate/internal/proxy/proxy.go` | 反向代理 | 转发到 Python FastAPI 服务 |
| ⑥ | `nexus_gate/internal/ws/hub.go` | WebSocket Hub | 连接管理、消息广播、座舱级隔离 |
| ⑦ | `nexus_gate/internal/handlers/handlers.go` | Go 原生处理器 | 健康检查、数据中台统计(查Redis) |
| ⑧ | `nexus_gate/internal/config/config.go` | Go 配置 | 从环境变量读取配置 |

**Go 网关的路由策略**:
```
请求进来
  ├── /health, /auth/token, /metrics        → Go 原生处理 (快)
  ├── /dataplatform/overview, /alerts       → Go 原生查 Redis (快)
  ├── /middleware/*                          → Go 原生 TCP 检查 (快)
  ├── /settings/cockpits (GET)              → Go 原生返回配置 (快)
  ├── /cockpit/*/chat, /vehicle, /asr, /tts → 转发 Python (需要AI)
  ├── /settings/cockpits (POST/PUT/DELETE)  → 转发 Python (需要MySQL)
  └── /cockpit/*/ws/chat                    → WebSocket Hub
```

### ✅ 阶段 5 检查点
- [ ] 理解 Go 网关的路由分类策略（哪些 Go 处理，哪些转发 Python）
- [ ] 能解释 JWT Token 的生成、解析、座舱权限校验流程
- [ ] 理解优先级限流的三级策略
- [ ] 知道 WebSocket Hub 的连接管理和消息广播机制

---

## 阶段 6: 基础设施与运维 (1-2 小时)

> **目标**: 理解 Docker 编排、监控体系、数据库迁移和部署流程。

### 6.1 Docker 编排 (30 分钟)

| 顺序 | 文件 | 学到什么 | 重点 |
|------|------|----------|------|
| ① | `docker-compose.yml` | 基础设施编排 | 所有服务定义、端口映射、依赖关系 |
| ② | `backend_design/Dockerfile` | 后端容器构建 | Python 环境构建 |
| ③ | `frontend_design/Dockerfile` | 前端容器构建 | Next.js standalone 构建 |
| ④ | `config/nginx/` | Nginx 配置 | 反向代理、负载均衡 |

### 6.2 监控体系 (30 分钟)

| 顺序 | 文件 | 学到什么 | 重点 |
|------|------|----------|------|
| ① | `nexus/observability/metrics.py` | Prometheus 指标 | Counter/Histogram/Gauge 定义 |
| ② | `nexus/observability/cockpit_metrics.py` | 座舱指标 | 每座舱的对话数、延迟、告警 |
| ③ | `nexus/observability/langfuse.py` | Langfuse 追踪 | LLM 调用链路追踪 |
| ④ | `nexus/observability/data_retention.py` | 数据保留策略 | 自动清理过期日志 |
| ⑤ | `config/prometheus/prometheus.yml` | Prometheus 配置 | 抓取目标定义 |
| ⑥ | `config/grafana/provisioning/` | Grafana 面板 | Dashboard 自动 provisioning |

### 6.3 数据库与迁移 (30 分钟)

| 顺序 | 文件 | 学到什么 | 重点 |
|------|------|----------|------|
| ① | `backend_design/scripts/v2.1_migration.sql` | v2.1 数据库迁移 | 建表语句、索引、外键 |
| ② | `backend_design/nexus/core/db_manager.py` | 异步数据库管理 | MySQL 连接池、CRUD 操作 |

### 6.4 测试与脚本 (30 分钟)

| 顺序 | 文件 | 学到什么 | 重点 |
|------|------|----------|------|
| ① | `backend_design/tests/test_v21.py` | 测试用例 | 座舱管理功能验证 |
| ② | `backend_design/scripts/test_api.py` | API 测试脚本 | 接口功能验证 |
| ③ | `backend_design/scripts/chaos_test.py` | 混沌测试 | 异常场景模拟 |
| ④ | `backend_design/scripts/test_db.py` | 数据库测试 | MySQL 连接与 CRUD 验证 |

### ✅ 阶段 6 检查点
- [ ] 能描述 docker-compose.yml 中定义了哪些服务
- [ ] 理解 Prometheus + Grafana 监控体系
- [ ] 知道数据库迁移脚本创建了哪些表
- [ ] 了解测试脚本的覆盖范围

---

## 实战练习：动手验证

完成以上 6 个阶段的学习后，按以下步骤实战验证:

### Step 1: 启动基础设施
```bash
docker compose up -d
```
验证: `docker compose ps` 看所有服务是否 `running`

### Step 2: 启动后端
```bash
cd backend_design
make dev
```
验证: 访问 `http://localhost:8000/docs` 看 Swagger 文档

### Step 3: 启动 Go 网关
```bash
cd backend_design/nexus_gate
go run cmd/main.go
```
验证: 访问 `http://localhost:8080/health` 看健康检查

### Step 4: 启动前端
```bash
cd frontend_design
npm run dev
```
验证: 访问 `http://localhost:3000/cockpit` 看座舱页面

### Step 5: 端到端测试
1. 在聊天框输入 "把空调调到 24 度" → 观察车控面板变化
2. 输入 "导航到上海虹桥" → 观察导航响应
3. 切换座舱 → 观察消息隔离
4. 访问 `/dashboard` → 查看运营数据
5. 访问 `/middleware` → 查看中间件状态

---

## 学习建议

1. **边读边画图**: 每读完一个模块，画一张流程图或架构图，加深理解
2. **加注释**: 用 `beginner-code-comment` 技能为看不懂的代码添加中文注释
3. **动手改**: 尝试修改一个小功能（如加一个新技能），加深理解
4. **看日志**: 启动服务后观察控制台日志，理解运行时行为
5. **用 Swagger**: 在 `/docs` 页面测试每个 API，理解输入输出
6. **分模块学**: 不要试图一次看懂所有代码，按阶段逐步深入

## 知识点速查表

| 概念 | 通俗解释 | 在项目中的位置 |
|------|----------|----------------|
| **FastAPI** | Python 的 Web 框架，类似 Flask 但支持异步 | `nexus/main.py` |
| **LangGraph** | 编排多个 AI Agent 协同工作的框架 | `nexus/agent/supervisor_graph.py` |
| **Milvus** | 专门存储和搜索"向量"的数据库 | `nexus/rag/vector_store.py` |
| **Neo4j** | 图数据库，存储关系和画像 | `nexus/rag/graph_store.py` |
| **Redis** | 内存缓存，用于语义缓存和限流 | `nexus/middleware/redis_cache.py` |
| **SSE** | Server-Sent Events，服务器逐块推送数据 | `nexus/api/routes/chat.py` |
| **JWT** | JSON Web Token，用户身份认证令牌 | `nexus_gate/internal/auth/jwt.go` |
| **Zustand** | 前端状态管理库，比 Redux 简单 | `frontend_design/src/stores/` |
| **GraphRAG** | 图增强检索，结合向量+图谱+全文三路搜索 | `nexus/rag/retriever.py` |
| **RRF** | Reciprocal Rank Fusion，排名倒数融合 | `nexus/rag/retriever.py` |
| **Rerank** | 对检索结果二次排序，提高准确性 | `nexus/rag/reranker.py` |
| **Embedding** | 把文字转换成数字向量 | `nexus/rag/embedding.py` |
| **ASR** | Automatic Speech Recognition，语音识别 | `nexus/asr/engine.py` |
| **TTS** | Text-To-Speech，文字转语音 | `nexus/tts/engine.py` |
| **MCP** | Model Context Protocol，AI 工具调用协议 | `nexus/mcp/gateway.py` |
| **RBAC** | Role-Based Access Control，基于角色的权限控制 | `nexus_gate/internal/auth/jwt.go` |
| **Circuit Breaker** | 熔断器，防止故障扩散 | `nexus/core/circuit_breaker.py` |
| **Celery** | Python 异步任务队列 | `nexus/middleware/task_queue.py` |

---

## 附录 A: 常见 Bug 排查实战 (新手必读)

> 以下是从实际运行日志中发现的 2 个典型 Bug，通过分析它们可以学到如何阅读错误栈、定位根因、编写修复代码。

### 🐛 Bug 1: `AttributeError: 'CockpitSettings' object has no attribute 'cockpits'`

#### 错误日志（截取关键部分）
```
File ".../middleware_status.py", line 302, in _get_app_config
    "cockpit_count": len(get_config().cockpit.cockpits) if hasattr(config, 'cockpit') else 3,
AttributeError: 'CockpitSettings' object has no attribute 'cockpits'
```

#### 🔍 根因分析

| 步骤 | 说明 |
|------|------|
| ① 看错误类型 | `AttributeError` = 访问了对象上不存在的属性 |
| ② 看错误位置 | `middleware_status.py` 第 302 行，`_get_app_config()` 函数 |
| ③ 看错误代码 | `get_config().cockpit.cockpits` — 访问 `cockpit` 对象的 `cockpits` 属性 |
| ④ 查类定义 | 打开 `config.py`，搜索 `class CockpitSettings`，发现只有 `default_cockpit_count`，没有 `cockpits` |
| ⑤ 确认根因 | 代码笔误：把 `default_cockpit_count` 写成了 `cockpits` |

#### ✅ 修复方案

```python
# 修复前（错误）:
"cockpit_count": len(get_config().cockpit.cockpits) if hasattr(config, 'cockpit') else 3,

# 修复后（正确）:
"cockpit_count": config.cockpit.default_cockpit_count if hasattr(config, 'cockpit') else 3,
```

#### 💡 新手知识点

- **Pydantic Settings 的属性必须和类定义一致**：`CockpitSettings` 里定义了什么字段，就只能访问什么字段
- **`hasattr` 只检查一级属性**：`hasattr(config, 'cockpit')` 只检查 `config` 有没有 `cockpit`，不检查 `cockpit` 里有没有 `cockpits`
- **热重载机制**：修改文件后 `WatchFiles` 会自动重启服务，所以你看到的错误日志可能是修改前的旧代码产生的

---

### 🐛 Bug 2: `RuntimeWarning: coroutine 'Connection.close' was never awaited`

#### 错误日志
```
main.py:315: RuntimeWarning: coroutine 'Connection.close' was never awaited
  app.state.checkpoint_saver.conn.close()
```

#### 🔍 根因分析

| 步骤 | 说明 |
|------|------|
| ① 看警告类型 | `RuntimeWarning` = 运行时警告（不是 Error，但说明代码有问题） |
| ② 看警告信息 | `coroutine ... was never awaited` = 一个协程没有被 `await` |
| ③ 看错误位置 | `main.py` 第 316 行，服务关闭时清理 `checkpoint_saver` |
| ④ 查类型链 | `checkpoint_saver` 是 `AsyncSqliteSaver` → 内部用 `aiosqlite.Connection` → `close()` 是 `async` 方法 |
| ⑤ 确认根因 | 异步方法必须用 `await` 调用，否则协程不会执行，连接不会真正关闭 |

#### ✅ 修复方案

```python
# 修复前（错误）:
if hasattr(app.state.checkpoint_saver, "conn"):
    app.state.checkpoint_saver.conn.close()  # ← 缺少 await

# 修复后（正确）:
if hasattr(app.state.checkpoint_saver, "conn"):
    await app.state.checkpoint_saver.conn.close()  # ← 加上 await
```

#### 💡 新手知识点

- **`async` / `await` 配对原则**：如果一个方法被 `async def` 定义，调用它时**必须**加 `await`
- **`aiosqlite` vs `sqlite3`**：`sqlite3` 是同步的（`conn.close()` 直接调用），`aiosqlite` 是异步的（必须 `await conn.close()`）
- **RuntimeWarning 不可忽视**：虽然不导致崩溃，但意味着资源（数据库连接）没有被正确释放，长时间运行会导致连接泄漏

---

## 附录 B: Bug 修复测试步骤

### 测试 Bug 1: 中间件状态接口

```bash
# 步骤 1: 启动后端服务
cd backend_design
make dev

# 步骤 2: 直接访问中间件状态 API
curl http://localhost:8000/middleware/

# 步骤 3: 验证返回结果中包含 cockpit_count 字段且无 500 错误
# 预期: HTTP 200, JSON 中 "app" 节点包含 "cockpit_count": 3（或 .env 中配置的值）

# 步骤 4: 通过前端验证
# 打开 http://localhost:3000/middleware → 查看"应用配置"卡片是否正常显示座舱数量
```

### 测试 Bug 2: 服务关闭无 RuntimeWarning

```bash
# 步骤 1: 启动后端服务
cd backend_design
make dev

# 步骤 2: 等待服务完全启动（看到 "NexusCockpit starting up..." 日志）

# 步骤 3: 按 Ctrl+C 停止服务

# 步骤 4: 检查控制台输出
# 预期: 看到 "NexusCockpit stopped" 且无 RuntimeWarning
# 如果仍有 "coroutine ... was never awaited" → 修复未生效，检查 main.py 第 316 行
```

### 测试回归项

```bash
# 确保以上两个修复没有影响其他功能

# 1. 对话功能正常
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你好", "cockpit_id": "cockpit-01"}'

# 2. 健康检查正常
curl http://localhost:8000/health

# 3. 中间件状态（通过 Go 网关）
curl http://localhost:8080/middleware/
```

---

### 🐛 Bug 3: `Embedding failed after retries: Event loop is closed`

#### 错误日志（截取关键部分）
```
2026-07-12T15:07:27Z [error] Embedding failed after retries: Event loop is closed
2026-07-12T15:08:19Z [error] Embedding failed after retries: Event loop is closed
HTTP Request: POST https://api.siliconflow.cn/v1/embeddings "HTTP/1.1 200 OK"
```

#### 🔍 根因分析

| 步骤 | 说明 |
|------|------|
| ① 看错误类型 | `Event loop is closed` = asyncio 事件循环已关闭，不能再使用 |
| ② 看错误位置 | `embedding.py` 第 67 行，`embed()` 方法内部调用 `httpx.AsyncClient.post()` |
| ③ 追踪调用链 | `supervisor_graph.py` → `memory_manager.store_from_text_async()` → 新线程中创建新事件循环 → `store_from_text()` → `vector_store.insert_memory()` → `embedding_service.embed()` |
| ④ 发现矛盾 | `EmbeddingService` 的 `httpx.AsyncClient` 在 FastAPI 主事件循环中创建（`main.py` lifespan），但后台线程创建了**另一个**事件循环来调用它 |
| ⑤ 确认根因 | `httpx.AsyncClient` 绑定在主事件循环上，跨事件循环使用导致 "Event loop is closed" |

#### ✅ 修复方案

```python
# 修复前（错误）— 在新线程中创建新事件循环:
def store_from_text_async(self, user_text, user_id):
    def _run():
        loop = asyncio.new_event_loop()        # ← 新事件循环
        loop.run_until_complete(self.store_from_text(...))
        loop.close()
    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

# 修复后（正确）— 在当前事件循环中调度:
def store_from_text_async(self, user_text, user_id):
    loop = asyncio.get_running_loop()           # ← 获取当前事件循环
    task = loop.create_task(self._store_from_text_safe(user_text, user_id))
    task.add_done_callback(self._task_done_callback("memory_storage"))
    return task
```

#### 💡 新手知识点

- **事件循环是唯一的**: 一个 `httpx.AsyncClient` 实例绑定在创建它的事件循环上，不能在另一个事件循环中使用
- **`asyncio.new_event_loop()` vs `asyncio.get_running_loop()`**: 前者创建新循环（通常用于线程），后者获取当前正在运行的循环
- **`asyncio.create_task()` 的优势**: 在同一个事件循环中调度后台任务，不需要创建线程，更轻量更安全
- **fire-and-forget 模式**: 创建 task 后不 await 它，让它在后台执行；通过 `add_done_callback` 确保异常不会静默丢失

---

### 🐛 Bug 4: Neo4j 警告 `missing property name is: mid`

#### 错误日志
```
Received notification from DBMS server:
  status_description="One of the property names in your query is not available
  in the database... the missing property name is: mid"
  severity=WARNING
for query: '... RETURN type(r) as relation, t.name as target, labels(t) as labels, r.mid as mid'
```

#### 🔍 根因分析

| 步骤 | 说明 |
|------|------|
| ① 看警告类型 | Neo4j `WARNING` — 查询引用了不存在的属性 |
| ② 看查询语句 | `r.mid as mid` — 直接访问关系的 `mid` 属性 |
| ③ 查数据 | 部分关系是通过非 `upsert_relation` 路径创建的旧数据，没有 `mid` 属性 |
| ④ 确认根因 | Cypher 查询直接访问可能不存在的属性，Neo4j 发出 WARNING |

#### ✅ 修复方案

```cypher
-- 修复前（会警告）:
RETURN type(r) as relation, t.name as target, labels(t) as labels, r.mid as mid

-- 修复后（安全）:
RETURN type(r) as relation, t.name as target, labels(t) as labels, coalesce(r.mid, -1) as mid
```

#### 💡 新手知识点

- **`coalesce()` 函数**: 类似 Python 的 `x or default`，返回第一个非 null 的值。`coalesce(r.mid, -1)` 表示"如果 `r.mid` 为 null，就返回 -1"
- **Neo4j 属性是可选的**: 与关系型数据库不同，Neo4j 的节点和关系不需要预定义字段，某些关系可能没有 `mid` 属性
- **WARNING 不可忽视**: 虽然不影响查询结果，但大量 WARNING 会污染日志、影响性能

---

## 附录 C: 模块学习卡片

> 以下学习卡片帮助新手快速理解本次 Bug 修复涉及的两个核心模块。

### 📦 模块学习卡片: MemoryManager (记忆管理器)

#### 🎯 是什么
这是 NexusCockpit 的"记忆中枢"，负责记住用户说过的话、喜欢什么、有什么习惯。就像人的大脑——既有短期记忆（刚才聊了什么），也有长期记忆（用户偏好）。

#### 🤔 为什么需要它
如果没有记忆系统，AI 每次对话都像失忆了一样：
- 用户说"把空调调到24度"，AI 调了
- 用户说"再调低一点"，AI 不知道"再"是指什么
- 用户说"我喜欢听爵士乐"，下次推荐音乐时 AI 忘了

MemoryManager 让 AI 能"记住"这些信息，实现个性化服务。

#### 🔧 怎么工作的

1. **召回记忆** (`recall`): 用户说话时，先去记忆库搜索相关历史
   - 三路搜索: 向量语义(意思相似) + 图谱关系(实体关联) + 关键词(精确匹配)
   - RRF 融合排序 → Rerank 精选 → 返回 Top-K

2. **存储记忆** (`store_from_text`): 对话结束后，从用户文本提取"记忆三元组"
   - LLM 提取: "我喜欢川菜" → (用户, LIKES, 川菜)
   - 冲突检测: 用户之前说"我喜欢粤菜"→ DELETE 旧记忆 / IGNORE 新记忆
   - 双向写入: Milvus 向量 + Neo4j 图谱

3. **非阻塞存储** (`store_from_text_async` / `store_conversation_async`):
   - 对话回复不等待记忆存储完成，用 `asyncio.create_task()` 在后台执行
   - v2.1.1 修复: 原来用线程+新事件循环，导致 embedding 跨循环报错；改为共享当前事件循环

#### 📁 关键文件

| 文件 | 作用 | 行数重点 |
|------|------|----------|
| `nexus/memory/manager.py` | 记忆管理器主类 | 第 38-85 行: 初始化和检索管道配置 |
| `nexus/memory/manager.py` | 非阻塞存储 | 第 297-375 行: store_from_text_async + 安全包装 + 回调 |
| `nexus/memory/manager.py` | 记忆召回 | 第 92-137 行: recall + 渐进式披露 |
| `nexus/memory/manager.py` | 记忆存储 | 第 201-268 行: store_from_text + 冲突裁决 |
| `nexus/rag/retriever.py` | GraphRAG 检索器 | 三路融合 + RRF + Rerank |

#### 🔗 和谁交互
- **上游（谁调用它）**: `SupervisorGraph._reviewer_node` → 对话结束后触发记忆存储
- **下游（它调用谁）**:
  - `MilvusVectorStore` → 向量存储/检索
  - `Neo4jGraphStore` → 图谱存储/检索
  - `EmbeddingService` → 文本向量化
  - `AsyncOpenAI` → LLM 记忆提取
  - `MySQL db_manager` → 用户习惯加载

#### 💡 生活类比
想象一个秘书：
- **recall** = 开会前翻笔记本，找和这次话题相关的记录
- **store_from_text** = 开完会后，把重要信息整理成卡片放进文件柜
- **store_from_text_async** = 让助理去整理文件柜，你不用等他整理完就可以继续工作
- **冲突检测** = 发现新信息和旧记录矛盾时，决定是更新还是忽略

#### ⚠️ 注意事项
- `store_from_text_async` 必须在 **async 上下文** 中调用（需要在 `async def` 函数内）
- 如果没有运行中的事件循环，方法会返回 `None` 并打印警告，不会崩溃
- 后台 task 的异常通过 `_task_done_callback` 自动记录，不会影响主流程

---

### 📦 模块学习卡片: Neo4jGraphStore (知识图谱存储)

#### 🎯 是什么
这是 NexusCockpit 的"关系网数据库"，用 Neo4j 图数据库存储用户和事物之间的关系。就像社交网络里的"好友关系图"——用户是节点，"喜欢"、"过敏"等是关系线。

#### 🤔 为什么需要它
向量数据库（Milvus）只能按"语义相似度"搜索，但有时候你需要按"关系"搜索：
- "用户对什么食物过敏？" → 需要遍历 `ALLERGY` 关系
- "用户喜欢什么类型的音乐？" → 需要遍历 `LIKES` 关系
- "用户的家在哪里？" → 需要遍历 `LIVES_IN` 关系

图谱存储弥补了向量搜索的不足，两者互补形成 GraphRAG。

#### 🔧 怎么工作的

1. **写入关系** (`upsert_relation`):
   ```
   (User:u1) -[:LIKES {mid: 42}]-> (Food:川菜)
   ```
   - `mid` 属性绑定 Milvus 向量 ID，实现双向查找
   - `MERGE` 语句: 如果关系已存在就更新，不存在就创建

2. **查询关系** (`search_user_graph`):
   ```cypher
   MATCH (u:User {id: "u1"})-[r]->(t)
   RETURN type(r) as relation, t.name as target, labels(t) as labels
   ```

3. **用户画像** (`get_user_profile`):
   ```cypher
   -- v2.1.1 修复: 使用 coalesce 处理可能缺失的 mid 属性
   RETURN type(r) as relation, t.name as target,
          labels(t) as labels, coalesce(r.mid, -1) as mid
   ```

#### 📁 关键文件

| 文件 | 作用 | 行数重点 |
|------|------|----------|
| `nexus/rag/graph_store.py` | Neo4j 图谱管理 | 第 20-39 行: 连接和初始化 |
| `nexus/rag/graph_store.py` | 写入关系 | 第 51-78 行: upsert_relation |
| `nexus/rag/graph_store.py` | 查询画像 | 第 149-168 行: get_user_profile (coalesce 修复) |
| `nexus/rag/graph_store.py` | 删除关系 | 第 80-93 行: delete_relation_by_mid |

#### 🔗 和谁交互
- **上游**: `MemoryManager` → 调用写入/查询/删除
- **下游**: Neo4j 数据库（通过 `GraphDatabase.driver`）

#### 💡 生活类比
想象一个侦探的调查板：
- 节点（User/Food/Location）= 照片钉在板上
- 关系（LIKES/ALLERGY/LIVES_IN）= 红线连接照片
- `upsert_relation` = 钉一张新照片 + 连一根线
- `get_user_profile` = 看某个人的所有连线
- `coalesce(r.mid, -1)` = 如果线上没标签就标个"-1"

#### ⚠️ 注意事项
- Neo4j 的属性是**可选的**——不是所有关系都有 `mid` 属性，旧数据可能缺失
- 用 `coalesce()` 函数安全处理缺失属性，避免 WARNING
- `MERGE` 语句是幂等的——重复执行不会创建重复关系

---

## 附录 D: 记忆存储数据流图

### 🔄 数据流图: 对话记忆存储 (v2.1.1)

```
用户在聊天框输入 "我喜欢听爵士乐"
  │
  ▼
[API 层] chat.py
  │   └─ POST /chat/stream → SSE 流式响应
  │
  ▼
[Agent 层] supervisor_graph.py
  │   ├─ Supervisor 节点: 意图路由 → lifestyle_expert
  │   ├─ Expert 节点: 生成回复 "好的，我记住了..."
  │   ├─ Responder 节点: LLM 流式生成最终回复
  │   └─ Reviewer 节点 (_reviewer_node):
  │       ├─ 质量检查 ✓
  │       │
  │       ├─ store_from_text_async(user_input, user_id)    ← 非阻塞!
  │       │   │
  │       │   ▼
  │       │   [asyncio.create_task]  ← v2.1.1 修复: 共享当前事件循环
  │       │   │
  │       │   ▼
  │       │   [_store_from_text_safe]  ← 安全包装: try/except
  │       │   │
  │       │   ▼
  │       │   [store_from_text]
  │       │   │   ├─ 1. LLM 提取三元组: ("用户", "LIKES", "爵士乐")
  │       │   │   ├─ 2. 冲突检测: 搜索现有记忆 → 无冲突
  │       │   │   ├─ 3. EmbeddingService.embed("用户 LIKES 爵士乐")
  │       │   │   │   └─ httpx.AsyncClient.post(ARK_API)  ← 同一事件循环! 不再报错
  │       │   │   ├─ 4. MilvusVectorStore.insert_memory()  → milvus_id=42
  │       │   │   └─ 5. Neo4jGraphStore.upsert_relation(u1, LIKES, 爵士乐, Music, 42)
  │       │   │       └─ (User:u1) -[:LIKES {mid:42}]-> (Music:爵士乐)
  │       │   │
  │       │   ▼
  │       │   [_task_done_callback]  ← 记录异常(如果有)
  │       │
  │       └─ store_conversation_async(...)  ← 同时存储完整对话
  │
  ▼
[前端] 逐块接收 SSE 事件 → 显示回复
  │   (记忆存储在后台异步进行，不阻塞用户看到回复)
  │
  ▼
✅ 用户看到回复 "好的，我记住了你喜欢爵士乐"
   后台: 记忆已存入 Milvus + Neo4j (用户无感知)
```

### 异常路径

```
[store_from_text_async]
  │
  ├─ 正常路径: asyncio.create_task → _store_from_text_safe → 成功
  │
  ├─ 无事件循环: get_running_loop() 抛 RuntimeError → 返回 None + 日志警告
  │   (不会崩溃，只是跳过记忆存储)
  │
  └─ 存储失败: embedding API 超时 / Milvus 连接断开
      → _store_from_text_safe 的 try/except 捕获
      → logger.error 记录错误
      → _task_done_callback 记录 task 异常
      → 不影响用户已收到的回复
```

### 关键数据结构

```python
# 记忆三元组 (LLM 提取结果)
{
    "relation": "LIKES",      # 关系类型
    "target": "爵士乐",        # 目标实体
    "type": "Music"            # 实体类型 (Neo4j 标签)
}

# Milvus 记忆记录
{
    "id": 42,                  # 主键 (auto_id)
    "user_id": "u1",           # 用户隔离
    "vector": [0.12, ...],     # 1024维浮点向量
    "text": "用户 LIKES 爵士乐",
    "timestamp": 1720785600
}

# Neo4j 关系
(User {id: "u1"}) -[:LIKES {mid: 42, timestamp: 1720785600}]-> (Music {name: "爵士乐"})
```

---

## 附录 E: 技术栈深度解读 (新手进阶)

> 以下内容对项目中每个核心技术进行"是什么 → 为什么选 → 在哪看 → 怎么学"四维解读，帮助新人从"知道有这个技术"进阶到"理解为什么这样选"。

### E.1 前端技术栈深度解读

#### Next.js 14 App Router

**是什么**: React 的全栈框架，v14 引入 App Router，用文件夹定义路由。

**为什么选它而非 Create React App / Vite**:
- **文件即路由**: `src/app/cockpit/page.tsx` 自动映射到 `/cockpit` 路由，无需手动配置路由表
- **内置 API 代理**: `next.config.js` 中的 `rewrites` 可将 `/api/*` 代理到 Go 网关，解决跨域
- **SSR/SSG**: 服务端渲染首屏，对 SEO 和首屏加载速度友好
- **代码分割**: 每个页面自动按需加载，不会一次性加载所有 JS

**在项目中的关键文件**:
```
frontend_design/src/app/
├── layout.tsx          ← 根布局（所有页面共享 Sidebar + Toaster）
├── page.tsx            ← 首页（redirect 到 /cockpit）
├── cockpit/page.tsx    ← 座舱页（聊天 + 车控 + 3D 模型）
├── chat/page.tsx       ← 独立聊天页
├── dashboard/page.tsx  ← 运营总览（图表 + 统计）
├── middleware/page.tsx ← 中间件看板
├── settings/page.tsx   ← 设置中心
└── dataplatform/page.tsx ← 数据中台
```

**学习要点**:
1. `layout.tsx` 是所有页面的"外壳"——Sidebar、Toaster、GpsProvider 都挂在这里
2. `"use client"` 声明客户端组件——用了 `useState`/`useEffect` 的页面必须加
3. `next.config.js` 的 `rewrites` 把 `/api/*` 转发到 `localhost:8080`（Go 网关）

**动手实验**:
```bash
# 1. 在 src/app/ 下新建 demo 文件夹
mkdir frontend_design/src/app/demo

# 2. 创建 page.tsx
cat > frontend_design/src/app/demo/page.tsx << 'EOF'
"use client"
export default function DemoPage() {
  return <div className="p-8 text-2xl">Hello NexusCockpit!</div>
}
EOF

# 3. 访问 http://localhost:3000/demo
```

---

#### Zustand 状态管理

**是什么**: 轻量级 React 状态管理库，用一个 `create()` 函数创建全局 store。

**为什么选它而非 Redux/Context**:
- **比 Redux 简单**: 不需要 action/type/reducer/dispatch，直接 `set()` 修改
- **比 Context 高效**: Zustand 使用 selector 订阅，只有用到的字段变化才 re-render
- **内置持久化**: `persist` 中间件一行代码实现 localStorage 持久化

**在项目中的两个核心 Store**:

| Store | 文件 | 管理什么 |
|-------|------|----------|
| `useChatStore` | `src/stores/chat-store.ts` | 消息列表、会话管理、流式状态、座舱切换 |
| `useAuth` | `src/stores/auth-store.ts` | JWT Token、用户 ID、角色、座舱 ID |

**关键代码解读**:
```typescript
// chat-store.ts 的持久化 + 座舱切换清空
export const useChatStore = create<ChatState>()(
  persist(                           // ← persist 中间件: 自动存到 localStorage
    (set) => ({
      messages: [],
      // ...
      newSession: () => set({ messages: [], streamingContent: "" }),
      // 座舱切换时调用，清空旧消息
    }),
    { name: "chat-storage" }         // ← localStorage 的 key
  )
)
```

**学习要点**:
1. `create<T>()(persist((set) => ({...}), {name: "..."}))` 是标准模式
2. 组件中用 `useChatStore((s) => s.messages)` 选择性订阅，避免全量 re-render
3. `persist` 会自动在页面刷新后恢复状态

---

#### SSE 流式通信 (Server-Sent Events)

**是什么**: 服务器单向推送技术，基于 HTTP 长连接。

**为什么选 SSE 而非 WebSocket**:
- AI 回复是"服务器 → 客户端"单向流，SSE 更合适
- SSE 基于 HTTP，不需要额外的协议升级
- SSE 自带断线重连机制
- 但 WebSocket 也有用——实时双向通信场景（如 WebSocket Hub）

**完整数据流**:
```
前端 ChatWindow.handleSend()
  │
  ├─ 调用 api.streamMessage(text, cockpitId)
  │   └─ fetch("/api/chat/stream", {method: POST, body: ...})
  │       └─ Go 网关代理到 Python FastAPI
  │           └─ chat_stream() 返回 StreamingResponse
  │               └─ 逐块 yield f"data: {json.dumps(chunk)}\n\n"
  │
  ├─ 前端 reader.read() 逐块读取
  │   └─ TextDecoder 解码 → 按 "\n" 分行 → 解析 "data: " 前缀
  │       └─ 每收到一个 chunk → updateMessage() 更新 UI
  │
  └─ 收到 "data: [DONE]" → 流结束 → 标记完成
```

**关键代码定位**:
- 前端发送: `src/lib/api.ts` → `streamMessage()` 函数
- 前端接收: `src/components/chat/chat-window.tsx` → `handleSend()` 函数
- 后端发送: `backend_design/nexus/api/routes/chat.py` → `chat_stream()` 函数
- 取消机制: `AbortController` — 用户点"停止"时 `controller.abort()`

---

### E.2 Go 网关技术栈深度解读

#### Go + Gin 路由分发

**是什么**: Go 语言 + Gin Web 框架，处理 HTTP 请求路由。

**为什么需要 Go 网关（不直接用 Python FastAPI）**:
- **性能**: Go 编译为机器码，并发处理能力远超 Python
- **职责分离**: Go 处理"快请求"（健康检查/限流/鉴权），Python 处理"慢请求"（AI 推理）
- **连接管理**: Go 的 goroutine 轻量级，适合管理千级 WebSocket 连接

**路由分类策略**（最重要的设计决策）:
```
请求进来
  ├── /health, /auth/token, /metrics        → Go 原生处理 (无需 AI)
  ├── /dataplatform/overview, /alerts       → Go 原生查 Redis (无需 AI)
  ├── /middleware/*                          → Go 原生 TCP 检查 (无需 AI)
  ├── /settings/cockpits (GET)              → Go 原生返回配置 (无需 AI)
  ├── /cockpit/*/chat, /vehicle, /asr, /tts → 转发 Python (需要 AI)
  └── /cockpit/*/ws/chat                    → WebSocket Hub
```

**关键文件阅读顺序**:
1. `cmd/main.go` → 理解启动流程
2. `internal/router/router.go` → 理解路由分类
3. `internal/proxy/proxy.go` → 理解反向代理转发
4. `internal/auth/jwt.go` → 理解 JWT 鉴权
5. `internal/ratelimit/ratelimit.go` → 理解限流
6. `internal/ws/hub.go` → 理解 WebSocket

---

#### Redis Lua 原子限流

**是什么**: 用 Redis + Lua 脚本实现多优先级令牌桶限流。

**为什么用 Lua 脚本**:
- 限流需要"读取计数 → 判断 → 写入"三步操作
- 如果分三条 Redis 命令执行，高并发下会有竞态条件
- Lua 脚本在 Redis 中**原子执行**，不会被其他命令打断

**三级优先级设计**:
| 优先级 | 场景 | 令牌分配 |
|--------|------|----------|
| High | 用户对话（/chat） | 60% 令牌 |
| Normal | 车控指令（/vehicle） | 30% 令牌 |
| Low | 管理操作（/admin） | 10% 令牌 |

**学习建议**: 阅读 `ratelimit.go` 中的 Lua 脚本，画出令牌添加和消费的流程图。

---

### E.3 Python AI 服务技术栈深度解读

#### LangGraph Multi-Agent 编排

**是什么**: LangChain 的图式 Agent 编排框架，用"图"来组织多个 AI Agent 的协作流程。

**核心概念**:
| 概念 | 通俗解释 | 项目对应 |
|------|----------|----------|
| **StateGraph** | 一张有向图，节点是函数，边是流转方向 | `supervisor_graph.py` 中的 `StateGraph(SupervisorState)` |
| **Node** | 图中的一个处理节点，是一个函数 | Supervisor/Experts/Responder/Reviewer |
| **Edge** | 节点之间的连线，表示执行顺序 | `add_edge("supervisor", "experts")` |
| **Conditional Edge** | 条件边，根据状态决定下一个节点 | `add_conditional_edges("supervisor", route_fn)` |
| **State** | 所有节点共享的状态对象 | `SupervisorState` TypedDict |

**项目中的 Agent 工作流**:
```
用户输入
  ↓
Supervisor (调度节点)
  ├── 意图路由: 判断需要哪些专家
  └── 条件边 → 激活对应专家
       ↓
  ┌────┬────┬────┬────┐
  │车控 │导航 │生活 │健康 │  ← 并行执行
  └─┬──┴─┬──┴─┬──┴─┬──┘
     └────┴────┴────┘
        ↓
  Responder (汇总节点)
  └── 合并多专家结果 + LLM 生成最终回复
        ↓
  Reviewer (审查节点)
  └── 质量检查 + 触发记忆存储
        ↓
  返回前端
```

**学习建议**:
1. 先理解"图"的概念——节点是函数，边是执行顺序
2. 阅读 `supervisor_graph.py` 的 `_build_graph()` 方法
3. 画出图结构，标注条件路由
4. 尝试新增一个 Expert 节点

---

#### GraphRAG 三路检索 + Rerank

**是什么**: 不是简单的一次向量搜索，而是三路并行检索 + 融合排序 + 精排。

**为什么需要三路**:
| 检索方式 | 擅长 | 不擅长 |
|----------|------|--------|
| 向量搜索 (Milvus) | 语义相似（"开心" ≈ "快乐"） | 精确关键词匹配 |
| 图谱遍历 (Neo4j) | 关系查询（用户喜欢什么） | 模糊语义 |
| 关键词 (BM25) | 精确匹配（故障码 P0301） | 语义理解 |

三路互补，覆盖不同类型的查询需求。

**RRF 融合算法**:
```
# 三个检索器各返回 Top-10 结果
# RRF 公式: score(d) = Σ 1/(k + rank_i(d))
# k=60 (常数，平衡头部和尾部结果)

文档A: 向量排名1 → 1/61=0.0164, 图谱排名3 → 1/63=0.0159, BM25未上榜 → 0
  总分 = 0.0164 + 0.0159 = 0.0323

文档B: 向量排名5 → 1/65=0.0154, 图谱未上榜 → 0, BM25排名1 → 1/61=0.0164
  总分 = 0.0154 + 0.0164 = 0.0318

→ 文档A 排在文档B 前面
```

**Rerank 二次排序**:
- RRF 融合后的 Top-K 结果送入 BGE CrossEncoder
- CrossEncoder 对 (query, document) 对做精细打分
- 比向量相似度更准确，但计算成本更高

**关键文件**: `nexus/rag/retriever.py` → `retrieve()` 方法

---

### E.4 数据存储技术栈深度解读

#### 四数据库分工

| 数据库 | 存什么 | 为什么选它 | 项目位置 |
|--------|--------|------------|----------|
| **Milvus** | 向量（文本的数字表示） | 十亿级向量毫秒搜索 | `nexus/rag/vector_store.py` |
| **Neo4j** | 关系图谱（用户→喜欢→食物） | 高效遍历关系 | `nexus/rag/graph_store.py` |
| **MySQL** | 结构化数据（用户、座舱、日志） | ACID 事务、成熟稳定 | `nexus/core/db_manager.py` |
| **Redis** | 缓存/限流/会话/指标 | 内存级速度、多数据结构 | `nexus/middleware/redis_cache.py` |

**多租户隔离策略**:
| 数据库 | 隔离方式 | 示例 |
|--------|----------|------|
| Redis | DB 编号分区 | cockpit-01 → DB 1, cockpit-02 → DB 2 |
| Milvus | Collection 前缀 | `cockpit_01_memories`, `cockpit_02_memories` |
| MySQL | 行级隔离 | `WHERE cockpit_id = 'cockpit-01'` |

---

### E.5 技术选型决策树

当你在项目中遇到"为什么用 A 而不用 B"的疑问时，参考以下决策树：

```
Q: 为什么用 Go + Python 双语言，而不是纯 Python？
A: Go 处理并发连接/限流/鉴权（性能敏感），Python 处理 AI 推理（生态丰富）

Q: 为什么用 Zustand 而不是 Redux？
A: Redux 模板代码太多（action/reducer/dispatch），Zustand 一个 create() 搞定

Q: 为什么用 SSE 而不是 WebSocket 做聊天？
A: AI 回复是单向流，SSE 更轻量。但 WebSocket 也用了——Hub 管理实时连接

Q: 为什么用 Milvus 而不是 Pinecone？
A: Milvus 可本地部署（数据安全），Pinecone 是 SaaS（数据出境风险）

Q: 为什么用 Neo4j 而不是只用 MySQL？
A: "用户喜欢什么食物"这种关系查询，图数据库遍历 O(1) vs 关系型 JOIN O(n)

Q: 为什么用 Celery 而不是 asyncio.create_task？
A: Celery 支持跨进程/跨机器分布式任务，asyncio.create_task 只在单进程内

Q: 为什么用 LangGraph 而不是直接写 if-else？
A: Agent 工作流有并行/条件/回环，图结构比 if-else 更清晰可维护
```

---

### E.6 推荐学习资源汇总

| 技术 | 官方文档 | 互动教程 | 视频推荐 |
|------|----------|----------|----------|
| Next.js | [nextjs.org/docs](https://nextjs.org/docs) | [nextjs.org/learn](https://nextjs.org/learn) | B站搜"Next.js App Router" |
| TypeScript | [typescriptlang.org](https://www.typescriptlang.org/zh/) | [typescript-exercises](https://typescript-exercises.github.io/) | B站搜"TypeScript 入门" |
| Tailwind CSS | [tailwindcss.com/docs](https://tailwindcss.com/docs) | [tailwindcss.com/docs/installation](https://tailwindcss.com/docs/installation) | 官方交互式文档 |
| Zustand | [GitHub README](https://github.com/pmndrs/zustand) | - | B站搜"Zustand" |
| Go | [go.dev/tour](https://go.dev/tour) | [go.dev/tour](https://go.dev/tour) | B站搜"Go 入门" |
| Gin | [gin-gonic.com/docs](https://gin-gonic.com/docs/) | - | - |
| FastAPI | [fastapi.tiangolo.com](https://fastapi.tiangolo.com/zh/) | 官方文档自带交互示例 | B站搜"FastAPI" |
| LangGraph | [langchain-ai.github.io/langgraph](https://langchain-ai.github.io/langgraph/) | - | - |
| Milvus | [milvus.io/docs](https://milvus.io/docs) | [milvus.io/bootcamp](https://milvus.io/bootcamp) | - |
| Neo4j | [neo4j.com/docs](https://neo4j.com/docs/) | [neo4j.com/graphacademy](https://neo4j.com/graphacademy/) | - |
| Redis | [redis.io/docs](https://redis.io/docs/) | [university.redis.com](https://university.redis.com/) | - |
| Docker | [docs.docker.com](https://docs.docker.com/) | [docker-curriculum.com](https://docker-curriculum.com/) | B站搜"Docker 入门" |
| Prometheus | [prometheus.io/docs](https://prometheus.io/docs/) | - | - |
