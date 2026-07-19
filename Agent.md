# Agent.md — NexusCockpit 项目导航

> 本文件是项目的**总入口导航**，用于 AI Agent 和开发者快速定位代码与文档。

## 项目概述

NexusCockpit 是一个企业级车载语音 Agent 系统，采用 **7 层分层架构**，集成了 Multi-Agent 协同、GraphRAG 融合检索、语义缓存、MCP 协议等前沿技术。

> NexusCockpit 采用 **座舱控制 + 运营总览** 架构，座舱控制台提供车控与语音交互，运营总览看板提供系统监控与数据分析。

## 座舱控制 + 运营总览架构概览

> **简化说明**: SubAgent 监控层和 MainAgent 确认层已移除（过度设计，未落地）。

```
┌───────────────────────────────────────────────────────┐
│  座舱控制台 ──┐                                        │
│  语音助手   ──┼── API Gateway (Go)                     │
│  运营总览   ──┘   ↓                                     │
│  Supervisor + 5 Experts                                 │
│       ↓                                                 │
│  中间件隔离层 (Redis DB / Milvus collection / 行级)    │
│       ↓                                                 │
│  运营总览看板 + 中间件看板 + 设置中心                   │
└───────────────────────────────────────────────────────┘
```

| 新增模块 | 路径 | 说明 |
|---------|------|------|
| 座舱管理器 | `backend_design/nexus/core/cockpit_manager.py` | 座舱注册/查询/状态 |
| 多租户上下文 | `backend_design/nexus/core/tenant_context.py` | 请求级 cockpit_id 隔离 |
| 个性化服务 | `backend_design/nexus/core/personalization.py` | v2.2: 声纹+偏好匹配+Prompt 注入 |
| 座舱 API | `backend_design/nexus/api/routes/cockpit.py` | `/cockpit/{id}/*` 路由 |
| 数据中台 API | `backend_design/nexus/api/routes/dataplatform.py` | 跨座舱统计 |
| 中间件看板 API | `backend_design/nexus/api/routes/middleware_status.py` | 中间件状态 |
| 设置中心 API | `backend_design/nexus/api/routes/settings.py` | 座舱/用户/中间件管理 |

## 分层架构总览

```
┌─────────────────────────────────────────────────────────────┐
│  L7  可观测层 (Observability)    →  docs/architecture/L7-observability.md
│      Langfuse / Prometheus / Grafana / 结构化日志
├─────────────────────────────────────────────────────────────┤
│  L6  API 层 (API Gateway)        →  docs/architecture/L6-api.md
│      FastAPI REST / SSE / WebSocket / JWT 认证
├─────────────────────────────────────────────────────────────┤
│  L5  中间件层 (Middleware)       →  docs/architecture/L5-middleware.md
│      Redis 语义缓存 / 限流 / asyncio 任务队列 / 熔断器
├─────────────────────────────────────────────────────────────┤
│  L4  Agent 层 (Multi-Agent)      →  docs/architecture/L4-agent.md
│      Supervisor → 5 Experts (并行) → Responder → Reflection → Reviewer
├─────────────────────────────────────────────────────────────┤
│  L3  服务层 (Services)           →  docs/architecture/L3-service.md
│      ASR / TTS / Skills / Vehicle / Intent / MCP
├─────────────────────────────────────────────────────────────┤
│  L2  数据层 (Data)               →  docs/architecture/L2-data.md
│      GraphRAG / Memory / Vector Store / Graph Store
├─────────────────────────────────────────────────────────────┤
│  L1  核心层 (Core)               →  docs/architecture/L1-core.md
│      Config / Logger / Exceptions / Circuit Breaker / Personalization
├─────────────────────────────────────────────────────────────┤
│  L0  基础设施层 (Infrastructure) →  docs/architecture/L0-infrastructure.md
│      Docker Compose / Nginx / Prometheus / Grafana
└─────────────────────────────────────────────────────────────┘
```

## 目录结构 (前后端分离)

```
NexusCockpit/
├── Agent.md                         # ← 本文件：项目总导航
├── README.md                        # 项目介绍与快速开始
├── LICENSE                          # MIT 开源协议
├── .env                             # 环境变量 (后端共享，位于根目录)
├── .env.example                     # 环境变量模板
├── docker-compose.yml               # 基础设施一键部署
├── Makefile                         # 工程化命令 (make dev/test/lint...)
├── .pre-commit-config.yaml          # 代码质量钩子
├── .editorconfig                    # 编辑器配置 (强制 UTF-8)
│
├── images/                          # 🖼️ README 展示图片
│   ├── frontend/                    #   前端界面截图 (cockpit/chat/settings/admin/vehicle)
│   ├── architecture/                #   架构设计图
│   ├── dashboard/                   #   监控看板截图 (dataplatform/middleware/grafana)
│   ├── misc/                        #   其他截图
│   └── README.md                    #   图片命名规范与截图清单
│
├── backend_design/                  # ===== 后端代码 (Python + Go) =====
│   ├── nexus/                       # 主 Python 包
│   │   ├── main.py                  #   FastAPI 应用入口
│   │   ├── config.py                #   配置中心 (自动定位 .env)
│   │   ├── core/                    #   L1 核心层 (日志/异常/熔断/个性化)
│   │   │   ├── cockpit_manager.py   #   v2.1: 座舱管理器
│   │   │   ├── tenant_context.py    #   v2.1: 多租户上下文
│   │   │   ├── db_manager.py        #   v2.1: 异步数据库管理器
│   │   │   ├── voiceprint.py        #   v2.1: 声纹识别
│   │   │   └── personalization.py   #   v2.2: 个性化服务
│   │   ├── models/                  #   数据模型 (Agent状态/API模型/座舱模型)
│   │   ├── rag/                     #   L2 数据层 (Embedding/向量/图谱)
│   │   ├── memory/                  #   L2 数据层 (记忆管理)
│   │   ├── agent/                   #   L4 Agent 层 (Multi-Agent)
│   │   │   ├── supervisor_graph.py  #   v2.0 编排核心
│   │   │   └── experts/             #   v2.0 专家 Agent
│   │   ├── skills/                  #   L3 服务层 (19个技能+编排)
│   │   ├── vehicle/                 #   L3 服务层 (车控适配)
│   │   ├── intent/                  #   L3 服务层 (意图路由)
│   │   ├── asr/                     #   L3 服务层 (语音识别)
│   │   ├── tts/                     #   L3 服务层 (语音合成)
│   │   ├── mcp/                     #   L3 服务层 (MCP 网关)
│   │   ├── middleware/              #   L5 中间件 (缓存/限流/队列)
│   │   ├── api/                     #   L6 API 层 (REST/SSE/WS)
│   │   │   └── routes/              #   路由 (chat/vehicle/cockpit/dataplatform/middleware_status/settings/asr)
│   │   └── observability/           #   L7 可观测层 (追踪/指标/座舱指标/数据保留)
│   ├── nexus_gate/                  # v2.1: Go 并发网关
│   │   ├── cmd/main.go              #   Go 网关入口
│   │   ├── internal/                #   内部包
│   │   │   ├── auth/                #   JWT 鉴权 + RBAC
│   │   │   ├── config/              #   配置加载
│   │   │   ├── handlers/            #   Go 原生处理器 (非 AI 请求)
│   │   │   ├── proxy/               #   反向代理到 Python
│   │   │   ├── ratelimit/           #   优先级令牌桶限流
│   │   │   ├── router/              #   Gin 路由分发
│   │   │   └── ws/                  #   WebSocket Hub
│   │   ├── proto/                   #   gRPC Proto 定义 (Phase 2)
│   │   └── go.mod
│   ├── tests/                       # 测试用例 (test_api + test_core + test_v21)
│   ├── scripts/                     # 初始化脚本 + v2.1 迁移 SQL + 混沌测试
│   ├── requirements.txt             # Python 依赖
│   └── pyproject.toml               # 项目配置
│
├── frontend_design/                 # ===== 前端代码 (Next.js) =====
│   ├── src/
│   │   ├── app/                     # 页面 (cockpit/chat/vehicle/settings/dashboard/middleware/admin/dataplatform)
│   │   ├── components/              # 组件 (ui/chat/vehicle/layout)
│   │   ├── lib/                     # API 客户端 + 工具函数
│   │   ├── stores/                  # Zustand 状态管理 (含 auth-store v2.1)
│   │   ├── hooks/                   # 自定义 Hooks (useAsync + useSpeechRecognition v2.1)
│   │   └── types/                   # TypeScript 类型
│   ├── package.json
│   ├── next.config.js
│   ├── tailwind.config.ts
│   └── tsconfig.json
│
├── .catpaw/skills/                  # ===== AI 开发技能 =====
│   ├── fronted-design/              # 前端设计规范
│   ├── code-doc/                    # 代码文档生成
│   ├── code-review/                 # 代码审查
│   ├── change-impact-report/        # 变更影响评估
│   ├── rapid-dev/                   # 快速开发
│   ├── beginner-code-comment/       # 小白代码注释
│   ├── doc-sync/                    # 文档同步检查
│   └── post-code-guardian/          # 代码修改后自动编排守护 (code-review→code-doc→doc-sync)
│
├── docs/                            # ===== 文档中心 =====
│   ├── architecture/                # 架构文档 (L0-L7)
│   ├── deployment/                  # 部署文档 (SETUP + VERIFICATION)
│   ├── testing/                     # 测试文档 (TESTING)
│   ├── development/                 # 开发规范
│   ├── api/                         # API 文档
│   └── PROGRESS.md                  # 项目开发进展与架构图
│
├── config/                          # ===== 基础设施配置 =====
│   ├── prometheus/                  # Prometheus 监控
│   ├── grafana/                     # Grafana 面板
│   ├── loki/                        # Loki 日志
│   └── nginx/                       # Nginx 反向代理
│
├── models/                          # 模型文件 (需下载)
├── data/                            # 数据目录
└── assets/                          # 音频资源
```

## 常用操作速查

| 操作 | 命令 |
|------|------|
| 启动基础设施 | `docker compose up -d` |
| 安装后端环境 | `make install` |
| 安装前端依赖 | `make install-frontend` |
| 启动后端 | `make dev` |
| 启动前端 | `make dev-frontend` |
| 运行测试 | `make test` |
| 代码检查 | `make lint` |
| 代码格式化 | `make format` |
| 初始化数据库 | `make init-db` |

## 文档导航

| 文档 | 说明 |
|------|------|
| [项目进展与架构图](docs/PROGRESS.md) | 开发进度、架构图、目录结构、文档索引 |
| [架构总览](docs/architecture/overview.md) | 7 层架构设计理念与数据流 |
| [环境搭建指南](docs/deployment/SETUP.md) | 虚拟环境、模型下载、中间件部署 |
| [前后端验证方案](docs/deployment/VERIFICATION.md) | 8 阶段逐步验证 |
| [测试方案](docs/testing/TESTING.md) | 单元/集成/前端/API/性能测试详细说明 |
| [L0 基础设施层](docs/architecture/L0-infrastructure.md) | Docker Compose 编排 |
| [L1 核心层](docs/architecture/L1-core.md) | 配置、日志、异常、熔断器、个性化服务 |
| [L2 数据层](docs/architecture/L2-data.md) | GraphRAG、记忆系统 |
| [L3 服务层](docs/architecture/L3-service.md) | ASR/TTS/技能/车控/意图 |
| [L4 Agent 层](docs/architecture/L4-agent.md) | Multi-Agent 工作流 |
| [L5 中间件层](docs/architecture/L5-middleware.md) | 缓存/限流/队列 |
| [L6 API 层](docs/architecture/L6-api.md) | REST/SSE/WebSocket |
| [L7 可观测层](docs/architecture/L7-observability.md) | 追踪/指标/面板 |

## 图片资源说明

README.md 中引用的所有展示图片存放在 `images/` 目录下，按用途分子目录：

| 子目录 | 用途 | 示例文件 |
|--------|------|----------|
| `images/frontend/` | 前端界面截图 | `cockpit-main.png`, `cockpit-chat.png`, `cockpit-multi.png`, `chat-page.png`, `settings.png`, `admin.png`, `vehicle.png` |
| `images/dashboard/` | 监控看板截图 | `dataplatform.png`, `middleware-monitor.png`, `grafana.png` |
| `images/architecture/` | 架构设计图 | `7-layer-arch.png`, `multi-agent-flow.png`, `graphrag-flow.png`, `v2.1-cs-arch.png` |
| `images/misc/` | 其他截图 | `docker-ps.png`, `swagger-ui.png` 等 |

> 截图命名规范和详细清单见 [images/README.md](images/README.md)

---

## 修改代码时的查找路径

| 需求 | 查找位置 |
|------|----------|
| 修改 API 接口 | `backend_design/nexus/api/routes/` |
| 修改 Agent 逻辑 | `backend_design/nexus/agent/` |
| 修改 RAG 检索 | `backend_design/nexus/rag/retriever.py` |
| 修改记忆策略 | `backend_design/nexus/memory/manager.py` |
| 新增车控技能 | `backend_design/nexus/skills/vehicle/` |
| 修改车控适配 | `backend_design/nexus/vehicle/` |
| 修改意图路由 | `backend_design/nexus/intent/` |
| 修改配置 | `backend_design/nexus/config.py` + `.env` (根目录) |
| 修改中间件 | `backend_design/nexus/middleware/` |
| 修改中间件 | `backend_design/nexus/middleware/` |
| 修改前端页面 | `frontend_design/src/app/` |
| 修改前端组件 | `frontend_design/src/components/` |
| 修改前端 API | `frontend_design/src/lib/api.ts` |
| 修改监控指标 | `backend_design/nexus/observability/` |
| 修改 ASR/TTS | `backend_design/nexus/asr/engine.py` / `tts/engine.py` |
| 修改 MCP 网关 | `backend_design/nexus/mcp/gateway.py` |
| 修改基础设施 | `docker-compose.yml` + `config/` |
| 修改 AI 技能 | `.catpaw/skills/` |
| **v2.1: 座舱管理** | `backend_design/nexus/core/cockpit_manager.py` |
| **v2.1: 多租户上下文** | `backend_design/nexus/core/tenant_context.py` |
| **v2.1: 数据中台 API** | `backend_design/nexus/api/routes/dataplatform.py` |
| **v2.1: 中间件看板 API** | `backend_design/nexus/api/routes/middleware_status.py` |
| **v2.1: 设置中心 API** | `backend_design/nexus/api/routes/settings.py` |
| **v2.1: Go 网关** | `backend_design/nexus_gate/internal/router/router.go` |
| **v2.1: Go 原生处理器** | `backend_design/nexus_gate/internal/handlers/handlers.go` |
| **v2.1: 声纹识别** | `backend_design/nexus/core/voiceprint.py` |
| **v2.1: 数据库管理** | `backend_design/nexus/core/db_manager.py` |
| **v2.1: 座舱指标** | `backend_design/nexus/observability/cockpit_metrics.py` |
| **v2.1: 数据保留** | `backend_design/nexus/observability/data_retention.py` |

## 代码修改后的质量保障流程（强制执行）

> **每次修改代码后，必须依次执行以下三个技能，确保代码质量、注释、文档三方一致。**

```
代码修改完成
     │
     ▼
┌──────────────────────────────────────────────────────┐
│  post-code-guardian (编排器)                          │
│  技能路径: .catpaw/skills/post-code-guardian/SKILL.md │
├──────────────────────────────────────────────────────┤
│                                                      │
│  Step 1: code-review   (.catpaw/skills/code-review/)  │
│          → 检测 bug / 安全漏洞 / 性能问题              │
│          → 发现 Critical/Warning → 立即修复            │
│                                                      │
│  Step 2: code-doc      (.catpaw/skills/code-doc/)     │
│          → 为新增/修改的函数补充 docstring             │
│          → 为复杂逻辑添加行内注释                      │
│                                                      │
│  Step 3: doc-sync      (.catpaw/skills/doc-sync/)     │
│          → 检查 .md 文档与代码是否一致                 │
│          → 自动更新过期文档                            │
│          → 也可运行: python .catpaw/skills/doc-sync/  │
│             check_doc_sync.py --all                   │
│                                                      │
│  Step 4: 汇总输出守护报告                              │
└──────────────────────────────────────────────────────┘
     │
     ▼
  质量闭环完成，可执行 git commit
```

### 技能说明

| 技能 | 路径 | 作用 | 触发时机 |
|------|------|------|----------|
| `post-code-guardian` | `.catpaw/skills/post-code-guardian/` | 编排器，依次调度下面三个子技能 | 代码修改完成后自动触发 |
| `code-review` | `.catpaw/skills/code-review/` | 静态分析、安全扫描、性能审查 | post-code-guardian Step 1 |
| `code-doc` | `.catpaw/skills/code-doc/` | 生成 docstring、补充行内注释 | post-code-guardian Step 2 |
| `doc-sync` | `.catpaw/skills/doc-sync/` | 检查并同步 .md 文档与代码一致性 | post-code-guardian Step 3 |

### 调度顺序的必要性

1. **code-review 必须最先**：修复 bug 可能改变代码结构，后续步骤需基于修复后的代码
2. **code-doc 在 code-review 之后**：确保注释针对的是最终版代码，避免注释与代码不一致
3. **doc-sync 最后执行**：前两步可能修改了函数签名/新增了文件，doc-sync 需要检查最终状态
