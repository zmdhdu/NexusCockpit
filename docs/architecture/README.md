# project_knowledge 目录索引

> 本目录包含 M-RAG-Voice 项目的全部知识文档和技术方案。
> 最后更新：2026-07-07

## 文件清单

| 文件 | 说明 | 目标读者 |
|------|------|----------|
| `structure.md` | 项目架构全景文档（架构图、学习路径、面试题、flowchart） | 新人小白 / 面试备战 / 架构理解 |
| `vehicle_agent_improvement_plan.md` | **深度技术方案 V2**（多 Agent + GraphRAG + 中间件 + 前端 + 监控） | 架构师 / 高级开发 / 面试展示 |
| `vehicle_agent_architecture_landing.md` | **落地实施 v3**（C++/Go/Rust/Python 作为选型池按场景取用 + 三档落地范围 + 技术栈复用矩阵 + IPC 契约 + 显存预算 + 安全闸 + Win11 本地落地 Runbook） | 实施工程师 / 全栈开发 / 落地交付 |
| `gap_analysis.md` | **查缺补漏**（对 structure.md 与 V2 方案的 21 项 gap 诊断 + 优先级落地建议） | 架构师 / 技术负责人 |

> **阅读顺序建议**：先 `structure.md` 建立全景 → `vehicle_agent_improvement_plan.md` 看深度方案 → `gap_analysis.md` 知道哪里要补 → `vehicle_agent_architecture_landing.md` 据此写代码落地。
> **冲突裁决**：当 `vehicle_agent_architecture_landing.md` 附录 A 与 V2 方案冲突时，以 Landing 文档为准。

## V2 方案核心升级

### 新增技术深度

| 维度 | V1 (Demo 导向) | V2 (深度版) |
|------|----------------|-------------|
| Agent | 单 LangGraph 图 | **多 Agent 协同** (Planner→Executor→Reviewer→Responder) |
| RAG | 朴素 RAG | **GraphRAG** (向量+图谱融合 + Reranker) |
| 缓存 | 无 | **Redis 语义缓存** (Embedding 相似度匹配) |
| 异步 | async/await | **Celery + RabbitMQ** 异步任务队列 |
| 消息 | 无 | **RabbitMQ 事件总线** (Agent 间通信) |
| 存储 | Milvus + Neo4j | + **PostgreSQL** + **MinIO** |
| 认证 | 无 | **JWT + OAuth2** |
| 网关 | FastAPI 直连 | **Nginx** 反向代理 + 限流 + TLS |
| 前端 | Gradio | **Next.js + TailwindCSS + shadcn/ui** |
| 监控 | Langfuse (可选) | **Langfuse + Prometheus + Grafana + Loki** |
| 部署 | 裸跑 | **Docker Compose** 一键编排 |

### 新增目录结构

```
agent/           # 多 Agent 模块 (Planner/Executor/Reviewer/Responder)
middleware/      # 中间件层 (Redis缓存/Celery/RabbitMQ/熔断器/限流)
core/            # 核心基础设施 (配置/安全/数据库/存储/异常)
rag/             # 升级版 RAG (GraphRAG/Reranker/语义缓存)
api/routes/      # API 模块化
web/             # Next.js 前端项目
monitoring/      # Prometheus/Grafana/Loki 配置
nginx/           # Nginx 反向代理配置
docker-compose.yml
```

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
| Redis | 缓存+消息 | Docker / redis.io/cloud |
| PostgreSQL | 结构化数据 | Docker / supabase.com |
| MinIO | 对象存储 | Docker |
| RabbitMQ | 消息队列 | Docker / cloudamqp.com |

### 可选（锦上添花）

| 服务 | 用途 |
|------|------|
| vLLM | 本地 LLM 高吞吐推理 |
| Cloudflare | CDN + DNS |
| SwanLab | 训练实验追踪 |
| 阿里云 OSS | 备用对象存储 |

## 快速启动（V2 目标）

```bash
# 一键启动全部服务
make up                    # docker-compose up -d

# 启动前端开发
cd web && npm run dev      # → http://localhost:3000

# 启动后端 API
make api                   # uvicorn api_server:app

# 启动 Celery Worker
make worker                # celery -A middleware.celery_tasks worker

# 查看监控
make monitor               # Grafana → http://localhost:3001
```

## 文档导航

### structure.md 内容概要

1. 项目设计初心 — 解决什么问题，核心设计理念
2. 整体架构图 — 三层架构 + Audio-Text-Audio 闭环
3. 技术栈全景 — 12 层技术栈分层
4. 核心模块详解 — 6 大核心模块
5. 新人快速上手路径 — 2 周学习路线图
6. 版本演进史 — V1→V4→当前
7. Flowchart 流程图集 — 4 张 Mermaid 流程图
8. 高频面试题 — 12 道面试题
9. 代码改进点 — 5 个改进方向
10. 全栈技术改造方案 — 4 阶段改造

### vehicle_agent_improvement_plan.md 内容概要 (V2 深度版)

1. **技术调研** — 车端前沿技术全景（MCP/SOA/多Agent/GraphRAG/语义缓存/vLLM）
2. **整体架构** — 7 层架构（接入层→Agent层→中间件层→数据层→模型层→可观测层）
3. **中间件设计** — Redis 语义缓存 + Celery 异步 + RabbitMQ 事件总线 + 熔断器 + 限流
4. **Agent 深化** — 多 Agent 协同 + GraphRAG + ReAct 推理 + 人机回路
5. **前端架构** — Next.js + TailwindCSS + shadcn/ui + 页面结构 + 视觉规范
6. **数据层深化** — 5 数据库分工 + PostgreSQL DDL + Redis 数据结构
7. **可观测性** — Langfuse + Prometheus + Grafana + Loki + 告警规则
8. **安全体系** — JWT 认证链 + 12 项安全措施
9. **云服务清单** — 必需/推荐/可选服务 + 完整 .env 模板
10. **实施路线图** — 7 Phase 分阶段实施 + 优先级排序

### vehicle_agent_architecture_landing.md 内容概要 (落地实施 v3)

在 V2 之上的三块增量：**①混合语言选型（非全量）②技术栈复用 ③实施级契约与本地落地**。

1. **设计目标与约束** — P0/P1/P2 目标分层 + 4 条硬约束（单卡显存/Win11/Demo 安全/不破坏旧代码）
2. **混合语言是选型而非全用（原则）** — C++/Go/Rust/Python 是选型池，按「必须有/可选增强」取舍，纪律上禁 ctypes 嵌入、禁为凑齐备而上语言
3. **语言分工矩阵与落地档位** — 每组件标档位 + Python 兜底实现；最小档/标准档★/完整档三档裁剪
4. **进程拓扑全景图（改进版）** — 七层重排、[复用] 标注、标准档实线/完整档虚线；含**复用矩阵**（Redis×7/PG/FastAPI/MinIO/监控栈/compose 换工时）
5. **进程清单与端口契约** — 17 进程/服务的端口+协议+healthcheck 表
6. **IPC 契约定义** — 4 套 gRPC proto 草案 + 共享内存音频布局 + MCP `_safety` 扩展 + CloudEvents 事件契约
7. **延迟预算** — 端到端时序 + 七环节 P95 预算表 + 超限自愈
8. **显存预算** — 8GB/12GB 分支、三层编排（常驻集/按需swap/INT4）、vLLM 衔接
9. **车控安全互锁** — L0-L3 分级 + 声明式 denyIf + Rust 安全闸
10. **数据一致性 Outbox** — 替换裸双写，对账 gauge 兜底
11. **全双工/AEC/Barge-in** — voiced Rust 补齐半双工缺陷
12. **本地落地 Runbook** — WSL2+Docker Desktop GPU 直通 + 一键 make up + 验证清单 + 显存自查
13. **目录与工程组织** — proto/ + services/ + infra/ + tests/ 跨语言布局
14. **构建依赖管理** — 四语言构建工具/依赖/镜像基址 + Python requirements 分层
15. **测试与评估体系** — 7 层测试金字塔 + 6 类离线评估指标 + 安全闸用例矩阵
16. **分阶段落地路线** — 对齐 V2 Phase1-7 并插入混合语言节点 + 最小可演示子集
17. **FMEA 摘要** — 8 类失效模式 + 检测 + 回退
- **附录 A** — 与 V2 计划的 9 处决策冲突点（以此为准）

### gap_analysis.md 内容概要 (查缺补漏)

5 类共 21 项 gap 的诊断 + 指路（每项指向 Landing 对应章节）：

- **A 架构哲学/语言层**（3 项 🔴）：纯 Python、进程边界缺、IPC 契约缺
- **B 实施级工程细节**（8 项 🔴）：显存预算、延迟分解、流式 ASR 协议、推理后端、Win11 GPU 直通、构建分层、OTel trace、评估基线
- **C 车载行业必备能力**（5 项 🟡）：安全分级、全双工、唤醒模型、SOA/DDS 落地、多音区
- **D 一致性/正确性**（2 项 🔴）：双写无事务、统一输入校验
- **E 过度设计/冗余**（3 项 🟢）：三套异步机制重叠、三套前端并存、监控栈偏重
- 末尾给出 8 步落地优先级排序

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

## 技术栈覆盖（V2 完整版）

```
前端:       Next.js 14 │ TailwindCSS │ shadcn/ui │ Zustand │ TanStack Query │ Framer Motion │ Recharts
API:        FastAPI │ Pydantic v2 │ JWT │ WebSocket │ SSE
Agent:      LangGraph (多Agent状态图) │ LangChain │ ReAct │ Human-in-the-Loop
RAG:        GraphRAG (向量+图谱融合) │ Reranker │ 语义缓存
中间件:     Redis (语义缓存) │ Celery (异步任务) │ RabbitMQ (事件总线) │ Nginx (反向代理)
数据库:     Milvus (向量) │ Neo4j (图谱) │ PostgreSQL (关系) │ Redis (KV) │ MinIO (对象)
AI模型:     SenseVoice (ASR) │ CAM++ (声纹) │ DeepSeek-V3 (LLM API) │ Qwen3-4B (本地) │ BERT (意图)
监控:       Langfuse (AI Trace) │ Prometheus (指标) │ Grafana (面板) │ Loki (日志)
部署:       Docker │ Docker Compose │ Nginx │ GitHub Actions
微调:       BERT LoRA (意图分类) │ Qwen3-4B LoRA (对话定制)
车控:       MCP协议 │ Mock/HTTP/MCP-stdio 适配器 │ 白名单/限流/审计
```
