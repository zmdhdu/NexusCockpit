# architecture 目录索引

> 本目录包含 NexusCockpit 项目的全部架构知识文档。
> 最后更新：2026-07-18

## 文件清单

| 文件 | 说明 | 目标读者 |
|------|------|----------|
| `overview.md` | 7 层架构总览 | 架构师 / 新人 |
| `L0-infrastructure.md` | Docker Compose 编排 | 运维 / 部署 |
| `L1-core.md` | 配置/日志/异常/熔断/个性化服务 | 后端开发 |
| `L2-data.md` | GraphRAG 三路检索 + Rerank + CherryKB + 记忆系统 | 后端开发 |
| `L3-service.md` | ASR/TTS/技能系统 (19 个)/车控/意图路由 | 后端开发 |
| `L4-agent.md` | Supervisor + 5 Expert Agents 工作流 | 后端开发 / 架构师 |
| `L5-middleware.md` | RediSearch KNN 缓存/限流/会话/队列 | 后端开发 |
| `L6-api.md` | REST/SSE/WebSocket + 知识库管理 + 座舱/数据中台/设置路由 | 后端开发 / 前端联调 |
| `L7-observability.md` | Langfuse + Prometheus + Grafana + Loki | 运维 / 架构师 |
| `degradation-strategy.md` | LLM 降级策略与 fallback 方案 | 架构师 / 运维 |

> **阅读顺序建议**：先 `overview.md` 建立全景 → `L0-infrastructure.md` 了解基础设施 → `L1-core.md` 到 `L7-observability.md` 逐层深入。

## 架构核心

### 7 层分层架构

| 层 | 模块 | 核心技术 |
|----|------|----------|
| L0 基础设施 | Docker Compose | Milvus / Neo4j / Redis / MySQL / Prometheus / Grafana / Loki |
| L1 核心层 | `core/` | Pydantic Settings 配置 / structlog 日志 / 分层异常 / 熔断器 / 个性化服务 |
| L2 数据层 | `rag/` + `memory/` | GraphRAG (向量+图谱+BM25 三路 RRF 融合) + Rerank + 记忆系统 |
| L3 服务层 | `skills/` + `vehicle/` + `intent/` | 19 个技能 / Mock-HTTP-MCP 三模车控 / 启发式→LLM 意图路由 |
| L4 Agent 层 | `agent/` | LangGraph Supervisor + 5 Expert Agents + Reflection + Reviewer |
| L5 中间件层 | `middleware/` | Redis 语义缓存 (KNN) / 限流 / 会话 / asyncio 异步队列 |
| L6 API 层 | `api/` | FastAPI REST + SSE + WebSocket / CockpitContextMiddleware |
| L7 可观测层 | `observability/` | Langfuse (AI Trace) + Prometheus (指标) + Grafana (面板) + Loki (日志) |

### Multi-Agent 工作流

```
Supervisor → [条件分派] → vehicle_expert  ↘
                      → nav_expert         → responder → reflection → reviewer → END
                      → lifestyle_expert  ↗
                      → health_expert     ↗
                      → chat_expert       ↗
                      → responder (澄清/无专家时直连)
```

**四层防御机制：**
1. 预校验 (_pre_check_chat_response) — LLM 调用前拦截明显问题
2. Tool→LLM 合成 (_synthesize_tool_response) — 工具结果回传 LLM 生成自然语言
3. 反思校验 (_reflection_node) — 事实性/一致性/无幻觉检查
4. 后校验 (_post_check_chat_response) — 检测编造对话历史

## 所需云服务与 API

### 必需（已有或免费）

| 服务 | 用途 | 获取地址 |
|------|------|----------|
| 火山引擎 ARK | LLM + Embedding | console.volcengine.com/ark |
| Tavily | 联网搜索 | tavily.com |
| Milvus | 向量库 | Docker / cloud.zilliz.com |
| Neo4j | 知识图谱 | Docker / neo4j.com/aura |

### 推荐（提升完整度）

| 服务 | 用途 | 获取地址 |
|------|------|----------|
| Langfuse Cloud | AI Trace | langfuse.com |
| Redis | 缓存+向量搜索 | Docker / redis.io/cloud |
| MySQL | 结构化数据 | Docker |

### 可选（锦上添花）

| 服务 | 用途 |
|------|------|
| vLLM | 本地 LLM 高吞吐推理 |
| Cloudflare | CDN + DNS |
| 高德地图 | POI 搜索 + IP 定位 |

## 快速启动

```bash
# 一键启动全部中间件
make up                    # docker-compose up -d

# 启动前端开发
cd frontend_design && npm run dev      # → http://localhost:3000

# 启动后端 API
make api                   # uvicorn nexus.main:app

# 查看监控
make monitor               # Grafana → http://localhost:3001
```

## Skills 清单（.catpaw/skills/）

| Skill | 路径 | 用途 |
|-------|------|------|
| `code-review` | `.catpaw/skills/code-review/` | 代码质量检测、安全漏洞扫描 |
| `code-doc` | `.catpaw/skills/code-doc/` | 代码注释生成、docstring |
| `beginner-code-comment` | `.catpaw/skills/beginner-code-comment/` | 面向小白的逐行代码注释 |
| `rapid-dev` | `.catpaw/skills/rapid-dev/` | 快速开发脚手架 |
| `change-impact-report` | `.catpaw/skills/change-impact-report/` | 变更影响评估报告 |
| `fronted-design` | `.catpaw/skills/fronted-design/` | 前端页面/组件设计 |
| `doc-sync` | `.catpaw/skills/doc-sync/` | 代码修改后自动检查文档一致性并同步更新 |
| `post-code-guardian` | `.catpaw/skills/post-code-guardian/` | 代码修改后自动编排守护（code-review→code-doc→doc-sync） |
| `tech-stack-guide` | `.catpaw/skills/tech-stack-guide/` | 技术栈学习导航，帮助新人系统学习项目技术栈 |

## 技术栈覆盖

```
前端:       Next.js 14 │ TailwindCSS │ shadcn/ui │ Zustand │ TanStack Query │ Framer Motion │ Recharts
API:        FastAPI │ Pydantic v2 │ JWT │ WebSocket │ SSE
Agent:      LangGraph (多Agent状态图) │ LangChain │ Reflection 反思校验
RAG:        GraphRAG (向量+图谱+BM25 三路融合) │ Reranker │ 语义缓存
中间件:     Redis (语义缓存) │ asyncio.create_task (进程内异步) │ Nginx (反向代理)
数据库:     Milvus (向量) │ Neo4j (图谱) │ MySQL (关系) │ Redis (KV)
AI模型:     SenseVoice (ASR) │ CAM++ (声纹) │ DeepSeek-V3 (LLM API) │ Qwen3-4B (本地)
监控:       Langfuse (AI Trace) │ Prometheus (指标) │ Grafana (面板) │ Loki (日志)
部署:       Docker │ Docker Compose │ Nginx │ GitHub Actions
车控:       MCP协议 │ Mock/HTTP/MCP-stdio 适配器 │ 白名单/限流/审计
```
