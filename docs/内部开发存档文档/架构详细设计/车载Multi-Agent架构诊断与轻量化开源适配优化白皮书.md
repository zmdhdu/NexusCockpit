# 车载 Multi-Agent 系统架构诊断 & 轻量化开源适配优化白皮书

> **文档编号**: NX-WP-2026-001  
> **版本**: v2.0  
> **编制日期**: 2026-08-01  
> **项目**: NexusCockpit — 车载离线 Multi-Agent 语音系统  
> **运行环境**: Windows 10/11 x64 + NVIDIA RTX4070 (CUDA) 本地仿真车机  
> **后端运行环境**:(nexus) PS D:\zhangmengdi\WorkSpace\NexusCockpit>
> **密级**: 内部开发存档

---

## 目录

- [章节1：项目现状全盘测绘](#章节1项目现状全盘测绘)
- [章节2：现有架构缺陷分级评估](#章节2现有架构缺陷分级评估)
- [章节3：架构方案选型论证](#章节3架构方案选型论证)
- [章节4：轻量化开源组件精准适配规划](#章节4轻量化开源组件精准适配规划)
- [章节5：改造后标准工程目录结构](#章节5改造后标准工程目录结构)
- [章节6：requirements 分层整改方案](#章节6requirements-分层整改方案)
- [章节7：分模块整改优先级矩阵](#章节7分模块整改优先级矩阵)
- [章节8：Windows(RTX4070)本机仿真车机部署规范](#章节8windowsrtx4070本机仿真车机部署规范)
- [章节9：改造验收硬性标准](#章节9改造验收硬性标准)

---

## 章节1：项目现状全盘测绘

### 1.1 分层标注：目录树架构分层

基于全项目目录树审查，将 NexusCockpit 划分为七大架构层级：

#### 层级 A — 硬件驱动层 (固化不动层)

| 路径 | 职责 | 行数估算 | 状态 |
|------|------|----------|------|
| `backend_design/nexus/vehicle/mock/` | 模拟车控总线（空调/车窗/座椅/导航/媒体/车况的内存状态模型，已拆分为子目录） | ~640 | **保留** |
| `backend_design/nexus/vehicle/http.py` | HTTP REST 车控总线适配器 | ~200 | **保留** |
| `backend_design/nexus/vehicle/mcp.py` | MCP stdio 车控总线适配器 (JSON-RPC over stdio) | ~300 | 待迁移到 MCP SDK |
| `backend_design/nexus/vehicle/base.py` | 车控适配器基类 + VehicleCommandResult 数据结构 | ~80 | **保留** |
| `backend_design/nexus/vehicle/factory.py` | 车控适配器工厂 (mock/http/mcp 多模式切换) | ~147 | **保留** |

> 此层代码完全保留，零修改。音频采集、降噪算法、ASR/TTS 模型推理、CAN 总线报文收发/解析全部在此层。

#### 层级 B — 语音处理层 (固化不动层)

| 路径 | 职责 | 行数估算 | 状态 |
|------|------|----------|------|
| `backend_design/nexus/asr/engine.py` | ASR 引擎 (FunASR SenseVoice 离线语音识别) | ~200 | **保留** |
| `backend_design/nexus/tts/engine.py` | TTS 引擎 (CosyVoice 离线语音合成) | ~200 | **保留** |
| `backend_design/nexus/core/voiceprint.py` | 声纹识别 (CAM++ 说话人验证) | ~250 | **保留** |
| `backend_design/nexus/core/device.py` | 设备管理（音频设备枚举与选择） | ~100 | **保留** |
| `backend_design/nexus/core/llama_cpp_manager.py` | llama.cpp 子进程管理（本地 LLM 推理守护） | ~240 | **保留** |
| `backend_design/nexus/core/ssl_fix.py` | SSL 证书修复（本地 HTTPS 兼容） | ~50 | **保留** |

> 此层代码完全保留，零修改。

#### 层级 C — Agent 核心调度层 (重构重点)

| 路径 | 职责 | 行数估算 | 状态 |
|------|------|----------|------|
| `nexus/agent/supervisor_graph.py` | **Supervisor 多智能体工作流编排核心** — Supervisor 调度 + 5 专家并行 + Responder + Reflection + Reviewer | **~1725** | ⚠️ **重度臃肿，待拆解** |
| `nexus/agent/graph_builder.py` | 图构建辅助函数（已定义但未被生产代码调用） | ~100 | 待激活 |
| `nexus/agent/responder.py` | Responder Agent（仅持有 compressor，逻辑已内联到 supervisor_graph） | ~39 | 空壳，待迁移 |
| `nexus/agent/reviewer.py` | Reviewer Agent（质量检查 + 记忆存储） | ~78 | **保留** |
| `nexus/agent/llm_client_factory.py` | LLM 客户端工厂 (ChatOpenAI + AsyncOpenAI 双客户端) | ~181 | 待统一 |
| `nexus/agent/experts/base.py` | 专家 Agent 基类 | ~140 | **保留** |
| `nexus/agent/experts/vehicle_expert.py` | 车控专家 Agent（空调/车窗/座椅/媒体/状态分发 + 结果验证 + 沙箱安全） | ~210 | **保留** |
| `nexus/agent/experts/nav_expert.py` | 导航专家 Agent | ~73 | **保留** |
| `nexus/agent/experts/lifestyle_expert.py` | 生活推荐专家 Agent (POI 搜索/联网搜索/点餐) | ~78 | **保留** |
| `nexus/agent/experts/health_expert.py` | 车辆健康专家 Agent (骨架实现) | ~53 | **保留** |
| `nexus/agent/experts/chat_expert.py` | 闲聊专家 Agent (声纹注册 + 纯 LLM 闲聊) | ~56 | **保留** |
| `nexus/agent/nodes/reviewer_node.py` | Reviewer Node（已修复循环依赖，支持依赖注入） | ~61 | 待激活 |

> **核心臃肿点 & 拆解流程**: `supervisor_graph.py` 单文件 1725 行，包含图构建、Supervisor 节点逻辑、专家并行分派、Responder 生成、Tool→LLM 合成、Reflection 反思校验（工具类/搜索类/闲聊类三种分支）、确定性日期检查、幻觉兜底检查、Reviewer 后处理、invoke 同步调用、stream 流式输出等全部逻辑。这是整个项目最大的技术债。
>
> **拆解顺序与验证规范**（每次拆解一个节点，拆完即验证）：
> 1. 先拆 `_build_graph()` → `graph_builder.py` → 验证图构建正常
> 2. 再拆 `_supervisor_node()` → `nodes/supervisor_node.py` → 验证意图路由 + 专家分派正常
> 3. 再拆 `_dispatch_node()` → `nodes/dispatch_node.py` → 验证专家并行执行 + 结果合并正常
> 4. 再拆 `_responder_node()` + `_synthesize_tool_response()` + `_generate_llm_response()` → `nodes/responder_node.py` → 验证回复生成正常
> 5. 最后拆 `_reflection_node()` + 三种反思分支 + 日期校验 + 幻觉检查 → `nodes/reflection_node.py` → 验证反思校验正常
> 6. `supervisor_graph.py` 瘦身为编排入口 → 全量回归测试
>
> **每次拆解后的验证步骤**: 启动后端 → 发送车控/导航/闲聊/搜索/知识库 5 类测试消息 → 确认全部正常响应 → 延迟无退化 → 方可进入下一步拆解。

#### 层级 D — 知识库 RAG 层

| 路径 | 职责 | 行数估算 | 状态 |
|------|------|----------|------|
| `nexus/rag/vector_store.py` | Milvus 向量存储 (Food_List + User_Memory 双 Collection) | ~240 | **保留** |
| `nexus/rag/vector_base.py` | 向量存储基类 | ~30 | **保留** |
| `nexus/rag/vector_factory.py` | 向量存储工厂（固定本地 Milvus） | ~34 | **保留** |
| `nexus/rag/graph_store.py` | Neo4j 图谱存储 | ~250 | **保留** |
| `nexus/rag/graph_base.py` | 图谱存储基类 | ~30 | **保留** |
| `nexus/rag/graph_factory.py` | 图谱存储工厂 | ~30 | **保留** |
| `nexus/rag/embedding.py` | Embedding 服务 (云端 API) | ~150 | **保留** |
| `nexus/rag/local_embedding.py` | 本地 Embedding 服务 (sentence-transformers bge-m3) | ~100 | **保留** |
| `nexus/rag/embedding_factory.py` | Embedding 工厂 (local/cloud 切换) | ~42 | **保留** |
| `nexus/rag/reranker.py` | 本地 Reranker (BGE CrossEncoder bge-reranker-v2-m3) | ~100 | **保留** |
| `nexus/rag/reranker_base.py` | Reranker 基类 | ~30 | **保留** |
| `nexus/rag/reranker_factory.py` | Reranker 工厂 (local/none 切换) | ~59 | **保留** |
| `nexus/rag/retriever.py` | GraphRAG 三路融合检索器 (向量+图谱+BM25 + RRF + Rerank) | ~183 | **保留** |
| `nexus/rag/cherry_kb.py` | Cherry 文档知识库 (车手册/故障码/FAQ 入库+检索) | ~395 | **保留** |
| `nexus/rag/framework_adapters.py` | 框架适配层 (langchain_openai OpenAIEmbeddings 单例) | ~67 | **保留** |

> **评估**: RAG 层共 15 个文件，已经使用了 `langchain-community.BM25Retriever` 替代手写 BM25、`langchain_text_splitters.RecursiveCharacterTextSplitter` 替代手写分块、`langchain_openai.OpenAIEmbeddings` 替代手写 Embedding。RAG 层框架适配已完成，维护状态良好。

#### 层级 E — 配置管理层

| 路径 | 职责 | 状态 |
|------|------|------|
| `nexus/config/` | 配置中心 (已拆分为子目录: `__init__.py`/`llm.py`/`database.py`/`cache.py`/`vehicle.py`/`asr.py`/`observability.py`/`server.py`/`providers.py`/`data.py`/`cockpit.py`/`_common.py`) | **保留** |
| `.env.local` | 本地开发配置 (API Key/中间件地址/模型路径/座舱配置/记忆管理参数) | **保留** |
| `docker-compose.yml` | 基础设施编排 (Milvus/Neo4j/Redis/MySQL/Langfuse/Loki/Prometheus/Grafana) | **保留** |
| `docker-compose.dev.yml` | 开发调试覆盖配置 (端口暴露/调试挂载) | **保留** |
| `config/grafana/` | Grafana Dashboard + Datasource 自动配置 | **保留** |
| `config/loki/loki-config.yml` | Loki 日志聚合配置 | **保留** |
| `config/prometheus/prometheus.yml` | Prometheus 指标采集配置 | **保留** |
| `backend_design/pyproject.toml` | Python 项目配置 (ruff/mypy 规则) | **保留** |

#### 层级 F — 部署脚本层

| 路径 | 职责 | 状态 |
|------|------|------|
| `Makefile` | 一键构建/启动/测试/格式化/清理命令 | **保留** |
| `scripts/start-backend.ps1` | 后端启动脚本 (PowerShell + 日志捕获) | **保留** |
| `scripts/start-frontend.ps1` | 前端启动脚本 | **保留** |
| `scripts/start-gateway.ps1` | Go 网关启动脚本 | **保留** |
| `backend_design/scripts/init_milvus.py` | Milvus 数据库初始化 (Collection 创建 + 食物数据导入) | **保留** |
| `backend_design/scripts/init_neo4j.py` | Neo4j 图谱初始化 (索引 + 约束) | **保留** |
| `backend_design/scripts/v2.1_migration.sql` | MySQL 迁移脚本 (多会话表/习惯表/审计日志表) | **保留** |
| `backend_design/scripts/debug/` | 调试脚本目录 | **保留** |
| `backend_design/Dockerfile` | 后端 Docker 镜像构建 | **保留** |
| `backend_design/nexus_gate/Dockerfile` | Go 网关 Docker 镜像构建 | **保留** |
| `frontend_design/Dockerfile` | 前端 Docker 镜像构建 | **保留** |

> 部署脚本层结构清晰，职责明确。PowerShell 启动脚本适配 Windows 环境，Makefile 提供统一入口。当前状态良好。

#### 层级 G — 附属文档层

| 路径 | 职责 | 状态 |
|------|------|------|
| `docs/交付版文档包/` (10 篇) | 部署安装/运维排查/API协议/参数配置/安全合规/硬件适配/CAN协议/架构总览/性能基准/LLM降级 | **保留** |
| `docs/内部开发存档文档/` | 架构详细设计/审核选型分析/开发过程记录/测试验证方案/语音技术文档/简历与个人材料 | **保留** |
| `README.md` | 项目总览 | **保留** |
| `Agent.md` | Agent 架构说明 | **保留** |

### 1.2 逐条解析 requirements.txt 所有依赖包

> 以下仅列出 requirements.txt 中当前保留的依赖包。已移除的 6 个冗余包 (langgraph-prebuilt / langchain-milvus / langchain-neo4j / sqlalchemy / duckduckgo-search / scikit-learn) 不再列出。

#### 1.2.1 系统基础依赖 (Web 框架 + 服务器)

| 包名 | 版本 | 用途 |
|------|------|------|
| `fastapi` | 0.128.0 | Web 框架 (API 路由 + WebSocket + 静态文件) |
| `uvicorn[standard]` | 0.40.0 | ASGI 服务器 (uvloop + httptools 加速) |
| `python-multipart` | 0.0.21 | FastAPI 文件上传支持 |
| `websockets` | 12.0 | WebSocket 协议库 (语音流式传输) |
| `starlette` | 0.50.0 | ASGI 框架底层 (FastAPI 依赖) |

#### 1.2.2 LLM / Agent 依赖 (LangChain + LangGraph 全栈)

| 包名 | 版本约束 | 用途 |
|------|----------|------|
| `langchain-openai` | >=1.1.0 | ChatOpenAI + OpenAIEmbeddings |
| `langchain-core` | >=1.2.0 | trim_messages, SystemMessage, StructuredTool, BaseMessage |
| `langchain-text-splitters` | >=1.0.0 | RecursiveCharacterTextSplitter (文档分块) |
| `langgraph` | >=1.0.6 | StateGraph 工作流编排 |
| `langgraph-checkpoint-sqlite` | >=2.0.0 | SQLite checkpoint 持久化 (AsyncSqliteSaver) |

> `call_llm_with_fallback()` 已迁移为 `ChatOpenAI.ainvoke()` 统一入口。`get_llm_client()` (AsyncOpenAI) 已标记弃用。`supervisor_graph.py` 中的 7 处 `self.llm_client.chat.completions.create()` 直接调用将在拆分阶段统一迁移为 `call_llm_with_fallback()` 调用。

#### 1.2.3 RAG / 向量存储 / 图谱

| 包名 | 版本约束 | 用途 |
|------|----------|------|
| `langchain-community` | >=0.4.0 | BM25Retriever (社区集成包) |
| `pymilvus` | >=3.0.0 | Milvus Python SDK (领域特定查询) |
| `neo4j` | >=5.18.0 | Neo4j Python Driver (领域特定 Cypher) |
| `sentence-transformers` | >=2.7.0 | 本地 Embedding (bge-m3) + Reranker (bge-reranker) |

#### 1.2.4 中间件依赖

| 包名 | 版本 | 用途 |
|------|------|------|
| `redis` | 5.0.0 | Redis 客户端 (语义缓存 + 限流器 + 会话存储 + 指标存储) |
| `aiomysql` | >=0.2.0 | MySQL 异步驱动 (用户管理 + 审计日志 + 对话历史 + 习惯记录) |

#### 1.2.5 MCP (Model Context Protocol)

| 包名 | 版本约束 | 用途 |
|------|----------|------|
| `mcp` | >=2.0.0 | MCP SDK (车控服务标准协议，待落地替换自研 stdio JSON-RPC) |

#### 1.2.6 配置 / 验证

| 包名 | 版本 | 用途 |
|------|------|------|
| `pydantic` | 2.12.5 | 数据验证 + 类型安全配置 |
| `pydantic-core` | 2.41.5 | Pydantic Rust 核心 |
| `pydantic-settings` | >=2.1.0 | BaseSettings 配置管理 |
| `python-dotenv` | 1.2.1 | .env 文件加载 |

#### 1.2.7 可观测性

| 包名 | 版本 | 用途 |
|------|------|------|
| `langfuse` | 4.5.0 | LLM 追踪平台 (Agent 调用链路记录) |
| `prometheus-client` | 0.23.1 | Prometheus 指标采集 |
| `structlog` | >=24.1.0 | 结构化日志 (JSON 格式日志输出) |

#### 1.2.8 认证

| 包名 | 版本 | 用途 |
|------|------|------|
| `PyJWT` | >=2.10.0 | JWT Token 签发与验证 |
| `passlib[bcrypt]` | >=1.7.4 | 密码哈希 (bcrypt) |

#### 1.2.9 音频 / ASR / TTS (固化层依赖)

| 包名 | 版本 | 用途 |
|------|------|------|
| `funasr` | 1.1.12 | FunASR 语音识别引擎 (SenseVoice 模型) |
| `modelscope` | 1.15.0 | ModelScope 模型下载 |
| `torchaudio` | >=2.2.0 | 音频处理 (PyTorch 音频扩展) |
| `librosa` | 0.11.0 | 音频分析 (MFCC/频谱特征提取) |
| `soundfile` | 0.13.1 | 音频文件读写 (WAV/FLAC) |
| `pydub` | 0.25.1 | 音频格式转换 (mp3→wav 等) |

#### 1.2.10 HTTP / 网络

| 包名 | 版本 | 用途 |
|------|------|------|
| `httpx` | 0.28.1 | 异步 HTTP 客户端 |
| `requests` | 2.32.5 | 同步 HTTP 客户端 |
| `aiohttp` | 3.13.3 | 异步 HTTP 客户端 |

#### 1.2.11 工具库

| 包名 | 版本 | 用途 |
|------|------|------|
| `orjson` | 3.11.5 | 高性能 JSON 序列化 |
| `tiktoken` | 0.12.0 | Token 计数 (langchain-core trim_messages 依赖) |
| `PyYAML` | 6.0.3 | YAML 配置文件解析 |

#### 1.2.12 搜索

| 包名 | 版本 | 用途 |
|------|------|------|
| `tavily` | 1.1.0 | Tavily AI 搜索引擎 (联网搜索技能) |

#### 1.2.13 数据处理

| 包名 | 版本 | 用途 |
|------|------|------|
| `numpy` | 1.26.4 | 数值计算 (向量运算/音频处理) |
| `pandas` | 2.3.3 | 数据处理 (食物知识库导入/数据分析) |

#### 1.2.14 NLP

| 包名 | 版本 | 用途 |
|------|------|------|
| `sentencepiece` | 0.2.1 | Token 分词 (transformers 依赖) |
| `transformers` | 4.45.2 | HuggingFace 模型加载 (BGE Embedding/Reranker) |
| `tokenizers` | 0.20.3 | 快速 Token 化 (transformers 依赖) |

#### 1.2.15 开发工具 (仅 dev 使用)

| 包名 | 版本 | 用途 |
|------|------|------|
| `pytest` | 9.0.2 | 测试框架 |
| `pytest-asyncio` | >=0.23.0 | 异步测试支持 |
| `pytest-cov` | >=4.1.0 | 测试覆盖率 |
| `ruff` | >=0.3.0 | 代码格式化 + Lint |
| `mypy` | >=1.8.0 | 类型检查 |

### 1.3 自研模块现存痛点（仅未解决项）

| # | 自研模块 | 核心文件 | 现存痛点 | 维护成本 | BUG 隐患 |
|---|---------|---------|---------|---------|---------|
| 1 | **多智能体调度** | `agent/supervisor_graph.py` (~1725行) | **上帝类**: 图构建+Supervisor逻辑+专家并行分派+Responder生成+Tool合成+三种Reflection分支+确定性日期检查+幻觉兜底+Reviewer后处理+invoke+stream 全部在一个文件 | **极高** | 任何修改都可能影响其他分支；流式输出逻辑与同步调用逻辑耦合 |
| 2 | **LLM 调用双客户端** | `agent/llm_client_factory.py` + `agent/supervisor_graph.py` | `AsyncOpenAI` 与 `ChatOpenAI` 双客户端并存，`supervisor_graph.py` 中 7 处仍使用 `self.llm_client.chat.completions.create()` 而非 `chat_model.ainvoke()` | 中 | 双客户端维护成本高，调用方式不统一 |
| 3 | **`graph_builder.py` 冗余** | `agent/graph_builder.py` | 定义了 `build_supervisor_graph()` 函数但未被生产代码调用 (`supervisor_graph.py` 内部自行构建图)，属于"抽取了一半"的半成品重构 | 中 | 与 supervisor_graph.py 拆分同步解决 |
| 4 | **`responder.py` 空壳文件** | `agent/responder.py` | 仅持有 `compressor` 属性，实际 Responder 逻辑已内联到 `supervisor_graph.py`。文件存在意义存疑 | 低 | 与 supervisor_graph.py 拆分同步解决 |
| 5 | **MCP SDK 未使用** | `vehicle/mcp.py` + `requirements.txt` | `mcp>=2.0.0` 已声明，但实际 MCP 车控适配器使用自研 stdio JSON-RPC 传输层，未使用 MCP SDK | 中 | 自研协议缺乏标准化，难以与第三方 MCP 服务互通 |
| 6 | **`default.yaml` 技能配置脱节** | `skills/default.yaml` | 定义了一套技能元数据，但实际技能实现使用 `@register_skill` 装饰器在 Python 类中定义，YAML 配置仅作为参考文档未参与运行时 | 中 | 维护时可能只改 Python 不改 YAML，导致配置脱节 |
| 7 | **Windows 后台常驻部署缺失** | `scripts/` | 当前使用 PowerShell 脚本手动启动，无 Windows Service / Task Scheduler 自启方案 | 低 | 服务意外退出后无法自动恢复 |

---

## 章节2：现有架构缺陷分级评估

### 2.1 高风险 (High Risk — 必须整改)

| # | 缺陷描述 | 影响范围 | 风险等级 |
|---|---------|---------|---------|
| H1 | **`supervisor_graph.py` 上帝类 (1725 行)** — 图构建、Supervisor 路由、专家分派、Responder 生成、Tool 合成、三种 Reflection 分支、日期校验、幻觉检查、Reviewer、invoke、stream 全部耦合在单个文件单个类中 | Agent 核心调度层 | 🔴 高 |

### 2.2 中风险 (Medium Risk — 应当优化)

| # | 缺陷描述 | 影响范围 | 风险等级 |
|---|---------|---------|---------|
| M2 | **`mcp` SDK 声明但未使用** — requirements.txt 声明了 `mcp>=2.0.0`，但实际 MCP 车控适配器 (`vehicle/mcp.py`) 使用自研 stdio JSON-RPC 传输层，未使用 MCP SDK | 车控层 | 🟡 中 |
| M3 | **`graph_builder.py` 冗余** — 定义了 `build_supervisor_graph()` 函数但未被生产代码调用 (`supervisor_graph.py` 内部自行构建图)，属于"抽取了一半"的半成品重构 | Agent 层 | 🟡 中 |
| M5 | **`AsyncOpenAI` 与 `ChatOpenAI` 双客户端并存** — `llm_client_factory.py` 同时维护 `AsyncOpenAI` (供反思校验、Tool 合成等直接调用) 和 `ChatOpenAI` (推荐方式)，`supervisor_graph.py` 中 7 处仍使用 `self.llm_client.chat.completions.create()` 而非 `chat_model.ainvoke()` | LLM 调用层 | 🟡 中 |
| M7 | **`default.yaml` 技能配置与 Python 实现脱节** — `skills/default.yaml` 定义了一套技能元数据 (vehicle_control/navigation/seat_control/music_control 等)，但实际技能实现使用 `@register_skill` 装饰器在 Python 类中定义，YAML 配置仅作为参考文档未参与运行时 | 技能层 | 🟡 中 |

### 2.3 低风险 (Low Risk — 可选迭代)

| # | 缺陷描述 | 影响范围 | 风险等级 |
|---|---------|---------|---------|
| L2 | **`responder.py` 空壳文件** — 仅持有 `compressor` 属性，实际 Responder 逻辑已内联到 `supervisor_graph.py`。文件存在意义存疑 | Agent 层 | 🟢 低 |
| L4 | **Windows 后台常驻部署方案缺失** — 当前使用 PowerShell 脚本手动启动，无 Windows Service / Task Scheduler 自启方案 | 部署层 | 🟢 低 |

---

## 章节3：架构方案选型论证

### 3.1 确认架构方案

> **确认方案: 方案 B — 一级分层架构 (1 个 Main-Agent + 多个职能 Sub-Agent)**

NexusCockpit 已采用此架构：Supervisor + 5 Expert (vehicle/navigation/lifestyle/health/chat) + Responder + Reflection + Reviewer。当前架构无需推翻重写，仅需优化拆解。

**架构特点**:
- 1 个 Supervisor Agent 负责意图路由和专家分派
- N 个 Sub-Agent 按职能分组管理各自领域的技能
- Sub-Agent 之间通过 `asyncio.gather` 并行执行
- 结果汇聚到 Responder 统一生成回复
- Reflection 反思校验 + Reviewer 质量审查后处理

**适配理由**:
1. 车载场景 5 个明确职能领域（车控/导航/生活/健康/闲聊），技能总数 10-15 个
2. RTX4070 单卡 8GB 显存，同一进程内并行无需多进程/多容器
3. 已有 LangGraph StateGraph 构建工作流图，图结构已就位
4. 已有"导航+开空调+播音乐"等多技能并行需求

### 3.2 臃肿文件拆解方案

#### 拆解目标: `supervisor_graph.py` (~1725 行 → 拆为 6 个文件)

**拆分原则**:
1. **单一职责**: 每个文件只承载一个节点或一组紧密相关的节点逻辑
2. **状态传递**: 节点间通过 `SupervisorState` (TypedDict) 传递，无直接引用
3. **图编排与节点逻辑分离**: 图结构定义与节点业务逻辑分开
4. **可测试性**: 每个节点可独立单元测试

| 拆解后文件 | 职责 | 原代码来源 (行号) |
|-----------|------|------------------|
| `agent/nodes/context.py` | **NodeContext**: 共享依赖容器 (dataclass)，持有 intent_router / memory_manager / skill_registry / llm_client / chat_model / experts / responder / reviewer / prompt_manager / checkpoint_saver | `__init__()` 中初始化的全部 self.* 属性 |
| `agent/graph_builder.py` | 图构建逻辑: 节点注册 + 边连接 + 编译 | `_build_graph()` (L133-178) |
| `agent/nodes/supervisor_node.py` | Supervisor 节点: 记忆召回 + 意图路由 + 专家分派决策 | `_supervisor_node()` (L189-384) + `_route_from_supervisor()` (L180-186) + `_determine_experts()` (L386-421) |
| `agent/nodes/dispatch_node.py` | 专家并行分派节点: asyncio.gather 并行调用 + 结果合并 | `_dispatch_node()` (L424-500) |
| `agent/nodes/responder_node.py` | Responder 节点: 汇总专家输出 + LLM 生成 + Tool 合成 + System Prompt 构建 | `_responder_node()` (L503-568) + `_synthesize_tool_response()` (L570-688) + `_generate_llm_response()` (L1483-1550) + `_stream_llm_response()` (L1552-1600) + `_get_system_prompt()` (L1201-1328) + `_format_key_context()` (L1330-1353) + `_get_location_status()` (L1355-1403) |
| `agent/nodes/reflection_node.py` | Reflection 节点: 三种反思分支 + 日期校验 + 幻觉检查 + 闲聊前后检查 | `_reflection_node()` (L690-825) + `_deterministic_date_check()` (L827-894) + `_reflect_search_response()` (L896-1000) + `_reflect_chat_response()` (L1002-1135) + `_regenerate_with_feedback()` (L1137-1199) + `_is_history_query()` (L1405-1407) + `_has_history()` (L1409-1423) + `_is_hallucinated_history()` (L1425-1427) + `_pre_check_chat_response()` (L1429-1452) + `_post_check_chat_response()` (L1454-1481) |
| `agent/supervisor_graph.py` (瘦身) | 编排入口: 初始化 NodeContext + 创建节点 + 持有图 + invoke/stream | `__init__()` (L91-131) + `invoke()` (L1703-1728) + `stream()` (L1730-1838) + `stream_with_events()` (L1840-1845) |

**拆解后效果**:
- `supervisor_graph.py` 从 ~1725 行瘦身到 ~200 行（仅保留初始化和入口调用）
- 每个节点文件 200-400 行，职责单一
- `graph_builder.py` 从废弃状态复活，真正承担图构建职责

#### 分步拆解执行计划（按顺序执行，每步完成后验证）

> **执行原则**: 每步拆完一个节点，立即启动后端发送 5 类测试消息（车控/导航/闲聊/搜索/知识库）验证，全部正常响应且延迟无退化后方可进入下一步。

---

**Step 1: 创建 `nodes/context.py` — NodeContext 共享依赖容器**

| 项 | 内容 |
|----|------|
| 文件 | `agent/nodes/context.py` (新建) |
| 内容 | `@dataclass class NodeContext`，持有全部共享依赖 |
| 依赖字段 | `intent_router: IntentRouterService`<br>`memory_manager: MemoryManager`<br>`skill_registry: SkillRegistry`<br>`llm_client: Any` (AsyncOpenAI，待 P1-1 统一移除)<br>`chat_model: Any` (ChatOpenAI，来自 `call_llm_with_fallback`)<br>`experts: dict[str, BaseExpertAgent]`<br>`responder: ResponderAgent` (持有 compressor)<br>`reviewer: ReviewerAgent`<br>`prompt_manager: PromptManager`<br>`checkpoint_saver: Any`<br>`_background_tasks: set` |
| 验证 | `python -c "from nexus.agent.nodes.context import NodeContext; print('OK')"` |

---

**Step 2: 创建 `nodes/supervisor_node.py` — Supervisor 节点**

| 项 | 内容 |
|----|------|
| 文件 | `agent/nodes/supervisor_node.py` (新建) |
| 抽取方法 | `_supervisor_node()` (L189-384, ~195行) + `_route_from_supervisor()` (L180-186, ~7行) + `_determine_experts()` (L386-421, ~36行) |
| NodeContext 依赖 | `ctx.intent_router` (route + heuristic.route + _build_default_intent)<br>`ctx.memory_manager` (recall + get_user_profile)<br>`ctx.responder.compressor` (extract_key_context + compress_history_with_threshold + augment_recall_query) |
| 改造要点 | 1. `self.xxx` → `ctx.xxx`<br>2. `@observe(name="supervisor-node")` 装饰器保留<br>3. `_route_from_supervisor` 和 `_determine_experts` 作为类的 staticmethod 或实例方法<br>4. `SupervisorGraph._build_graph()` 中 `self._supervisor_node` 改为 `self.supervisor_node.run` |
| 验证 | 启动后端 → 发送"打开空调" → 验证意图路由命中 heuristic 快速路径 → 验证专家分派正常 |

---

**Step 3: 创建 `nodes/dispatch_node.py` — 专家并行分派节点**

| 项 | 内容 |
|----|------|
| 文件 | `agent/nodes/dispatch_node.py` (新建) |
| 抽取方法 | `_dispatch_node()` (L424-500, ~77行) |
| NodeContext 依赖 | `ctx.experts` (dict，获取专家实例) |
| 改造要点 | 1. `self.experts` → `ctx.experts`<br>2. `@observe(name="expert-dispatch", as_type="agent")` 装饰器保留<br>3. `SupervisorGraph._build_graph()` 中 `self._dispatch_node` 改为 `self.dispatch_node.run` |
| 验证 | 启动后端 → 发送"导航到杭州东站" → 验证导航专家并行执行正常 → 验证 expert_results 合并正常 |

---

**Step 4: 创建 `nodes/responder_node.py` — Responder 节点**

| 项 | 内容 |
|----|------|
| 文件 | `agent/nodes/responder_node.py` (新建) |
| 抽取方法 | `_responder_node()` (L503-568, ~66行) + `_synthesize_tool_response()` (L570-688, ~119行) + `_generate_llm_response()` (L1483-1550, ~68行) + `_stream_llm_response()` (L1552-1600, ~49行) + `_get_system_prompt()` (L1201-1328, ~128行) + `_format_key_context()` (L1330-1353, ~24行) + `_get_location_status()` (L1355-1403, ~49行) |
| NodeContext 依赖 | `ctx.llm_client` (chat.completions.create — 待 P1-1 迁移到 chat_model.ainvoke)<br>`ctx.responder.compressor` (build_context)<br>`ctx.prompt_manager`<br>`ctx.memory_manager`<br>`ctx._background_tasks` |
| 改造要点 | 1. 全部 `self.xxx` → `ctx.xxx`<br>2. `@observe` 装饰器保留<br>3. `agent/responder.py` 的 `compressor` 持有逻辑迁移到此文件<br>4. `_get_system_prompt` 和 helper 方法作为 ResponderNode 的实例方法<br>5. `SupervisorGraph._build_graph()` 中 `self._responder_node` 改为 `self.responder_node.run` |
| 验证 | 启动后端 → 发送闲聊消息"你好" → 验证 LLM 回复生成正常 → 发送"搜索今天新闻" → 验证 Tool 合成正常 |

---

**Step 5: 创建 `nodes/reflection_node.py` — Reflection 反思节点**

| 项 | 内容 |
|----|------|
| 文件 | `agent/nodes/reflection_node.py` (新建) |
| 抽取方法 | `_reflection_node()` (L690-825, ~136行) + `_deterministic_date_check()` (L827-894, ~68行) + `_reflect_search_response()` (L896-1000, ~105行) + `_reflect_chat_response()` (L1002-1135, ~134行) + `_regenerate_with_feedback()` (L1137-1199, ~63行) + `_is_history_query()` (L1405-1407, ~3行) + `_has_history()` (L1409-1423, ~15行) + `_is_hallucinated_history()` (L1425-1427, ~3行) + `_pre_check_chat_response()` (L1429-1452, ~24行) + `_post_check_chat_response()` (L1454-1481, ~28行) |
| NodeContext 依赖 | `ctx.llm_client` (chat.completions.create — 反思校验 LLM 调用)<br>`ctx.prompt_manager`<br>`ctx.memory_manager`<br>`ctx._background_tasks` |
| 改造要点 | 1. 全部 `self.xxx` → `ctx.xxx`<br>2. `@observe` 装饰器保留<br>3. 闲聊前检查 `_pre_check_chat_response` 和后检查 `_post_check_chat_response` 作为 ReflectionNode 的实例方法<br>4. `_regenerate_with_feedback` 调用 `ctx.llm_client`，待 P1-1 统一迁移<br>5. `SupervisorGraph._build_graph()` 中 `self._reflection_node` 改为 `self.reflection_node.run` |
| 验证 | 启动后端 → 发送"今天几号" → 验证确定性日期检查正常 → 发送闲聊 → 验证幻觉检查正常 → 发送搜索类 → 验证搜索反思正常 |

---

**Step 6: 更新 `graph_builder.py` — 图构建逻辑**

| 项 | 内容 |
|----|------|
| 文件 | `agent/graph_builder.py` (修改) |
| 抽取方法 | `_build_graph()` (L133-178, ~46行) |
| 改造要点 | 1. 函数签名: `build_supervisor_graph(nodes: dict, checkpoint_saver=None) -> compiled_graph`<br>2. `nodes` 参数包含: `{"supervisor": supervisor_node.run, "dispatch": dispatch_node.run, "responder": responder_node.run, "reflection": reflection_node.run, "reviewer": reviewer_node.run, "vehicle_expert": experts["vehicle"].run, ...}`<br>3. 节点注册 + 边连接 + 条件边 + 编译 全部在此函数完成<br>4. `SupervisorGraph.__init__()` 调用 `build_supervisor_graph()` 替代内部 `_build_graph()` |
| 验证 | 启动后端 → 发送任意消息 → 验证 LangGraph 图执行流程正常 |

---

**Step 7: 重写 `supervisor_graph.py` — 瘦身编排入口**

| 项 | 内容 |
|----|------|
| 文件 | `agent/supervisor_graph.py` (重写，从 ~1725 行 → ~200 行) |
| 保留方法 | `__init__()` (创建 NodeContext + 创建节点实例 + 调用 graph_builder) + `invoke()` (L1703-1728) + `stream()` (L1730-1838) + `stream_with_events()` (L1840-1845) |
| 改造要点 | 1. `__init__` 中创建 `NodeContext` 并传入各节点构造函数<br>2. 创建 `SupervisorNode(ctx)`, `DispatchNode(ctx)`, `ResponderNode(ctx)`, `ReflectionNode(ctx)`, `ReviewerNode(ctx)`<br>3. 调用 `build_supervisor_graph()` 构建图<br>4. `invoke()` / `stream()` 逻辑保持不变（委托给 `self._graph`）<br>5. 删除所有已抽取的方法 |
| 验证 | 全量回归测试: 启动后端 → 发送 5 类测试消息 → 全部正常响应 → 延迟无退化 → `wc -l supervisor_graph.py` 确认 ≤ 300 行 |

---

**Step 8: 更新 `nodes/__init__.py` — 恢复导入**

| 项 | 内容 |
|----|------|
| 文件 | `agent/nodes/__init__.py` (修改) |
| 改造要点 | 取消注释，恢复导入: `SupervisorNode`, `DispatchNode`, `ResponderNode`, `ReflectionNode`, `ReviewerNode` |
| 验证 | `python -c "from nexus.agent.nodes import SupervisorNode, DispatchNode, ResponderNode, ReflectionNode, ReviewerNode; print('OK')"` |

---

#### 拆解后依赖关系图

```
SupervisorGraph (编排入口, ~200行)
  ├── NodeContext (共享依赖容器)
  │     ├── intent_router (IntentRouterService)
  │     ├── memory_manager (MemoryManager)
  │     ├── skill_registry (SkillRegistry)
  │     ├── llm_client (AsyncOpenAI, 待 P1-1 统一移除)
  │     ├── chat_model (ChatOpenAI, call_llm_with_fallback)
  │     ├── experts (dict[str, BaseExpertAgent])
  │     ├── responder (ResponderAgent → compressor)
  │     ├── reviewer (ReviewerAgent)
  │     ├── prompt_manager (PromptManager)
  │     └── _background_tasks (set)
  │
  ├── graph_builder.py (build_supervisor_graph)
  │     └── 注册节点 + 边连接 + 编译
  │
  ├── nodes/supervisor_node.py (SupervisorNode)
  │     └── run() → _supervisor_node 逻辑
  │
  ├── nodes/dispatch_node.py (DispatchNode)
  │     └── run() → _dispatch_node 逻辑
  │
  ├── nodes/responder_node.py (ResponderNode)
  │     └── run() → _responder_node + _synthesize_tool + _generate_llm + _get_prompt
  │
  ├── nodes/reflection_node.py (ReflectionNode)
  │     └── run() → _reflection_node + _reflect_search + _reflect_chat + 日期检查 + 幻觉检查
  │
  └── nodes/reviewer_node.py (ReviewerNode)
        └── run() → 委托 ReviewerAgent.review()
```

#### 其他冗余文件清理（仅未解决项）

| 文件 | 处理方式 | 理由 |
|------|---------|------|
| `agent/responder.py` | 🔄 保留但迁移 | `compressor` 持有逻辑迁移到 `responder_node.py` (依赖 Step 4 完成) |
| `skills/default.yaml` | 🔄 重新定位 | 转为技能开发参考文档，不参与运行时 |

---

## 章节4：轻量化开源组件精准适配规划

### 4.1 自研模块 → 开源组件对照表（仅待落地项）

| # | 自研模块 | 可选开源组件 | 是否接入 | 仅使用该框架哪些能力 | 舍弃框架多余功能 | 改造收益 |
|---|---------|-------------|---------|-------------------|---------------|---------|
| 1 | Prompt 模板管理 (`prompts/__init__.py`) | **LangChain 1.x** `ChatPromptTemplate` | ⚠️ 可选接入 | 模板渲染 + 变量注入 + Few-shot | — | 当前自研 `PromptManager` 功能够用，**保留原生写法** |
| 2 | 结构化 Skill 定义 (`skills/base.py`) | **LangChain 1.x** `StructuredTool` / `@tool` | ⚠️ 可选接入 | Skill → Tool Schema 自动生成 | `create_react_agent` 等 | 当前自研 `@register_skill` 装饰器运行稳定，**保留原生写法** |
| 3 | MainAgent 进程 ↔ 语音服务进程 ↔ CAN 服务进程跨模块通信 | **MCP** 协议 | 🔜 待接入 | 标准化进程间通信协议 | — | 替换自研 stdio JSON-RPC 为 MCP SDK 标准实现 |

### 4.2 固定使用边界

#### 边界 1: LangChain 1.x — 局部接入

| 使用能力 | 使用位置 | 不使用能力 | 理由 |
|---------|---------|-----------|------|
| `ChatOpenAI.ainvoke()` | `llm_client_factory.py` | Agent Executor | LangGraph StateGraph 已替代 |
| `with_structured_output()` | Reflection 节点 JSON 解析 (待迁移) | Tool Calling Agent | 自研意图路由更适配车载场景 |
| `astream()` | 流式回复 (待迁移) | | |
| `trim_messages()` | 上下文压缩 token 截断 | | |

#### 边界 2: LangGraph — 按需使用状态编排

| 使用能力 | 使用位置 | 不使用能力 | 理由 |
|---------|---------|-----------|------|
| `StateGraph` + `add_node` + `add_conditional_edges` | `supervisor_graph.py` | `create_react_agent` | 自研 Supervisor 路由更精确 |
| `AsyncSqliteSaver` checkpoint | `main.py` | `ToolNode` prebuilt | 自研 `_dispatch_node` 支持并行+合并 |
| `Annotated[list, add]` reducer | `models/state.py` | | |

#### 边界 3: MCP — 多服务标准化协同

| 使用能力 | 使用位置 | 不使用能力 | 理由 |
|---------|---------|-----------|------|
| MCP stdio 传输协议 | `vehicle/mcp.py` (待迁移到 MCP SDK) | MCP Server 注册中心 | 单机车载无需 |
| MCP tools/call | 车控指令下发 | MCP Resources | 不需要 |
| MCP initialize + tools/list | 车控服务发现 | MCP Prompts | 不需要 |

> **迁移方案**: 将 `vehicle/mcp.py` 中自研的 `StdioJsonRpcTransport` 替换为 MCP SDK 的 `mcp.ClientSession` + `mcp.StdioServerParameters`，保留 `MCPStdioVehicleAdapter` 接口不变。

#### 边界 4: Skill 插件化 — 统一注册管理

| 当前实现 | 改造计划 |
|---------|---------|
| `@register_skill` 装饰器自动注册 | 无需改动 |
| `SkillRegistry` 自动发现 + 手动注册 | 无需改动 |
| `SkillGroup` 枚举分组 | 无需改动 |
| `SkillResult` 统一结果 | 无需改动 |
| `has_side_effect` / `cache_ttl` 缓存安全控制 | 无需改动 |

---

## 章节5：改造后标准工程目录结构

> 以下目录结构适配 Windows 10/11 + RTX4070 仿真车机部署。

```
NexusCockpit/
│
├── backend_design/                    # 后端 Python 代码
│   ├── nexus/
│   │   ├── agent/                     # ═══ Multi-Agent 调度目录 ═══
│   │   │   ├── supervisor_graph.py    # [待瘦身] 编排入口: 初始化 + invoke/stream (~200行)
│   │   │   ├── graph_builder.py       # [待激活] 图构建: 节点注册 + 边连接 + 编译
│   │   │   ├── llm_client_factory.py  # [保留] LLM 客户端工厂
│   │   │   ├── experts/               # [保留] Sub-Agent 职能目录
│   │   │   │   ├── base.py            #   专家基类
│   │   │   │   ├── vehicle_expert.py  #   车控专家 (含沙箱安全审查)
│   │   │   │   ├── nav_expert.py      #   导航专家
│   │   │   │   ├── lifestyle_expert.py#   生活推荐专家
│   │   │   │   ├── health_expert.py   #   车辆健康专家
│   │   │   │   └── chat_expert.py     #   闲聊专家
│   │   │   └── nodes/                 # [待拆解] 节点逻辑目录
│   │   │       ├── supervisor_node.py #   Supervisor 节点 (待创建)
│   │   │       ├── dispatch_node.py   #   专家并行分派节点 (待创建)
│   │   │       ├── responder_node.py  #   Responder 节点 (待创建)
│   │   │       ├── reflection_node.py #   Reflection 节点 (待创建)
│   │   │       └── reviewer_node.py   #   Reviewer 节点 (已修复循环依赖)
│   │   │
│   │   ├── core/                      # ═══ 底层固化目录 ═══
│   │   │   ├── llama_cpp_manager.py   # llama.cpp 子进程管理
│   │   │   ├── voiceprint.py          # 声纹识别
│   │   │   ├── device.py              # 音频设备管理
│   │   │   ├── db_manager.py          # MySQL 数据库管理
│   │   │   ├── cockpit_manager.py     # 多座舱管理
│   │   │   ├── auth.py                # JWT 认证
│   │   │   ├── circuit_breaker.py     # 熔断器
│   │   │   ├── exceptions.py          # 异常定义
│   │   │   ├── logger.py              # 日志管理
│   │   │   ├── personalization.py     # 个性化引擎
│   │   │   ├── tenant_context.py      # 多租户上下文
│   │   │   ├── ssl_fix.py             # SSL 修复
│   │   │   └── sandbox.py              # 高危车控指令沙箱安全隔离
│   │   │
│   │   ├── skills/                    # ═══ Skill 插件目录 ═══
│   │   │   ├── base.py                # 技能基类 + @register_skill 装饰器
│   │   │   ├── registry.py            # 技能注册中心
│   │   │   ├── vehicle/               # 车控技能组
│   │   │   ├── special.py             # 非车控技能 (搜索/点餐/声纹注册)
│   │   │   ├── habit.py               # 习惯画像技能
│   │   │   ├── health.py              # 车辆健康技能
│   │   │   ├── reminder.py            # 日程提醒技能
│   │   │   └── default.yaml           # [待重新定位] 技能开发参考文档
│   │   │
│   │   ├── intent/                    # 意图路由
│   │   ├── memory/                    # 记忆管理
│   │   │   ├── manager.py             # 长期记忆召回 (GraphRAG)
│   │   │   ├── compressor.py          # 上下文压缩/滚动摘要
│   │   │   ├── conflict.py            # 记忆冲突检测
│   │   │   └── context_coordinator.py # 统一上下文管理门面
│   │   ├── rag/                       # 知识库 RAG
│   │   ├── middleware/                # 中间件 (Redis缓存/限流/会话)
│   │   ├── observability/             # 可观测性
│   │   │   ├── langfuse.py            # LLM 追踪
│   │   │   ├── metrics.py             # Prometheus 指标
│   │   │   ├── data_retention.py      # 数据保留策略
│   │   │   ├── cockpit_metrics.py     # 座舱指标
│   │   │   └── unified.py             # 统一可观测性门面
│   │   ├── prompts/                   # Prompt 模板
│   │   ├── models/                    # 数据模型
│   │   ├── api/                       # API 路由
│   │   ├── asr/                       # 底层固化 (零修改)
│   │   ├── tts/                       # 底层固化 (零修改)
│   │   ├── vehicle/                   # 底层固化 (零修改)
│   │   ├── mcp/                       # [待新增] MCP 标准协议通信目录
│   │   │   └── transport.py           # MCP SDK 传输层 (待创建)
│   │   ├── config/                    # 配置中心 (已拆分为子目录)
│   │   ├── main.py                    # FastAPI 入口
│   │   └── __init__.py
│   │
│   ├── nexus_gate/                    # Go 网关
│   ├── scripts/                       # 部署脚本目录
│   ├── tests/                         # 测试目录
│   ├── requirements.txt               # 分层依赖清单
│   └── pyproject.toml
│
├── frontend_design/                   # 前端
├── config/                            # 统一配置目录
│   ├── grafana/
│   ├── loki/
│   └── prometheus/
├── models/                            # 模型资源目录
├── data/                              # 数据目录
├── assets/                            # 音频资源目录
├── scripts/                           # 启动脚本目录
├── logs/                              # 日志目录
├── docs/                              # 交付文档目录
├── .env.local                         # 本地环境配置
├── docker-compose.yml
├── docker-compose.dev.yml
├── Makefile
└── README.md
```

**待落地新增文件清单**:
1. `nexus/agent/nodes/supervisor_node.py` — 从 supervisor_graph.py 拆出
2. `nexus/agent/nodes/dispatch_node.py` — 从 supervisor_graph.py 拆出
3. `nexus/agent/nodes/responder_node.py` — 从 supervisor_graph.py 拆出
4. `nexus/agent/nodes/reflection_node.py` — 从 supervisor_graph.py 拆出
5. `nexus/mcp/transport.py` — MCP SDK 标准传输层

**待落地删除/迁移文件清单**:
1. `nexus/agent/responder.py` — 空壳文件删除（compressor 迁移到 responder_node.py）
2. `nexus/skills/default.yaml` — 重新定位为技能开发参考文档

---

## 章节6：requirements 分层整改方案

### 6.1 [prod] 车机仿真运行生产依赖

```txt
# ============================================================
# NexusCockpit [prod] 车机仿真运行生产依赖
# Python >= 3.10 required
# PyTorch must be installed separately before this file.
#   GPU: pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
# ============================================================

# --- Web Framework ---
fastapi==0.128.0
uvicorn[standard]==0.40.0
python-multipart==0.0.21
websockets==12.0
starlette==0.50.0

# --- LLM / Agent (LangChain + LangGraph 全栈) ---
langchain-openai>=1.1.0
langchain-core>=1.2.0
langchain-text-splitters>=1.0.0
langgraph>=1.0.6
langgraph-checkpoint-sqlite>=2.0.0

# --- RAG / Vector Store ---
langchain-community>=0.4.0           # BM25Retriever
pymilvus>=3.0.0
neo4j>=5.18.0
sentence-transformers>=2.7.0

# --- Middleware ---
redis==5.0.0

# --- Database ---
aiomysql>=0.2.0

# --- MCP ---
mcp>=2.0.0

# --- Config / Validation ---
pydantic==2.12.5
pydantic-core==2.41.5
pydantic-settings>=2.1.0
python-dotenv==1.2.1

# --- Observability ---
langfuse==4.5.0
prometheus-client==0.23.1
structlog>=24.1.0

# --- Auth ---
PyJWT>=2.10.0
passlib[bcrypt]>=1.7.4

# --- Audio / ASR / TTS (固化层) ---
funasr==1.1.12
modelscope==1.15.0
torchaudio>=2.2.0
librosa==0.11.0
soundfile==0.13.1
pydub==0.25.1

# --- HTTP / Network ---
httpx==0.28.1
requests==2.32.5
aiohttp==3.13.3

# --- Utils ---
orjson==3.11.5
tiktoken==0.12.0
PyYAML==6.0.3

# --- Search ---
tavily==1.1.0

# --- Data Processing ---
numpy==1.26.4
pandas==2.3.3

# --- NLP ---
sentencepiece==0.2.1
transformers==4.45.2
tokenizers==0.20.3
```

### 6.2 [dev] 仅本地调试、代码格式化、单元测试使用依赖

```txt
# ============================================================
# NexusCockpit [dev] 开发工具依赖
# 安装方式: pip install -r requirements-dev.txt
# ============================================================

# --- Dev Tools ---
pytest==9.0.2
pytest-asyncio>=0.23.0
pytest-cov>=4.1.0
ruff>=0.3.0
mypy>=1.8.0
```

### 6.3 原有依赖处理明细

| 包名 | 处理方式 | 理由 |
|------|---------|------|
| `mcp>=2.0.0` | 待落地 | 待替换自研 stdio JSON-RPC 为 MCP SDK 标准实现 |
| 其余全部包 | 原样保留 | — |

---

## 章节7：分模块整改优先级矩阵

### 高优 (P0 — 必须整改，架构严重问题)

| # | 整改项 | 整改内容 | 预估工作量 | 影响范围 |
|---|--------|---------|-----------|---------|
| P0-2 | **`supervisor_graph.py` 拆分** | 将 ~1725 行上帝类拆解为 6 个文件 (graph_builder + 4 个 node 文件 + 瘦身后的 supervisor_graph) | 3-5 天 | `agent/` 全部 |

### 中优 (P1 — 架构规范化优化，提升可维护性)

| # | 整改项 | 整改内容 | 预估工作量 | 影响范围 |
|---|--------|---------|-----------|---------|
| P1-1 | **LLM 调用统一到 ChatOpenAI** | 将 `supervisor_graph.py` 中 `self.llm_client.chat.completions.create()` 统一迁移到 `ChatOpenAI.ainvoke()` | 1-2 天 | `agent/`, `intent/` |
| P1-2 | **LangGraph 图编排优化** | 使用拆分后的 `graph_builder.py` 替代 `supervisor_graph.py` 内部 `_build_graph()` | 1 天 | `agent/` |
| P1-4 | **MCP SDK 落地** | 用 `mcp.ClientSession` 替换 `vehicle/mcp.py` 中自研 `StdioJsonRpcTransport` | 2-3 天 | `vehicle/`, `mcp/` |

### 低优 (P2 — 可选迭代优化)

| # | 整改项 | 整改内容 | 预估工作量 | 影响范围 |
|---|--------|---------|-----------|---------|
| P2-1 | **Windows 后台常驻部署** | 编写 Windows Service / Task Scheduler 自启方案 | 1-2 天 | `scripts/` |
| P2-4 | **default.yaml 技能配置重定位** | 转为技能开发参考文档 | 0.5 天 | `skills/` |
| P2-5 | **交付文档补齐** | 补充架构改造设计文档、测试验证方案 | 2-3 天 | `docs/` |

---

## 章节8：Windows(RTX4070) 本机仿真车机部署规范

### 8.1 GPU 显存资源分配

| 组件 | 显存占用 (预估) | 说明 |
|------|----------------|------|
| LLM 推理 (llama.cpp Qwen3.5-4B Q4_K_M) | ~3.0 GB | RTX4070 8GB 的 37.5% |
| ASR (FunASR SenseVoice) | ~0.8 GB | 仅推理时加载 |
| TTS (CosyVoice) | ~1.2 GB | 仅推理时加载 |
| Embedding (bge-m3 sentence-transformers) | ~0.5 GB | 常驻 |
| Reranker (bge-reranker-v2-m3) | ~0.4 GB | 常驻 |
| 声纹 (CAM++) | ~0.2 GB | 仅验证时加载 |
| **总计** | **~6.1 GB** | RTX4070 8GB 显存可承载 |
| **剩余** | **~1.9 GB** | 预留给系统/浏览器等 |

> **显存管理策略**: ASR/TTS 模型后台预加载（`asyncio.create_task`），首次请求时已就绪。LLM 推理通过 llama.cpp 子进程管理，支持 `--gpu-layers` 参数控制 GPU 层数。

### 8.2 多进程守护运行

| 进程 | 启动方式 | 守护方式 |
|------|---------|---------|
| FastAPI 后端 | `python -m nexus.main` / `uvicorn nexus.main:app` | PowerShell 脚本 + 日志捕获 |
| Go 网关 (NexusGate) | `nexus_gate` 二进制 | PowerShell 脚本 + 日志捕获 |
| Next.js 前端 | `npm run dev` / `npm run start` | PowerShell 脚本 + 日志捕获 |
| llama.cpp 子进程 | Python `subprocess.Popen` | `LlamaCppProcessManager` 健康检查 + 崩溃重启 |
| Docker 中间件 | `docker compose up -d` | Docker 容器自动重启 (`restart: unless-stopped`) |

### 8.3 环境变量隔离

| 环境文件 | 用途 | 安全级别 |
|---------|------|---------|
| `.env` | 统一默认配置 (提交 GitHub) | 公开 |
| `.env.local` | 本机覆盖配置 (不提交, 含个人 API Key) | 敏感 |
| `.env.prod` | 生产环境配置 (不提交) | 敏感 |

**加载优先级**: `.env.local` > `.env` (存在则覆盖)

### 8.4 配置加载策略

- `config/` 子目录使用 `pydantic-settings.BaseSettings` 自动从 `.env` 文件读取
- 路径解析使用 `_resolve_path()` 函数确保基于项目根目录
- `model_post_init` 实现 LLM_PROVIDER=local 时自动切换连接参数
- `@lru_cache(maxsize=1)` 确保全局单例配置

### 8.5 模型资源目录管理

```
models/
├── asr/sensevoice/           # ASR 模型 (~500MB)
├── llm/
│   ├── llama.cpp/           # llama-server 二进制
│   └── qwen/                # Qwen3.5-4B GGUF 模型 (~2.5GB)
├── reranker/
│   └── bge-reranker-v2-m3/  # Reranker 模型 (~560MB)
├── sv/cam_plus/             # 声纹模型 (~30MB)
└── tts/cosyvoice/           # TTS 模型 (~1.5GB)
```

### 8.6 Windows 开机自启方案 (低优 P2)

**方案 A — Task Scheduler (推荐)**:
1. 创建 `scripts/start-all.ps1` 一键启动脚本
2. 在 Windows Task Scheduler 中创建任务，触发器设为"用户登录时"
3. 操作设为运行 `start-all.ps1`

**方案 B — Windows Service (可选)**:
1. 使用 `nssm` (Non-Sucking Service Manager) 将 Python 进程注册为 Windows Service
2. 设置服务恢复策略为"自动重启"

### 8.7 离线环境部署校验步骤

1. **Docker 中间件启动**: `docker compose up -d` → 等待 Milvus/Neo4j/Redis/MySQL 健康检查通过
2. **Python 虚拟环境激活**: `.\.venv\Scripts\activate`
3. **配置文件检查**: 确认 `.env.local` 存在且 API Key 有效
4. **模型文件检查**: 确认 `models/` 下各模型文件完整
5. **后端启动**: `make dev` 或 `make dev-log` → 等待 "NexusCockpit ready!" 日志
6. **API 健康检查**: `curl http://localhost:8000/health` → 返回 `{"status": "ok"}`
7. **LLM 联通测试**: 通过 `/chat` 接口发送测试消息
8. **车控指令测试**: 通过 `/vehicle` 接口发送模拟指令
9. **前端启动**: `make dev-frontend` → 浏览器访问 `http://localhost:3000`
10. **Go 网关启动** (可选): `make dev-gateway-log` → 网关代理测试

---

## 章节9：改造验收硬性标准

### 9.1 业务功能一致性验收

| # | 验收项 | 验收标准 | 验证方法 |
|---|--------|---------|---------|
| 1 | 语音交互全链路 | 唤醒→ASR→Agent→TTS 全链路功能与改造前 100% 一致 | 语音输入"打开空调" → ASR 识别 → Agent 执行 → TTS 播报 |
| 2 | 车控指令执行 | 空调/车窗/座椅/导航/媒体/车况 6 类指令全部正常执行 | 逐类发送语音指令，验证 MockVehicleBus 状态变更 |
| 3 | 知识库问答 | 车辆手册/故障码/FAQ 问答功能正常 | 发送"发动机故障灯亮了怎么办" → 检索知识库 → 生成回复 |
| 4 | 闲聊对话 | 纯 LLM 闲聊功能正常 | 发送"你好" → LLM 生成自然语言回复 |
| 5 | 联网搜索 | Tavily 搜索技能正常 | 发送"明天天气怎么样" → 搜索 → 生成回复 |
| 6 | 记忆管理 | 短期历史/长期记忆/习惯注入 功能正常 | 多轮对话后验证记忆召回 |
| 7 | 底层零侵入 | 音频采集、降噪、ASR/TTS 推理、CAN 报文收发代码零修改 | `git diff` 确认 `asr/`, `tts/`, `vehicle/`, `core/llama_cpp_manager.py` 等固化层无变更 |

### 9.2 框架接入边界验收

| # | 验收项 | 验收标准 | 验证方法 |
|---|--------|---------|---------|
| 1 | 无多余框架组件 | 项目不出现 `langgraph-prebuilt`, `langchain-milvus`, `langchain-neo4j` 等未落地依赖 | `pip list` 检查 + `requirements.txt` 审查 |
| 2 | 无多层嵌套臃肿 | LangChain/LangGraph 仅启用规划内能力 | 代码审查 `import` 语句 |
| 3 | 上帝类消除 | `supervisor_graph.py` ≤ 300 行 | `wc -l supervisor_graph.py` |
| 4 | 节点文件单一职责 | 每个节点文件 ≤ 500 行 | `wc -l agent/nodes/*.py` |

### 9.3 每个改造模块的 Windows 本机自测方案

| 改造模块 | 自测方案 | 校验指标 |
|---------|---------|---------|
| `supervisor_graph.py` 拆分 | 启动后端 → 发送 5 类测试消息 → 验证 Agent 工作流完整执行 | 全部 5 类消息正常响应，延迟 < 改造前 +10% |
| 冗余代码清理 | `ruff check` 无 unused import 警告 | 0 个 unused import |
| LLM 调用统一 | 发送闲聊消息 → 验证 `ChatOpenAI.ainvoke()` 被调用 | Langfuse 追踪显示 `ChatOpenAI` 调用链路 |
| MCP SDK 落地 | 配置 `VEHICLE_ADAPTER=mcp-stdio` → 发送车控指令 | 车控指令通过 MCP SDK 正常执行 |

---

## 附录：技术选型版本约束

| 框架/组件 | 版本约束 | 选用理由 | 舍弃能力 |
|----------|---------|---------|---------|
| LangChain | 1.2.x ~ 1.3.x | LLM 统一调用、Prompt 模板、结构化 Skill 定义、对话记忆管理 | Agent Executor, Tool Calling Agent |
| LangGraph | 匹配 LangChain 兼容正式版 | StateGraph 工作流编排、Sub-Agent 状态调度、Checkpoint 持久化 | create_react_agent, ToolNode prebuilt |
| DeepAgents | 仅 Sandbox 模块 | 高危车控指令沙箱执行隔离 | Agent 框架、Tool 体系、Memory |
| MCP | 2.x | 多 Agent 进程、语音进程、CAN 通信进程标准化协同 | Server 注册中心、Resources、Prompts |

---

> **白皮书生效条件**: 本文档经项目负责人审阅确认后生效。后续代码重构将严格按照本白皮书约定的架构方案、组件接入范围、版本号、整改优先级开展，禁止私自扩充改造范围、额外引入无关框架。

> **文档结束**
