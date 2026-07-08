# NexusCockpit 项目开发进展与架构说明

> 最后更新 2026-07-08

---

## 一、项目开发进度

### 总体进度

| 阶段 | 状态 | 完成度 | 说明 |
|------|------|--------|------|
| 项目初始化与架构设计 | ✅ 已完成 | 100% | 七层架构设计、目录结构、文档体系 |
| 后端核心代码实现 | ✅ 已完成 | 95% | L0-L7 全部模块代码就位 |
| 前端界面实现 | ✅ 已完成 | 90% | 4 个核心页面已完成，待联调微调 |
| 基础设施 (Docker) | ✅ 已完成 | 100% | Milvus/Neo4j/Redis/RabbitMQ/MySQL/Prometheus/Grafana |
| OSS 对象存储集成 | ✅ 已完成 | 100% | 阿里云 OSS 已接入，支持上传/下载/公开读 |
| 工程化配置 | ✅ 已完成 | 100% | Makefile/pre-commit/CI/CD/.gitignore |
| 前后端分离 | ✅ 已完成 | 100% | backend_design/ 与 frontend_design/ 独立 |
| Skills 体系 | ✅ 已完成 | 100% | 8 个 skill 已迁移到 .catpaw/skills/ |
| 测试文档 | ✅ 已完成 | 100% | VERIFICATION.md + TESTING.md |
| 模型下载与部署 | ⏳ 待执行 | 0% | 需用户按 SETUP.md 下载 |
| API Key 配置 | ⏳ 待执行 | 0% | 需用户填入 ARK_API_KEY 等 |
| 前后端联调 | ⏳ 待执行 | 0% | 需启动后端后联调 |
| 性能压测 | 🔲 未开始 | 0% | 联调通过后进行 |

### 后端模块完成详情

| 模块 | 路径 | 状态 | 关键文件 |
|------|------|------|----------|
| 配置中心 | `backend_design/nexus/config.py` | ✅ | 支持 OSS、相对路径自动解析 |
| 日志系统 | `backend_design/nexus/core/logger.py` | ✅ | structlog JSON 格式 |
| 异常处理 | `backend_design/nexus/core/exceptions.py` | ✅ | 统一 NexusError |
| 熔断器 | `backend_design/nexus/core/circuit_breaker.py` | ✅ | tenacity 重试 + 熔断 |
| OSS 存储 | `backend_design/nexus/core/oss.py` | ✅ | upload/download/sign_url |
| ASR 引擎 | `backend_design/nexus/asr/engine.py` | ✅ | FunASR SenseVoice |
| TTS 引擎 | `backend_design/nexus/tts/engine.py` | ✅ | CosyVoice-300M |
| Embedding | `backend_design/nexus/rag/embedding.py` | ✅ | Qwen3-Embedding-4B |
| 向量存储 | `backend_design/nexus/rag/vector_store.py` | ✅ | Milvus HNSW |
| 图谱存储 | `backend_design/nexus/rag/graph_store.py` | ✅ | Neo4j |
| 意图路由 | `backend_design/nexus/intent/` | ✅ | 启发式 + LLM 双路 |
| 技能系统 | `backend_design/nexus/skills/` | ✅ | 9 个技能 + 编排器 |
| 车控适配 | `backend_design/nexus/vehicle/` | ✅ | Mock/HTTP/MCP 三模式 |
| Agent 层 | `backend_design/nexus/agent/` | ✅ | Planner-Executor-Responder-Reviewer |
| 记忆管理 | `backend_design/nexus/memory/` | ✅ | 短期+长期+冲突裁决 |
| 语义缓存 | `backend_design/nexus/middleware/redis_cache.py` | ✅ | Redis + Embedding 相似度 |
| JWT 认证 | `backend_design/nexus/core/auth.py` | ✅ | JWT 令牌签发/验证/依赖注入 |
| 限流器 | `backend_design/nexus/middleware/rate_limiter.py` | ✅ | Redis Lua 脚本原子化滑动窗口 |
| 任务队列 | `backend_design/nexus/middleware/task_queue.py` | ✅ | RabbitMQ/Celery |
| 会话存储 | `backend_design/nexus/middleware/session_store.py` | ✅ | Redis 持久化 + 内存回退 |
| 认证路由 | `backend_design/nexus/api/routes/auth.py` | ✅ | POST /auth/token 令牌签发 |
| API 路由 | `backend_design/nexus/api/routes/` | ✅ | chat/vehicle/admin/health |
| WebSocket | `backend_design/nexus/api/websocket.py` | ✅ | 实时流式 |
| MCP 网关 | `backend_design/nexus/mcp/` | ✅ | MCP 协议适配器 |
| 数据模型 | `backend_design/nexus/models/` | ✅ | Pydantic schemas + AgentState |
| 可观测性 | `backend_design/nexus/observability/` | ✅ | Prometheus + Langfuse |
| 测试用例 | `backend_design/tests/` | ✅ | test_api + test_core |

### 前端页面完成详情

| 页面 | 路由 | 状态 | 功能 |
|------|------|------|------|
| 仪表盘 | `/dashboard` | ✅ | 统计卡片、服务状态、缓存统计 |
| 语音助手 | `/chat` | ✅ | 流式聊天、意图标签、Markdown 渲染、可取消 |
| 车控面板 | `/vehicle` | ✅ | 空调/车窗/座椅/媒体/导航/状态 6 卡片 |
| 设置 | `/settings` | ✅ | API 密钥/模型配置/数据库状态 |

### 前端工程化改进 (v1.0)

| 改进项 | 状态 | 说明 |
|--------|------|------|
| 统一类型定义 | ✅ | `src/types/index.ts` 集中管理所有接口类型 |
| 自定义 Hooks | ✅ | `src/hooks/use-async.ts` 封装异步请求 + 卸载保护 |
| AbortController | ✅ | 流式请求支持取消，组件卸载自动 abort |
| useEffect 清理 | ✅ | Dashboard/VehiclePanel 均加 cancelled 标志位 |
| 错误提示 | ✅ | sonner toast 替代静默 catch，区分错误类型 |
| Markdown 渲染 | ✅ | react-markdown + remark-gfm 渲染助手回复 |
| 状态持久化 | ✅ | Zustand persist 中间件，刷新不丢对话 |
| 离线标记 | ✅ | VehiclePanel 后端不可达时显示"离线"提示 |
| CVA 按钮 | ✅ | class-variance-authority 类型安全变体 |
| 依赖清理 | ✅ | 移除 4 个未使用依赖 (react-query/recharts/framer-motion/date-fns) |

---

## 二、系统架构图

### 2.1 整体架构 (L0-L7 分层)

```
┌─────────────────────────────────────────────────────────────────────┐
│                       用户 / 车载终端                                │
│                   ┌────────────────────────┐                       │
│                   │  frontend_design/      │                       │
│                   │  Next.js Web UI        │                       │
│                   │  (仪表盘/聊天/车控)    │                       │
│                   └───────────┬────────────┘                       │
│                               │HTTP / WebSocket / SSE              │
├────────────────────────────────┼────────────────────────────────────┤
│ L7 可观测层                    │                                    │
│ ┌──────────┐┌──────────┐┌──────────┐                            │
│ │Langfuse  ││Prometheus││ Grafana  │                            │
│ │(追踪)    ││(指标)    ││(面板)    │                            │
│ └──────────┘└──────────┘└──────────┘                            │
├─────────────────────────────────────────────────────────────────────┤
│ L6 API 层                                                          │
│ ┌──────────┐┌──────────┐┌──────────┐┌──────────┐                 │
│ │/chat     ││/vehicle  ││/admin    ││/ws/chat  │                 │
│ │(对话)    ││(车控)    ││(管理)    ││(实时)    │                 │
│ └────┬─────┘└────┬─────┘└────┬─────┘└────┬─────┘                 │
├───────┼───────────┼───────────┼───────────┼───────────────────────┤
│ L5 中间件层          │           │           │                      │
│ ┌──────────┐┌──────────┐┌──────────┐                              │
│ │语义缓存  ││限流器    ││任务队列  │                              │
│ │(Redis)   ││(令牌桶)  ││(RabbitMQ)│                              │
│ └──────────┘└──────────┘└──────────┘                              │
├─────────────────────────────────────────────────────────────────────┤
│ L4 Agent 层 (Multi-Agent Workflow)                                  │
│ ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐        │
│ │Planner   │──▶│ Executor │──▶│Responder │──▶│ Reviewer │        │
│ │(规划)    │   │(执行)    │   │(响应)    │   │(评审)    │        │
│ └──────────┘   └────┬─────┘   └──────────┘   └──────────┘        │
│                      │                                             │
│ L3 服务层            │                                             │
│ ┌──────┐┌──────┐┌──┴──────┐┌──────┐┌──────┐┌──────┐             │
│ │ASR   ││TTS   ││Skills   ││Intent││Memory││Vehicle│             │
│ │(语音)││(合成)││(9技能)  ││(路由)││(记忆)││(车控) │             │
│ └──────┘└──────┘└─────────┘└──────┘└──────┘└──────┘             │
├─────────────────────────────────────────────────────────────────────┤
│ L2 数据层                                                           │
│ ┌──────────┐┌──────────┐┌──────────┐┌──────────┐                 │
│ │Milvus    ││Neo4j     ││MySQL     ││OSS       │                 │
│ │(向量库)  ││(知识图谱)││(用户数据)││(对象存储)│                 │
│ └──────────┘└──────────┘└──────────┘└──────────┘                 │
├─────────────────────────────────────────────────────────────────────┤
│ L1 核心层                                                           │
│ ┌──────┐┌──────┐┌──────────┐┌──────────┐┌──────┐               │
│ │Config││Logger││Exceptions││CircuitBr ││OSS   │               │
│ └──────┘└──────┘└──────────┘└──────────┘└──────┘               │
├─────────────────────────────────────────────────────────────────────┤
│ L0 基础设施 (Docker Compose)                                        │
│ Milvus + etcd + MinIO + Neo4j + Redis + RabbitMQ + MySQL           │
│ + Prometheus + Grafana + Loki                                       │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 请求处理流程

```
用户输入 "把空调调到24度"
    │
    ▼
┌─────────────┐    ┌──────────────┐    ┌───────────────┐
│ 前端 Chat   │───▶│  /chat API   │───▶│  语义缓存检查  │
│ (发送文本)  │    │ (FastAPI)    │    │ (Redis相似度) │
└─────────────┘    └──────────────┘    └───────┬───────┘
                                                 │
                                    ┌────────────┴────────────┐
                                    │ 缓存命中?                │
                                    └────────────┬────────────┘
                                     命中 ◀──────┼──────▶ 未命中
                                      │          │
                                      │          ▼
                                      │ ┌──────────────┐
                                      │ │ Agent Graph  │
                                      │ │              │
                                      │ │ 1. Planner   │
                                      │ │    (意图识别) │
                                      │ │       │      │
                                      │ │       ▼      │
                                      │ │ 2. Executor  │
                                      │ │    (技能调用) │
                                      │ │    ┌────────┐│
                                      │ │    │Climate ││
                                      │ │    │Skill   ││
                                      │ │    │调车控   ││
                                      │ │    └────────┘│
                                      │ │       │      │
                                      │ │       ▼      │
                                      │ │ 3. Responder │
                                      │ │    (生成回复) │
                                      │ │       │      │
                                      │ │       ▼      │
                                      │ │ 4. Reviewer  │
                                      │ │    (存记忆)  │
                                      │ └──────┬───────┘
                                      │        │
                                      ▼        ▼
                                    ┌─────────────────────────┐
                                    │   返回响应给前端         │
                                    │ "已将空调设置到24度"     │
                                    └─────────────────────────┘
```

### 2.3 目录结构

```
NexusCockpit/
│
├── backend_design/                 # 后端代码 (Python)
│   ├── nexus/                      # 主应用包
│   │   ├── config.py               # 配置中心 (自动定位 .env)
│   │   ├── main.py                 # FastAPI 入口
│   │   ├── api/                    # REST API + WebSocket
│   │   ├── agent/                  # Multi-Agent 工作流
│   │   ├── asr/                    # 语音识别引擎
│   │   ├── tts/                    # 语音合成引擎
│   │   ├── core/                   # 核心组件 (日志/异常/熔断/OSS)
│   │   ├── intent/                 # 意图路由
│   │   ├── mcp/                    # MCP 网关
│   │   ├── memory/                 # 记忆管理
│   │   ├── middleware/             # 中间件 (缓存/限流/队列)
│   │   ├── models/                 # 数据模型
│   │   ├── observability/          # 可观测性
│   │   ├── rag/                    # RAG 检索
│   │   ├── skills/                 # 技能系统
│   │   └── vehicle/                # 车控适配器
│   ├── tests/                      # 测试用例
│   ├── scripts/                    # 初始化脚本
│   ├── requirements.txt            # Python 依赖
│   └── pyproject.toml              # 项目配置
│
├── frontend_design/                # 前端代码 (Next.js)
│   ├── src/
│   │   ├── app/                    # 页面 (dashboard/chat/vehicle/settings)
│   │   ├── components/             # 组件 (ui/chat/vehicle/layout)
│   │   ├── lib/                    # API 客户端 + 工具函数
│   │   ├── stores/                 # Zustand 状态管理
│   │   ├── hooks/                  # 自定义 Hooks (useAsync)
│   │   └── types/                  # TypeScript 类型定义 (统一管理)
│   ├── package.json
│   ├── next.config.js
│   ├── tailwind.config.ts
│   └── tsconfig.json
│
├── .catpaw/skills/                 # AI 开发技能
│   ├── fronted-design/             # 前端设计规范
│   ├── code-doc/                   # 代码文档生成
│   ├── code-review/                # 代码审查
│   ├── change-impact-report/       # 变更影响评估
│   ├── rapid-dev/                  # 快速开发
│   └── beginner-code-comment/      # 小白代码注释
│
├── docs/                           # 文档中心
│   ├── architecture/               # L0-L7 架构文档
│   ├── deployment/                 # 部署与验证文档
│   ├── development/                # 开发规范
│   ├── api/                        # API 文档
│   └── testing/                    # 测试文档
│
├── config/                         # 基础设施配置
│   ├── prometheus/                 # Prometheus 监控配置
│   ├── grafana/                    # Grafana 面板配置
│   ├── loki/                       # Loki 日志配置
│   └── nginx/                      # Nginx 反向代理配置
│
├── models/                         # 模型文件 (需下载)
├── data/                           # 数据文件
├── assets/                         # 音频资源
│
├── .env                            # 环境变量 (后端共享)
├── .env.example                    # 环境变量模板
├── .editorconfig                   # 编辑器配置 (强制 UTF-8)
├── docker-compose.yml              # 基础设施编排
├── Makefile                        # 工程化命令
├── .pre-commit-config.yaml         # 代码质量钩子
├── .github/workflows/ci.yml        # CI/CD 流水线
├── Agent.md                        # 项目导航
└── README.md                       # 项目说明
```

---

## 三、开发文档索引

| 文档 | 路径 | 用途 |
|------|------|------|
| 项目导航 | `Agent.md` | 代码修改时的查找入口 |
| 环境搭建 | `docs/deployment/SETUP.md` | 虚拟环境、模型下载、Docker 部署 |
| 前后端验证 | `docs/deployment/VERIFICATION.md` | 8 阶段逐步验证方案 |
| 测试方案 | `docs/testing/TESTING.md` | 单元/集成/E2E 测试详细说明 |
| 架构总览 | `docs/architecture/overview.md` | 7 层架构设计理念 |
| L0 基础设施 | `docs/architecture/L0-infrastructure.md` | Docker Compose 编排 |
| L1 核心层 | `docs/architecture/L1-core.md` | 配置/日志/异常/熔断 |
| L2 数据层 | `docs/architecture/L2-data.md` | GraphRAG/记忆系统 |
| L3 服务层 | `docs/architecture/L3-service.md` | ASR/TTS/技能/车控 |
| L4 Agent 层 | `docs/architecture/L4-agent.md` | Multi-Agent 工作流 |
| L5 中间件 | `docs/architecture/L5-middleware.md` | 缓存/限流/队列 |
| L6 API 层 | `docs/architecture/L6-api.md` | REST/SSE/WebSocket |
| L7 可观测 | `docs/architecture/L7-observability.md` | 追踪/指标/面板 |
| 项目进展 | `docs/PROGRESS.md` | 本文档 |
