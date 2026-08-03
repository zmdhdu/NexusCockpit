# 车载 Multi-Agent 系统架构诊断 & 轻量化开源适配优化白皮书

> **文档编号**: NX-WP-2026-001  
> **版本**: v3.1 (LangChain 可选接入完成版)  
> **编制日期**: 2026-08-01  
> **项目**: NexusCockpit — 车载离线 Multi-Agent 语音系统  
> **运行环境**: Windows 10/11 x64 + NVIDIA RTX4070 (CUDA) 本地仿真车机  
> **密级**: 内部开发存档

---

## 整改完成总结

> 全部 P0/P1/P2 整改项已落地，以下为完成清单。

| # | 整改项 | 完成内容 | 影响范围 |
|---|--------|---------|---------|
|  | **`supervisor_graph.py` 拆分** | ~1725 行上帝类拆解为 6 个文件 (graph_builder + 4 个 node 文件 + 瘦身后的 supervisor_graph)，supervisor_graph.py 从 ~1725 行瘦身到 ~280 行 | `agent/` 全部 |
|  | **LLM 调用统一到 ChatOpenAI** | 7 处 `llm_client.chat.completions.create()` 全部迁移为 `chat_model.ainvoke()` / `chat_model.astream()`，token 用量从 `usage.prompt_tokens` 迁移到 `usage_metadata.input_tokens` | `agent/` |
|  | **LangGraph 图编排优化** | `graph_builder.py` 的 `build_supervisor_graph()` 替代 `supervisor_graph.py` 内部 `_build_graph()` | `agent/` |
|  | **MCP SDK 落地** | `vehicle/mcp.py` 中自研 `StdioJsonRpcTransport` 替换为 MCP SDK 的 `mcp.ClientSession` + `mcp.StdioServerParameters`，通过后台 asyncio 事件循环桥接同步接口，`MCPStdioVehicleAdapter` 接口不变 | `vehicle/` |
|  | **Windows 后台常驻部署** | 新增 `scripts/start-all.ps1` (一键后台启动) + `scripts/install-autostart.ps1` (Task Scheduler 自启注册) + `scripts/stop-all.ps1` (全部停止) | `scripts/` |
|  | **default.yaml 技能配置重定位** | `skills/default.yaml` 头部添加显著注释标记为技能开发参考文档，不在运行时加载；`skills/__init__.py` 同步更新说明 | `skills/` |
|  | **交付文档补齐** | 白皮书 v3.0 更新，移除已落地项和保留状态参考表，仅保留待确认项和验收/部署规范 | `docs/` |
| LC-1 | **LangChain ChatPromptTemplate 接入** | `PromptManager` 从手动 `string.replace()` 迁移到 `ChatPromptTemplate.from_template().format()`，模板文件无需修改 | `prompts/` |
| LC-2 | **LangChain StructuredTool 接入** | `BaseSkill` 新增 `to_structured_tool()` 方法，动态创建 Pydantic `args_schema` 并包装 `execute()` 为 `StructuredTool`；`SkillRegistry` 新增 `get_structured_tools()` | `skills/` |

---

## LangChain 可选接入项 (已落地)

以下两项已确认接入，原有原生写法保留向后兼容。

| # | 自研模块 | 接入组件 | 接入内容 |
|---|---------|---------|--------|
| 1 | Prompt 模板管理 (`prompts/__init__.py`) | LangChain `ChatPromptTemplate` | ✅ 已接入 — `PromptManager` 内部使用 `ChatPromptTemplate.from_template()` 创建模板，`.format()` 渲染变量，保留降级手动替换 |
| 2 | 结构化 Skill 定义 (`skills/base.py`) | LangChain `StructuredTool` | ✅ 已接入 — `BaseSkill.to_structured_tool()` 动态创建 Pydantic `args_schema` 并包装 `execute()` 为 `StructuredTool`；`SkillRegistry.get_structured_tools()` 批量转换 |

---

## 章节：分模块整改优先级矩阵

### 高优 (P0 — 必须整改，架构严重问题)

| # | 整改项 | 状态 | 完成内容 |
|---|--------|------|---------|
|  | **`supervisor_graph.py` 拆分** | ✅ 已完成 | 拆解为 6 个文件：context.py + supervisor_node.py + dispatch_node.py + responder_node.py + reflection_node.py + graph_builder.py，supervisor_graph.py 瘦身为编排入口 |

### 中优 (P1 — 架构规范化优化，提升可维护性)

| # | 整改项 | 状态 | 完成内容 |
|---|--------|------|---------|
|  | **LLM 调用统一到 ChatOpenAI** | ✅ 已完成 | responder_node.py (3处) + reflection_node.py (4处) 共 7 处 `llm_client.chat.completions.create()` 迁移为 `chat_model.ainvoke()` / `astream()` |
|  | **LangGraph 图编排优化** | ✅ 已完成 | `build_supervisor_graph()` 替代内部 `_build_graph()`，graph_builder.py 正式承担图构建职责 |
|  | **MCP SDK 落地** | ✅ 已完成 | `_MCPBackgroundRunner` 后台线程运行 MCP SDK 异步上下文，`MCPStdioVehicleAdapter` 同步接口不变 |

### 低优 (P2 — 可选迭代优化)

| # | 整改项 | 状态 | 完成内容 |
|---|--------|------|---------|
|  | **Windows 后台常驻部署** | ✅ 已完成 | `scripts/start-all.ps1` + `install-autostart.ps1` + `stop-all.ps1`，Task Scheduler 登录自启 |
|  | **default.yaml 技能配置重定位** | ✅ 已完成 | 文件头部注释标记为开发参考文档，`skills/__init__.py` 同步说明 |
|  | **交付文档补齐** | ✅ 已完成 | 白皮书 v3.0 精简更新 |

---

## 章节：Windows(RTX4070) 本机仿真车机部署规范

### GPU 显存资源分配

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

### 多进程守护运行

| 进程 | 启动方式 | 守护方式 |
|------|---------|---------|
| FastAPI 后端 | `uvicorn nexus.main:app --host 0.0.0.0 --port 8000` | `scripts/start-all.ps1` 后台启动 + Task Scheduler 自启 |
| Go 网关 (NexusGate) | `go run ./cmd/ --env .env.local` | `scripts/start-all.ps1` 后台启动 + Task Scheduler 自启 |
| Next.js 前端 | `npm run dev` | `scripts/start-all.ps1` 后台启动 + Task Scheduler 自启 |
| llama.cpp 子进程 | Python `subprocess.Popen` | `LlamaCppProcessManager` 健康检查 + 崩溃重启 |
| Docker 中间件 | `docker compose up -d` | Docker 容器自动重启 (`restart: unless-stopped`) |

### 环境变量隔离

| 环境文件 | 用途 | 安全级别 |
|---------|------|---------|
| `.env` | 统一默认配置 (提交 GitHub) | 公开 |
| `.env.local` | 本机覆盖配置 (不提交, 含个人 API Key) | 敏感 |
| `.env.prod` | 生产环境配置 (不提交) | 敏感 |

**加载优先级**: `.env.local` > `.env` (存在则覆盖)

### 配置加载策略

- `config/` 子目录使用 `pydantic-settings.BaseSettings` 自动从 `.env` 文件读取
- 路径解析使用 `_resolve_path()` 函数确保基于项目根目录
- `model_post_init` 实现 LLM_PROVIDER=local 时自动切换连接参数
- `@lru_cache(maxsize=1)` 确保全局单例配置

### 模型资源目录管理

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

### Windows 开机自启方案 ( 已落地)

**方案 A — Task Scheduler (已实现)**:
1. `scripts/start-all.ps1` — 一键后台启动 Backend + Gateway + Frontend，各进程独立日志捕获
2. `scripts/install-autostart.ps1` — 注册 Windows Task Scheduler 任务 "NexusCockpitAutoStart"，用户登录时自动触发
3. `scripts/stop-all.ps1` — 按端口 (8000/9090/3000) 精准停止全部后台进程

**使用方式**:
```powershell
# 注册开机自启
.\scripts\install-autostart.ps1

# 手动启动全部服务（后台运行）
.\scripts\start-all.ps1

# 停止全部服务
.\scripts\stop-all.ps1

# 移除自启任务
.\scripts\install-autostart.ps1 -Remove
```

**方案 B — Windows Service (可选，未实现)**:
1. 使用 `nssm` (Non-Sucking Service Manager) 将 Python 进程注册为 Windows Service
2. 设置服务恢复策略为"自动重启"

### 离线环境部署校验步骤

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

## 章节：改造验收硬性标准

### 业务功能一致性验收

| # | 验收项 | 验收标准 | 验证方法 |
|---|--------|---------|---------|
| 1 | 语音交互全链路 | 唤醒→ASR→Agent→TTS 全链路功能与改造前 100% 一致 | 语音输入"打开空调" → ASR 识别 → Agent 执行 → TTS 播报 |
| 2 | 车控指令执行 | 空调/车窗/座椅/导航/媒体/车况 6 类指令全部正常执行 | 逐类发送语音指令，验证 MockVehicleBus 状态变更 |
| 3 | 知识库问答 | 车辆手册/故障码/FAQ 问答功能正常 | 发送"发动机故障灯亮了怎么办" → 检索知识库 → 生成回复 |
| 4 | 闲聊对话 | 纯 LLM 闲聊功能正常 | 发送"你好" → LLM 生成自然语言回复 |
| 5 | 联网搜索 | Tavily 搜索技能正常 | 发送"明天天气怎么样" → 搜索 → 生成回复 |
| 6 | 记忆管理 | 短期历史/长期记忆/习惯注入 功能正常 | 多轮对话后验证记忆召回 |
| 7 | 底层零侵入 | 音频采集、降噪、ASR/TTS 推理、CAN 报文收发代码零修改 | `git diff` 确认 `asr/`, `tts/`, `vehicle/`, `core/llama_cpp_manager.py` 等固化层无变更 |

### 框架接入边界验收

| # | 验收项 | 验收标准 | 验证方法 |
|---|--------|---------|---------|
| 1 | 无多余框架组件 | 项目不出现 `langgraph-prebuilt`, `langchain-milvus`, `langchain-neo4j` 等未落地依赖 | `pip list` 检查 + `requirements.txt` 审查 |
| 2 | 无多层嵌套臃肿 | LangChain/LangGraph 仅启用规划内能力 | 代码审查 `import` 语句 |
| 3 | 上帝类消除 | `supervisor_graph.py` ≤ 300 行 | `wc -l supervisor_graph.py` |
| 4 | 节点文件单一职责 | 每个节点文件 ≤ 500 行 | `wc -l agent/nodes/*.py` |

### 每个改造模块的 Windows 本机自测方案

| 改造模块 | 自测方案 | 校验指标 |
|---------|---------|---------|
| `supervisor_graph.py` 拆分 | 启动后端 → 发送 5 类测试消息 → 验证 Agent 工作流完整执行 | 全部 5 类消息正常响应，延迟 < 改造前 +10% |
| LLM 调用统一 | 发送闲聊消息 → 验证 `ChatOpenAI.ainvoke()` 被调用 | Langfuse 追踪显示 `ChatOpenAI` 调用链路 |
| MCP SDK 落地 | 配置 `VEHICLE_ADAPTER=mcp-stdio` → 发送车控指令 | 车控指令通过 MCP SDK 正常执行 |
| Windows 自启部署 | 运行 `install-autostart.ps1` → 注销重新登录 | Backend/Gateway/Frontend 全部后台启动 |

---

## 附录：技术选型版本约束

| 框架/组件 | 版本约束 | 选用理由 | 舍弃能力 |
|----------|---------|---------|---------|
| LangChain | 1.2.x ~ 1.3.x | LLM 统一调用、Prompt 模板、结构化 Skill 定义、对话记忆管理 | Agent Executor, Tool Calling Agent |
| LangGraph | 匹配 LangChain 兼容正式版 | StateGraph 工作流编排、Sub-Agent 状态调度、Checkpoint 持久化 | create_react_agent, ToolNode prebuilt |
| MCP | 2.x | 多 Agent 进程、语音进程、CAN 通信进程标准化协同 | Server 注册中心、Resources、Prompts |

---

> **白皮书生效条件**: 本文档经项目负责人审阅确认后生效。后续代码重构将严格按照本白皮书约定的架构方案、组件接入范围、版本号、整改优先级开展，禁止私自扩充改造范围、额外引入无关框架。

> **文档结束**
