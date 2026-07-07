# 车载语音 Agent — 混合语言架构与本地落地方案 (Landing v3)

> **文档定位**：在 `vehicle_agent_improvement_plan.md`（V2 深度版）之上，补齐三块短板——
> ① **混合语言架构（作为选型，非全量使用）**：C++ / Go / Rust / Python 是架构选型池，按场景择优，给出最小档/标准档/完整档三档落地范围，**默认只落必需项**，不为用而用（见 §3）；
> ② **实施级细节**（进程边界、IPC 契约、端口、Schema、延迟/显存预算，可直接据此写代码）；
> ③ **本地落地 Runbook**（Win11 + RTX 4070 单机一键起来）。
>
> **复用优先（成本/工时换性能）**：同一组件尽量多用途覆盖，**显式接受小幅性能损失换开发时长与运维成本**——Redis 一物七用、FastAPI 兼 BFF+网关、PostgreSQL 兼 Outbox+审计+结构化、Milvus 兼 RAG+缓存回退。删减 RabbitMQ/Celery/Nginx 等"为了用而用"的重型件（见 §4 复用矩阵 + 附录 A 复用决策）。
>
> **与现有文档关系**：本文件不重复 V2 计划已经写清的内容（多 Agent / GraphRAG / 前端 / 监控等），只在其上做「语言分工 + 契约定义 + 落地工程」的增量，并对冲突点给出决策。配套的 `gap_analysis.md` 记录查缺补漏清单。
>
> **硬件环境**：NVIDIA RTX 4070 (8GB 或 12GB VRAM) + Win11 + i7-14650HX/1400HX + 32GB RAM（建议）。
> **最后更新**：2026-07-07

---

## 目录

- [1. 设计目标与约束](#1-设计目标与约束)
- [2. 混合语言是选型而非全用（原则）](#2-混合语言是选型而非全用原则)
- [3. 语言分工矩阵与落地档位](#3-语言分工矩阵与落地档位)
- [4. 进程拓扑全景图（改进版）](#4-进程拓扑全景图改进版)
- [5. 进程清单与端口契约](#5-进程清单与端口契约)
- [6. IPC 契约定义](#6-ipc-契约定义)
- [7. 关键链路时序与延迟预算](#7-关键链路时序与延迟预算)
- [8. 显存预算与模型编排](#8-显存预算与模型编排)
- [9. 车控安全互锁（Safety Interlock）](#9-车控安全互锁safety-interlock)
- [10. 数据一致性与 Outbox 模式](#10-数据一致性与-outbox-模式)
- [11. 全双工 / AEC / 唤醒 / 打断](#11-全双工--aec--唤醒--打断)
- [12. 本地落地 Runbook（Win11 + RTX 4070）](#12-本地落地-runbookwin11--rtx-4070)
- [13. 目录结构与跨语言工程组织](#13-目录结构与跨语言工程组织)
- [14. 构建、依赖与环境管理](#14-构建依赖与环境管理)
- [15. 测试与评估体系](#15-测试与评估体系)
- [16. 分阶段落地路线（对齐 V2 计划）](#16-分阶段落地路线对齐-v2-计划)
- [17. 风险与回退（FMEA 摘要）](#17-风险与回退fmea-摘要)
- [附录 A：与 V2 计划的决策冲突点](#附录-a与-v2-计划的决策冲突点)

---

## 1. 设计目标与约束

### 1.1 目标层级（按重要性倒序删减依据）

| 优先级 | 目标 | 判据 |
|--------|------|------|
| P0 | 单机跑通端到端 | 一条语音指令从「按键/唤醒」到「车控执行 + 语音播报」可演示 |
| P0 | 架构贴近车载主流 | MCP / 端云协同 / SOA 服务化 / 流式 ASR / 全双工打断 均有对应模块 |
| P1 | 工程深度可展示 | 混合语言、IPC 契约、可观测、安全互锁、双库一致性均有实现 |
| P1 | 可本地落地 | `make up` 一条命令拉起全部服务，README 步骤可复现 |
| P2 | 性能指标 | 端到端 P95 ≤ 4s（关键词+BERT 路径）、首字延迟 ≤ 1.2s（留待迭代） |

### 1.2 硬约束（不可妥协）

1. **单卡 8/12GB 显存**：四个模型（ASR + 声纹 + 意图 BERT + 本地 LLM）无法同时常驻 FP16，需显存编排策略（见 §8）。
2. **Win11 宿主**：容器 GPU 直通依赖 WSL2 + Docker Desktop / NVIDIA Container Toolkit；不能假设原生 Linux。
3. **Demo 取向**：宁可在「真实车控」上做安全仿真（MockVehicleBus + 安全闸），也不要省略安全设计——展示价值高于跑通真实 CAN。
4. **不破坏现有 Python 代码骨架**：`SenseVoice_Agent_*.py`、`skills.py`、`orchestrator.py` 等保持可用，新语言组件作为「旁路/前置/后置」服务接入，通过 IPC 解耦。

---

## 2. 混合语言是选型而非全用（原则）

C++ / Go / Rust / Python 在本项目里是**架构选型池**——每个语言对应一类「Python 解决不好」的场景，**按需启用，默认不全量上**。判断标准只有两条：

1. **必须有**：该组件用 Python 会丢帧/不确定/无法对接厂商 SDK/撑不住并发 → 上对应语言。
2. **可选增强**：Python 能凑合但慢/重 → 列入选型，**默认用 Python 兜底，有空再切换**。

### 2.1 选型对照（按场景，非按语言硬塞）

| 场景 | 主流车载做法 | Python 局限 | 选用语言 | 档位（见 §3.2） |
|------|--------------|-------------|----------|---------------|
| 音频前端 / VAD / 唤醒 / 打断 | Rust（automotive-rs）/ C++ | GIL+GC 导致音频帧抖动丢帧 | **Rust** | 标准档起启用 |
| 车控总线 / 信号编解码 / 安全闸 | C/C++（Vector/ETAS）+ Rust | 实时报文 + 安全检查需确定性 | **Rust** | 标准档起启用 |
| 网关 / BFF / 服务发现 | Go（云原生车云连接器事实标准） | 万级 WS + TLS 终止不如 Go | **Go** | **完整档才启用**；标准档用 FastAPI 替代 |
| 推理引擎 / TensorRT EP / 厂商 SDK | C++（ONNX-RT/TRT/libtorch） | 自研算子/TRT EP 必须 C++ | **C++** | **完整档才启用**；标准档用 Python ONNX-RT 兜底 |
| Agent 编排 / RAG / 训练 / LLM 对接 | Python 生态独占 | — | **Python** | 所有档位必备 |
| 前端 HMI | TypeScript / Next.js | — | **TypeScript** | 标准档起启用（最小档用 Gradio 凑） |

### 2.2 选型纪律（避免"为用而用"）

- **禁**：把 Rust/C++ 用 ctypes 嵌进 Python 进程——破坏隔离、GIL 吃掉并发收益。
- **禁**：为了凑"四语言齐备"而上 Go 网关或 C++ 推理，而 Demo 并发/延迟没到瓶颈。
- **应**：跨语言一律走 §6 的 gRPC/MCP 契约，保证**任意语言组件可被 Python 兜底实现平滑替换**。
- **应**：性能不敏感的环节（意图路由、记忆 CRUD、RAG 检索编排）一律 Python，不引入多语言维护成本。

> 一句话：**Python 是骨架，Rust 是车端实时性的两块补丁（voiced/vebridged），Go 与 C++ 是「展示深度」的进阶可选件**——按档位渐进，不强求齐备。

---

## 3. 语言分工矩阵与落地档位

### 3.1 分工矩阵（语言 = 选型，标注档位与可替代实现）

| 组件 | 选用语言 | 进程名 | 职责 | 档位 | Python 兜底实现（不选该语言时） |
|------|----------|--------|------|------|--------------------------------|
| 音频前端守护 | **Rust** | `voiced` | 采集 → AEC → VAD → 唤醒 → 帧封装 → 推流 | 标准 | `sounddevice`+`webrtcvad` 线程版（现状 `Main.py` 即此，半双工） |
| 车控总线桥 + 安全闸 | **Rust** | `vebridged` | MCP 调用 → 安全校验 → CAN/DDS 仿真 → 回执 | 标准 | `vehicle_bus.py`+`mcp_gateway.py`（已有，无安全分级） |
| API 网关 / BFF（含 WS Hub、TLS、限流、JWT） | **Go** | `gatewayd` | 统一入口、追踪注入 | **完整** | **FastAPI + uvicorn**（标准档即用，限流用 `slowapi`） |
| 服务注册发现 (SOA 模拟) | **Go** | `registrar` | gRPC 注册/心跳/发现 | **完整** | 略；用环境变量静态配置 |
| 推理运行时守护 | **C++** | `inferd` | ONNX-RT(+TRT EP) 跑 ASR/声纹/TTS | **完整** | **Python `onnxruntime-gpu` 直接在 agentd/独立进程**（标档即用） |
| Agent 编排 + RAG + 记忆 + 微调 | **Python** | `agentd` | LangGraph 多 Agent、GraphRAG、意图、记忆、LLM 客户端 | **必备** | — |
| MCP 车控 Server | **Python** | `vehicle_mcp_server` | MCP JSON-RPC 工具暴露 → 调 `vebridged` | 标准 | 已有，保留 |
| 前端 HMI | **TypeScript** | `web` (Next.js) | 座舱 Dashboard | 标准 | Gradio `webui.py`（最小档） |

> **关键**：每一行都给了「不选该语言时的 Python 兜底实现」。即便只落地 Python + 两块 Rust 补丁，整条链路也能跑通——Go/C++ 是性能与展示深度的增量，不是阻塞项。

> **规则**：跨语言调用一律走 §6 的 gRPC/MCP 契约。禁止 ctypes 嵌入；唯一例外是 `inferd` 内部 C++ ↔ ONNX。

### 3.2 三档落地范围（按人力/时间裁剪）

```
┌─────────────┬───────────────────────────────────────────────────────────┐
│ 最小档        │ Python(agentd+vehicle_mcp_server) + Rust(voiced+vebridged)│
│ (1人/3-4天)   │ + Gradio前端 + Milvus/Neo4j + Redis + PostgreSQL           │
│  目标:跑通演示 │ 推理走 Python onnxruntime;网关=FastAPI直连;无Go无C++       │
│               │ → 能演示 全双工+安全闸+车控+记忆,展示价值已达标 80%        │
├─────────────┼───────────────────────────────────────────────────────────┤
│ 标准档 ★默认   │ 最小档 + Next.js 前端 + Prometheus/Grafana/Langfuse        │
│ (1-2人/5-7天) │ + 安全闸L0-L3 + Outbox一致性 + 流式ASR契约                 │
│  目标:可展示   │ 仍无Go网关、无C++推理;性能"够用",工程深度达标              │
├─────────────┼───────────────────────────────────────────────────────────┤
│ 完整档        │ 标准档 + Go(gatewayd+registrar) + C++(inferd+TensorRT EP)  │
│ (2人+/8-12天) │ + AEC/Barge-in 真实Rust版 + DDS仿真 + 全套监控             │
│  目标:面试硬核 │ 把性能与"贴近车载主流"拉满,四语言全到齐                    │
└─────────────┴───────────────────────────────────────────────────────────┘
```

> 本方案其余章节默认按「**标准档**」描述；凡涉及 Go/C++ 的内容会标注「完整档」。开发时按档位取用，不要一上来追求四语言齐备。

---

## 4. 进程拓扑全景图（改进版）

改进点：① 按「接入 / 智能编排 / 端侧实时 / 推理 / 车控 / 数据 / 横切」七层重排，边界清晰；
② 用 `[复用]` 标注同一组件承担多职责；③ `标准档=实线`、`完整档=虚线` 一眼看出哪些可选；
④ 删去 RabbitMQ/Celery（并入 Redis）。

```
┌──────────────────────────────────────────────────────────────────────────┐
│ L1 接入层  Access                                                          │
│   ┌───────────────┐         ┌──────────────────────┐                      │
│   │ web (Next.js) │─WSS────▶│ gatewayd [Go·完整档] │── 或标准档 FastAPI 直连│
│   │ +麦/扬声器     │  REST   │ TLS/JWT/限流/WS Hub  │                      │
│   └───────────────┘         └──────────┬───────────┘                      │
└──────────────────────────────────────────┼───────────────────────────────┘
                                           │ gRPC / WSS(音频+流式文本)
┌──────────────────────────────────────────▼───────────────────────────────┐
│ L2 智能编排层  Orchestration  (Python)                                     │
│   ┌─────────────────────────────────────────────────────────────────┐    │
│   │ agentd : LangGraph多Agent(Planner→Executor→Reviewer→Responder)   │    │
│   │         GraphRAG · 语义缓存命中 · 意图路由 · 记忆召回/冲突裁决      │    │
│   └──┬─────────────┬────────────────┬───────────────┬─────────────────┘    │
│      │ ASR流(gRPC) │ 车控(MCP/gRPC) │ TTS请求        │ RAG/记忆CRUD        │
└──────┼─────────────┼────────────────┼───────────────┼─────────────────────┘
       │             │                │               │
┌──────▼─────┐ ┌─────▼──────────┐ ┌───▼────────┐  ┌──▼──────────────────────┐
│ L3 端侧实时 │ │ L5 车控(实时)   │ │ L4 推理     │  │ L6 数据                  │
│  voiced     │ │  vebridged      │ │  inferd     │  │  Milvus(向量+RAG)        │
│  [Rust·标准]│ │  [Rust·标准]    │ │  [C++·完整] │  │  Neo4j(图谱/GraphRAG)    │
│  采集/AEC/  │ │  安全闸L0-L3    │ │  ASR/声纹/  │  │  PostgreSQL[复用]        │
│  VAD/唤醒/  │ │  +CAN/DDS仿真   │ │  TTS/TRT-EP │  │   =结构化+审计+Outbox    │
│  Barge-in   │ │  →Mock/HttpBus │ │  (标档:Py    │  │  Redis[复用×7] 见下      │
│  推ASR帧流  │ │  →回执→审计     │ │   onnxruntime│  │  MinIO[复用]=音频+权重   │
└──────┬──────┘ └────────┬───────┘ │   兜底)      │  └────────────────────────┘
       │  PCM帧上行        │ 回执     └─────┬──────┘
       └────────┐         │               │ 流式TTS下行
                ▼         │               ▼
          ┌──────────────────────────────────┐
          │ inferd 流式 ASR(gRPC bidi)        │  ◀── voiced 与 inferd 同机时
          │ AsrToken 下发 → agentd            │      可选走共享内存(§6.3)
          └──────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│ L7 横切层  Cross-cutting    (标准档=实线, 完整档=---)                      │
│  Redis[复用×7] : 语义缓存 │ 会话状态 │ 限流计数 │ 事件流(替代RabbitMQ)     │
│                  │ Celery替代(asyncio+Redis Streams) │ 任务队列 │ pub/sub   │
│  PostgreSQL[复用]: 结构化数据 │ 车控审计 │ Outbox表 │ 会话(可选)            │
│  MinIO[复用]    : TTS音频临时 │ 上传文档 │ 模型权重(大文件)                 │
│  监控 [复用栈]  : Langfuse(AI Trace) + Prometheus(指标) + Grafana(面板)    │
│                  Loki[可选] 日志聚合 (标档用文件日志+Grafana 关联 trace_id) │
│  推理后端 [切换]: vLLM(主,完整档) / Python onnxruntime(标档) / transformers(降级)│
└──────────────────────────────────────────────────────────────────────────┘
```

### 4.1 拓扑图图例

- **实线** = 标准档必选链路；**虚线 `---`** = 完整档增量。
- `[复用×N]` = 该组件承担 N 个职责，是降本关键（见 §4.2）。
- `[Rust·标准]` / `[Go·完整]` / `[C++·完整]` = 语言档位标注，对应 §3.2。
- 标准档下，`gatewayd(Go)` 与 `inferd(C++)` 退化为：网关=FastAPI 直连、推理=Python onnxruntime 进程，**链路不变、只换实现**——这正是 §2「可平滑替换」原则的体现。

### 4.2 复用矩阵（技术栈对照，复用换性能/工时）

> 原则：**一个组件能覆盖的职责不招第二个**，显式接受小幅性能损失换开发时长与运维成本。

| 组件 | 原计划(V2)职责 | 复用后承担 | 砍掉的组件 | 性能代价(可接受) |
|------|----------------|-----------|-----------|------------------|
| **Redis** | 语义缓存 + 会话 | +限流计数 +事件流(替代RabbitMQ) +任务队列(替代Celery broker) +pub/sub +在线用户 +Agent状态 | RabbitMQ、Celery broker | Streams 吞吐 < RabbitMQ 专用 MQ，但单机 Demo 够用 |
| **PostgreSQL** | 结构化(用户/会话/对话) | +车控审计日志 +Outbox 表 +系统配置(可选) | 独立审计服务、system_config 单库 | 审计写同库追加，吞吐有限但 Demo 足够 |
| **Milvus** | 向量记忆 + RAG 索引 | +语义缓存回退存储(Redis 未命中时降级检索) | 独立缓存向量库 | 多一次 ANN 查询，仅在缓存层失效时 |
| **FastAPI** (agentd) | Agent + RAG 逻辑 | +BFF 网关(标档) +WS Hub +健康检查 | gatewayd(Go,完整档)、Nginx(标档可省) | 单进程 TLS/限流不如 Go+Nginx，靠 slowapi+uvicorn workers 兜 |
| **MinIO** | 音频文件 | +模型权重存储 +上传 RAG 文档 | 多个文件目录 | 小文件性能弱于本地盘，但统一管理 |
| **监控栈** | Langfuse+Prometheus+Grafana+Loki | 标档只跑 Langfuse+Prometheus+Grafana;日志走文件+trace_id 关联 | Loki(标档省略) | 无集中日志聚合，靠 trace_id 在 Grafana 跳 Langfuse |
| **docker-compose** | 全服务编排 | +本地 GPU 直通 +健康检查 +依赖顺序 | K8s(不引) | 单机编排，不展示 K8s，但 Demo 够用 |

### 4.3 数据流要点（对应图）

- `voiced` 流式上行 PCM → `inferd` 流式 ASR → `agentd` 收 AsrToken（端到端首字延迟主路径）。
- `agentd` 车控请求 → `vehicle_mcp_server`(MCP) → `vebridged` 安全闸 → `MockVehicleBus/HttpAdapter` → 回执 → 异步写 `PostgreSQL.审计`（经 Outbox/Redis Streams）。
- `agentd` 后台记忆提取/冲突裁决 → 投 `Redis Streams` → memory worker → Outbox 消费 → Milvus+Neo4j 双写幂等（§10）。
- 全部跨进程调用携带 OTel `trace_id`，由网关注入（标档 FastAPI 中间件 / 完整档 gatewayd）。
- 服务发现：标准档用环境变量静态地址；完整档才上 `registrar`(Go) 模拟 SOA SD。

---

## 5. 进程清单与端口契约

单机端口规划（避开 80/443，全用高位端口，便于 Win11 + Docker 共存）：

| 进程 | 语言 | 监听端口 | 协议 | 健康检查 |
|------|------|----------|------|---------|
| `gatewayd` | Go | `:8443` (HTTPS/WSS), `:8081` (metrics) | HTTP/2, WS, gRPC | `GET /healthz` |
| `agentd` (FastAPI) | Python | `:8000` (REST/WS), `:8001` (gRPC) | HTTP/2, gRPC | `GET /api/health` |
| `voiced` | Rust | `:9001` (gRPC), `:9002` (WS-音频给前端) | gRPC bidi, WS | gRPC Health |
| `inferd` | C++ | `:9003` (gRPC) | gRPC bidi | gRPC Health |
| `vehicle_mcp_server` | Python | stdio / `:9004` (SSE/HTTP MCP) | JSON-RPC | `tools/list` |
| `vebridged` | Rust | `:9005` (gRPC), `:9006` (DDS-UDP 仿真) | gRPC, UDP | gRPC Health |
| `registrar` | Go | `:2379`-兼容 (gRPC) / `:8080` (HTTP-UI) | gRPC | `GET /health` |
| `web` (Next.js) | TS | `:3000` | HTTP/WS | `GET /` |
| Milvus | — | `:19530`, `:9091` | gRPC | `/healthz` |
| Neo4j | — | `:7687` (bolt), `:7474` (http) | bolt | `GET /` |
| PostgreSQL | — | `:5432` | pg | `pg_isready` |
| Redis | — | `:6379` | RESP | `PING` |
| RabbitMQ | — | `:5672` (amqp), `:15672` (mgmt) | amqp | mgmt UI |
| MinIO | — | `:9000` (s3), `:9001` (console) | S3 | `/minio/health/live` |
| Langfuse | — | `:3001` | HTTP | `GET /api/public/health` |
| Prometheus | — | `:9090` | HTTP | `/-/healthy` |
| Grafana | — | `:3030` | HTTP | `/api/health` |
| Loki | — | `:3100` | HTTP | `/ready` |

> 端口冲突预案：所有应用层端口集中在 8000-9100，基础设施用默认；冲突时由 `.env` 的 `*_PORT` 变量统一覆盖（见 §12 的 env 模板）。

---

## 6. IPC 契约定义

> 本节是「可直接写代码」的契约层。所有跨语言调用先在 `proto/` 落 protobuf，再生成各语言 stub。

### 6.1 gRPC 服务总览

| 服务 | 提供 | 消费 | 关键方法 |
|------|------|------|---------|
| `VoiceService` | voiced | agentd, web | `StreamASR(bidi)`, `StartSession`, `StopSession`, `BargeIn` |
| `InferenceService` | inferd | agentd, voiced | `ASR(stream)`, `SpeakerEmbed`, `TTS(stream)` |
| `VehicleControlService` | vebridged | agentd(经 mcp) | `Execute(cmd) -> result`, `GetStatus`, `SubscribeEvents` |
| `AgentService` | agentd | gatewayd | `Chat(stream)`, `RouteIntent`, `RecallMemory` |
| `RegistryService` | registrar | 全部 | `Register`, `Heartbeat`, `Discover` |

### 6.2 核心 proto 草案

```protobuf
// proto/voice.proto
syntax = "proto3";
package mrvo.voice.v1;

service VoiceService {
  rpc StartSession(SessionInit) returns (SessionHandle);
  rpc StreamASR(stream AudioFrame) returns (stream AsrToken);   // 双向流
  rpc BargeIn(BargeInRequest) returns (Ack);                    // 全双工打断
  rpc StopSession(SessionHandle) returns (Ack);
}

message AudioFrame {
  string session_id = 1;
  bytes  pcm = 2;            // 16kHz mono int16le
  uint32 sample_rate = 3;
  double timestamp_ms = 4;   // 单调时钟，用于 AEC/对齐
  bool   vad_active = 5;
}

message AsrToken {
  string session_id = 1;
  string text = 2;           // 增量文本
  bool   is_final = 3;       // 是否为该句终态
  double confidence = 4;
  double latency_ms = 5;
}
```

```protobuf
// proto/inference.proto
service InferenceService {
  rpc ASR(stream AudioChunk) returns (stream AsrResult);
  rpc SpeakerEmbed(AudioChunk) returns (Embedding);           // 1024d CAM++
  rpc TTS(TtsRequest) returns (stream AudioChunk);            // 流式 TTS
  rpc IntentClassify(Text) returns (Intent);                  // BERT (可选，通常在 agentd 内)
}

message Embedding { repeated float vec = 1; }
message TtsRequest {
  string text = 1;
  string voice_id = 2;        // 声纹克隆目标；空=默认音色
  float  speed = 3;
}
```

```protobuf
// proto/vehicle.proto
service VehicleControlService {
  rpc Execute(VehicleCommand) returns (CommandResult);
  rpc GetStatus(StatusQuery) returns (VehicleStatus);
  rpc SubscribeEvents(Empty) returns (stream VehicleEvent);   // DDS-仿真事件流
}

message VehicleCommand {
  string trace_id = 1;
  string actor_id = 2;        // 声纹用户
  string tool = 3;            // vehicle_climate / vehicle_window ...
  string op = 4;              // set_temp / open / close ...
  bytes  args_json = 5;       // 工具特定参数
  bool   dry_run = 6;         // 安全闸：仅校验不执行
  uint32 safety_level = 7;    // 0=普通 1=需确认 2=禁行(车速>阈值开窗等)
}

message CommandResult {
  bool   success = 1;
  string message = 2;
  bytes  data_json = 3;
  uint32 latency_ms = 4;
}
```

### 6.3 共享内存音频契约（voiced ↔ inferd 可选优化）

当 `voiced` 与 `inferd` 同机，为避免 16kHz×2 字节 PCM 走 gRPC 拷贝，可走命名共享内存 + 环形缓冲：

| 字段 | 布局 | 说明 |
|------|------|------|
| Header (64B) | `[magic(4)] [write_idx(4)] [read_idx(4)] [frame_size(4)] [ capacity_frames(4)] [sample_rate(4)] [reserved(40)]` | 原子读写索引 |
| Ring | `capacity_frames × frame_size` | frame_size 默认 320B (10ms@16kHz mono int16) |

> 落地优先级：**先用 gRPC 流式跑通**（简单、跨机可迁移）；仅当压测显示 PCM 拷贝是瓶颈再切共享内存。共享内存实现用 Rust `shared_memory` crate，inferd 侧用 `boost::interprocess`。

### 6.4 MCP 车控工具契约（保留并收敛）

`vehicle_mcp_server` 暴露的 MCP 工具 Schema 与 `vehicle.proto` 的 `VehicleCommand` 字段一一映射：

```json
{
  "name": "vehicle_window",
  "description": "控制车窗",
  "inputSchema": {
    "type": "object",
    "properties": {
      "op": {"type": "string", "enum": ["open","close","set"]},
      "position": {"type": "string", "enum": ["all","front_left","front_right","rear_left","rear_right"]},
      "percent": {"type": "integer", "minimum": 0, "maximum": 100}
    },
    "required": ["op"]
  },
  "_safety": {"level": 1, "denyIf": {"vehicle_speed_kmh_gt": 60, "op": "open"}}
}
```

> `_safety` 字段是本方案新增的声明式安全约束，由 `vebridged` 安全闸解释执行（见 §9）。MCP 调用链：agentd → vehicle_mcp_server(MCP) → vebridged(安全闸+执行) → MockVehicleBus。

### 6.5 消息总线契约

- **事件命名**：`mrvo.{domain}.{event}`，如 `mrvo.memory.conflict_detected`、`mrvo.vehicle.command_executed`、`mrvo.agent.turn_completed`。
- **载体**：CloudEvents 1.0 JSON（`source/type/subject/data`），便于 Loki/Langfuse 关联 trace_id。
- **总线选型**：V2 计划用 RabbitMQ。本方案建议 **Redis Streams** 作为默认（单机少一个重型中间件、与语义缓存共用实例），RabbitMQ 作为「展示消息中间件能力」的可选编排（见附录 A 冲突点）。

---

## 7. 关键链路时序与延迟预算

### 7.1 端到端时序（车控 + 播报，全双工链路）

```
t0  用户开口
     │ voiced: VAD 检出语音 (目标 <30ms)
t1  ─┼─ voiced: 推 ASR 帧流 ──▶ inferd 流式 ASR
t2  ─┼─ inferd: 首个 AsrToken 下发 (目标 首字<300ms after t1)
t3  ─┼─ agentd: 唤醒词命中 + 流式声纹识别 (CAM++ 在 inferd)
t4  ─┼─ agentd: 意图路由 (BERT/启发式 <50ms 路径；LLM FC ~800ms 路径)
t5  ─┼─ agentd: Planner→Executor 调 vehicle_mcp_server → vebridged 安全闸 → MockVehicleBus
t6  ─┼─ vebridged: 回执 CommandResult → agentd
t7  ─┼─ agentd: Responder 流式 LLM 生成首句
t8  ─┼─ agentd: 首句送 TTS(inferd) → voiced/前端播放  ★首字延迟目标 ≤1.2s (t8-t0)
t9  ─┼─ 后台: 记忆提取/冲突裁决(Celery异步) 不阻塞主链
```

### 7.2 各环节延迟预算（Demo 验收基线，P95）

| 环节 | 预算(P95) | 责任进程 | 超限自愈 |
|------|-----------|---------|---------|
| VAD → 推流 | 30ms | voiced | 丢帧计数告警 |
| ASR 首字 | 300ms | inferd | 切离线 SenseVoice → 降级兜底文本 |
| 声纹识别 | 200ms | inferd | 识别失败 → Guest 会话 |
| 意图路由(快路径) | 50ms | agentd | 关键词/BERT；LLM FC 超时 800ms 降级 |
| 车控安全闸+执行 | 80ms | vebridged | 安全拒绝 → 返回需确认 |
| LLM 首句生成 | 600ms | agentd | 云端熔断 → 本地 Qwen INT4 |
| TTS 首音频 | 250ms | inferd | CosyVoice 慢 → 降级 Edge-TTS/pyttsx3 |
| **端到端首字 P95 目标** | **≤1.2s** | — | 见 §17 |

> 现状 README 实测 7s+ 的根因（串行网络链路）通过：① ASR 流式化 ② 意图快路径 ③ 流式 TTS ④ 语义缓存 ⑤ 异步记忆处理 五项叠加消除。

---

## 8. 显存预算与模型编排

### 8.1 单卡 8GB 问题（核心约束）

四个候选常驻模型同卡 FP16 显存估算：

| 模型 | 精度 | 显存(约) | 用途 |
|------|------|----------|------|
| SenseVoice-Small | FP16 | ~0.9GB | ASR |
| CAM++ | FP32 | ~0.3GB | 声纹 |
| rbt3 (BERT 意图) | FP32 | ~0.1GB | 意图分类 |
| Qwen3-4B | FP16 | ~8GB | 本地 LLM（隐私模式） |

→ 4B FP16 单独就占满 8GB。**不能全量常驻**。

### 8.2 编排策略（分两层）

**层 1：常驻集（开机即加载，~1.4GB）**
SenseVoice(FP16) + CAM++ + BERT 意图。这三者首字延迟敏感，常驻。

**层 2：按需加载（swap-in/swap-out，8GB 卡的主策略）**
- 本地 Qwen3-4B 以 **AWQ-INT4** 量化（~2.5GB），仅在「隐私模式」或「云端熔断降级」时加载，用完 `unload()`（`privacy_llm.py` 已有 `unload` 接口）。
- 推理服务用 **vLLM**（PagedAttention，高吞吐）或 **SGLang**（多轮快）。`inferd` 通过 vLLM 的 OpenAI 兼容 API 转发，而非直接 transformers.generate（现状 `privacy_llm.py` 用 transformers，吞吐低）。

**层 3：12GB 卡（如 4070 Ti/12G）**
可在常驻集基础上 + Qwen3-4B-INT4 常驻，免 swap，延迟更稳。`.env` 的 `GPU_VRAM_BUDGET_GB` 决定走层 2 还是层 3。

### 8.3 量化与导出链路（C++ 推理对齐）

| 模型 | 导出 | 运行时 |
|------|------|--------|
| SenseVoice | ONNX → TensorRT | inferd (ORT + TensorRT EP) |
| CAM++ | ONNX | inferd (ORT CPU/CUDA) |
| 意图 BERT | ONNX | inferd 或 agentd 内 transformers |
| Qwen3-4B | AWQ-INT4 | vLLM（Python 守护，inferd 转发） |
| CosyVoice TTS | ONNX（可选） | inferd；否则 Python CosyVoice 原生 |

> 主路径 ASR/声纹走 C++ `inferd`（展示性能调优）；LLM 走 vLLM（展示高吞吐部署）。两者清晰分工，不强行把 LLM 也塞进 C++。

---

## 9. 车控安全互锁（Safety Interlock）

V2 计划把所有车控指令一视同仁，缺少车载行业必须的「安全栅」。本方案补齐。

### 9.1 指令安全分级

| 级别 | 含义 | 处理 | 示例 |
|------|------|------|------|
| L0 普通查询 | 只读 | 直接执行 | 查询剩余油量、车窗当前开度 |
| L1 普通控制 | 无副作用危险 | 直接执行 | 空调温度调节、媒体播放 |
| L2 需确认 | 有环境依赖风险 | 返回 `need_confirm`，需用户二次确认或前置条件满足 | 车速 >60km/h 时开窗、挂D挡时开后备箱 |
| L3 禁行 | 硬实时安全红线 | 直接拒绝 + 审计 | 行驶中解锁车门、熄火 |

### 9.2 安全闸执行点（vebridged，Rust）

```
VehicleCommand ──▶ [1] 黑白名单(tool) ──▶ [2] 参数Schema校验
       │                                     │
       │                              [3] 安全规则求值(_safety.denyIf)
       │                                     │
       │              ┌──────────────────────┤
       │              ▼                      ▼
       │        deny → L3 reject       allow → dry_run? 
       │                                     │
       │                              yes→返回"将通过" ; no→执行
       │                                     ▼
       └─────────────────────────────  MockVehicleBus / HttpAdapter
                                              │
                                              ▼
                                  [4] 审计写入 PostgreSQL + CloudEvent
```

### 9.3 车辆状态来源

`_safety.denyIf` 依赖的车辆状态（车速、挡位、车门）由 `vebridged` 维护：
- Mock 模式：`vehicle_bus.MockVehicleBus` 内部状态机（可被前端滑块/脚本注入场景）。
- Http 模式：周期拉取或 DDS 事件订阅（`SubscribeEvents`）。

### 9.4 决策入口：MCP 直连 vs 经 vehicle_mcp_server

两种调用路径并存，由 `VEHICLE_ADAPTER` 与 `VEHICLE_GATEWAY` 环境变量选择：
- `mcp-stdio`（现状）：agentd → vehicle_mcp_server(MCP) → vebridged(gRPC)。
- `grpc-direct`（新增，低延迟路径）：agentd → vebridged(gRPC)，跳过 MCP 序列化。

> 展示时默认走 MCP（体现协议能力）；压测/低延迟演示时切 grpc-direct。两者共用同一套安全闸。

---

## 10. 数据一致性与 Outbox 模式

V2 计划承认 Milvus ↔ Neo4j 双写无事务，存在孤儿关系。这是 P0 数据正确性缺口。

### 10.1 Outbox + CDC 方案

```
agentd(Responder后台)
   │ 1. 业务事务：PostgreSQL 写 conversations + outbox 表 (同一本地事务)
   ▼
PostgreSQL.outbox ──▶ 2. Debezium/轮询worker 读 outbox
                            │ 3. 投递 CloudEvent 到 Redis Streams
                            ▼
                  ┌─────────────────────────┐
                  │ memory_consumer worker   │
                  │  按 mid 幂等处理：        │
                  │  - Milvus insert/delete  │
                  │  - Neo4j upsert/delete   │
                  │  - 失败重试 → DLQ        │
                  └─────────────────────────┘
```

- **本地事务保证** conversations 与 outbox 同生共死（PostgreSQL 事务）。
- **最终一致** Milvus + Neo4j 通过消费者幂等 + 重试 + DLQ 达到一致；冲突裁决在新记忆入 outbox 前由 agentd 完成。
- **删除联动**：`delete_memory_by_ids` 与 `delete_relation_by_mid` 由同一消费者的同一 handler 顺序执行，失败整体回滚标记 `outbox.status=retry`。

### 10.2 衡量指标

- `dual_write_inconsistency_count`（Gauge）= Milvus 有但 Neo4j 无的 mid 数（定时对账 worker 计算）。
- 目标：0。Demo 展示「数据一致性」时直接展示该指标曲线。

---

## 11. 全双工 / AEC / 唤醒 / 打断

现状是半双工（`is_speaking`/`is_processing` 互斥，丢弃 TTS 期间的音频）。主流车载是全双工 + 打断。本方案由 `voiced`(Rust) 补齐。

### 11.1 能力清单

| 能力 | 实现 | 缓解现状缺陷 |
|------|------|-------------|
| AEC（回声消除） | voiced 内 WebRTC AEC3（Rust 绑定 `webrtc-audio-processing`）；无参考信号时降级为「TTS 播放时静音采集」 | 半双工丢词 |
| 唤醒词 | 拼音匹配（现状）+ 可选 Porcelain/Sherpa-onnx 唤醒模型 | 仅靠拼音易误唤醒 |
| Barge-in 打断 | TTS 播放中检测到用户语音 → `BargeIn` RPC → 立即停止 TTS、清空 TTS 队列、重置 Responder | 用户无法打断 |
| 多音区（可选） | 多通道采集 + DOA，输出 `speaker_zone`；Mock 阶段单通道 | 展示前瞻性 |

### 11.2 Barge-in 时序

```
TTS 播放中 ── voiced 检测到人声(非回声) ──▶ voiced 发 BargeIn(session_id)
                                              │
                          agentd: cancel Responder token + tts_text_queue.clear()
                                              │
                          inferd: 停止当前 TTS 流 (gRPC cancel)
                                              │
                          voiced/前端: 渐隐停止播放，立即进入新一轮 listening
```

---

## 12. 本地落地 Runbook（Win11 + RTX 4070）

### 12.1 宿主准备

```powershell
# 1. WSL2 + Ubuntu 22.04 (推荐，容器跑在 WSL2 内，GPU 直通更稳)
wsl --install -d Ubuntu-22.04

# 2. Docker Desktop → Settings: 启用 WSL2 引擎 + 资源限制 (CPU8/RAM16G/Swap4G)
#    Resources → WSL Integration → 勾选 Ubuntu-22.04

# 3. NVIDIA 驱动 (>=550) + 在 WSL2 内验证 GPU 可见
nvidia-smi   # WSL2 内应列出 RTX 4070

# 4. NVIDIA Container Toolkit (WSL2 内)
#    Docker Desktop 已内置 GPU 支持，验证：
docker run --rm --gpus all nvcr.io/nvidia/k8s/cuda-sample:nbody nbody -benchmark
```

> **原生 Win11 Docker Desktop 也可用**，但 WSL2 路径对 CUDA 容器兼容性更好，是首选。

### 12.2 一键启动

```bash
# 仓库根
cp .env.example .env   # 填 ARK_API_KEY / TAVILY_API_KEY / 各密码
make build             # 构建各语言镜像 (rust/go/c++/python/web)
make up                # docker compose up -d
make ps                # 查看全部服务健康
make seed              # 灌入 RAG 示例文档 + 注册默认声纹
```

### 12.3 验证清单（按序勾选）

- [ ] `make health` —— 全部服务 `healthy`（含 voiced/inferd/vebridged/gatewayd/agentd）
- [ ] `web` http://localhost:3000 可打开座舱 HMI
- [ ] 「云端模式」文本输入「把空调调到 24 度」→ 前端出现车控回执 + 语音播报
- [ ] 「隐私模式」切换 → local Qwen3-4B-INT4 被 swap 进显存（`nvidia-smi` 可见），对话后 swap 出
- [ ] Barge-in：播报过程中说话 → 播报立即停止
- [ ] 安全闸：注入 `vehicle_speed=80` 场景后说「打开车窗」→ 返回 L2 `need_confirm`
- [ ] Langfuse http://localhost:3001 看到完整 Trace 链（Span 树含 voiced/inferd/vebridged）
- [ ] Grafana http://localhost:3030 「M-RAG-Voice」面板 P95 延迟曲线
- [ ] `dual_write_inconsistency_count` = 0

### 12.4 关键 .env 增量（V2 计划之外）

```env
# ===== 混合语言服务 =====
VOICED_GRPC_PORT=9001
INFERD_GRPC_PORT=9003
VEBRIDGED_GRPC_PORT=9005
GATEWAYD_HTTPS_PORT=8443
VEHICLE_GATEWAY=mcp-stdio        # mcp-stdio | grpc-direct

# ===== 推理后端 =====
INFER_BACKEND=onnxrt             # onnxrt | vllm | transformers
VLLM_BASE_URL=http://localhost:8010/v1
LOCAL_LLM_QUANT=awq-int4
GPU_VRAM_BUDGET_GB=8             # 8 | 12 决定 swap 策略

# ===== 全双工 =====
AEC_MODE=webrtc                  # webrtc | mute-during-tts | off
BARGE_IN_ENABLED=true
WAKEWORD_ENGINE=pinyin           # pinyin | sherpa

# ===== 安全闸 =====
VEHICLE_SAFETY_ENABLED=true
VEHICLE_STATE_SOURCE=mock        # mock | http | dds

# ===== 一致性 =====
OUTBOX_ENABLED=true
DUAL_WRITE_RECONCILE_INTERVAL_S=60
```

### 12.5 显存自查命令

```bash
docker exec agentd python -c "import torch;print(torch.cuda.memory_allocated()/2**30,'GB used')"
docker exec inferd ./inferdctl stats    # 各模型占用
nvidia-smi --query-gpu=memory.used --format=csv -l 2
```

---

## 13. 目录结构与跨语言工程组织

在 V2 计划的目录基础上，新增 `services/` 多语言区与 `proto/`：

```
Agent_ASR-master/
├── proto/                         # ★ 契约源（单一事实来源）
│   ├── voice.proto
│   ├── inference.proto
│   ├── vehicle.proto
│   ├── registry.proto
│   └── buf.yaml                   # buf 管理与 lint
├── services/                      # ★ 跨语言服务
│   ├── voiced/                    # Rust  (Cargo.toml, src/)
│   │   └── Cargo.toml
│   ├── vebridged/                 # Rust
│   ├── gatewayd/                  # Go   (go.mod, cmd/)
│   ├── registrar/                 # Go
│   └── inferd/                    # C++  (CMakeLists.txt, src/)
├── agent/                         # Python 多 Agent (V2 计划已有)
├── middleware/                    # Python 中间件 (V2 已有)
├── core/                          # Python 核心 (V2 已有)
├── rag/                           # Python RAG (V2 已有)
├── api/                           # Python FastAPI 路由 (V2 已有)
├── web/                           # Next.js (V2 已有)
├── infra/                         # ★ 部署与编排
│   ├── docker/
│   │   ├── Dockerfile.voiced
│   │   ├── Dockerfile.vebridged
│   │   ├── Dockerfile.gatewayd
│   │   ├── Dockerfile.inferd
│   │   ├── Dockerfile.agentd
│   │   └── Dockerfile.web
│   ├── docker-compose.yml
│   ├── docker-compose.gpu.yml     # GPU profile
│   ├── nginx/nginx.conf
│   └── monitoring/ (prometheus/grafana/loki/alertmanager)
├── tests/                         # ★ 跨语言测试
│   ├── contract/                  # gRPC 契约测试(pact/grpcurl)
│   ├── e2e/
│   ├── load/ (locust/k6)
│   └── safety/                    # 安全闸用例
├── scripts/                       # ★ 工具
│   ├── gen_proto.sh               # 一键生成各语言 stub
│   └── bench_e2e.py
├── Makefile
└── .env.example
```

**生成 stub**：`make proto` → 用 `buf` 生成 Python/Rust/Go/C++ 四份 stub 到各自 `services/*/gen/`。

---

## 14. 构建、依赖与环境管理

| 语言 | 构建工具 | 关键依赖 | 镜像基址 |
|------|---------|---------|---------|
| Rust | cargo | `tonic`(gRPC), `webrtc-audio-processing`, `shared_memory`, `parking_lot` | `rust:1.83-slim` (多阶段→distroless) |
| Go | go modules | `grpc-go`, `cobra`, `prometheus/client`, `nhooyr/websocket` | `golang:1.23` (多阶段→scratch/distroless) |
| C++ | CMake + vcpkg | ONNX Runtime, TensorRT, protobuf, gRPC, boost | `nvidia/cuda:12.x-devel-ubuntu22.04` |
| Python | uv/poetry | 见 requirements 拆分 (见下) | `python:3.10-slim` + GPU |
| TS | pnpm | Next14, Tailwind, shadcn, zustand, @tanstack/query | `node:20` |

**Python 依赖分层**（现状单 `requirements.txt` 已 6KB，建议拆分以减镜像体积）：

```
requirements/
├── base.txt        # 通用
├── agent.txt       # langchain/langgraph/openai
├── infer.txt       # torch/funasr/transformers/onnxruntime-gpu
├── web.txt         # fastapi/uvicorn/gradio
└── dev.txt         # pytest/ruff/mypy/pyinstrument
```

> `inferd` 容器只需 `infer.txt` 的 C++ 对等部分（ONNX/TensorRT），不含 Python AI 栈，体积小、启动快。

---

## 15. 测试与评估体系

V2 计划仅提「回归测试 + 压测」，缺契约测试与离线评估。补齐四层：

### 15.1 测试金字塔

| 层 | 工具 | 覆盖 | 门禁 |
|----|------|------|------|
| 单元 | pytest(rust:cargo test / go:go test / c++:gtest) | 各服务内部逻辑 | PR 必过 |
| 契约 | grpcurl + pact | proto 兼容性、字段非空 | CI 必过 |
| 集成 | docker-compose.test.yml | 单链路冒烟（ASR→意图→车控→TTS） | 每日 |
| E2E | Playwright(web) + 音频 fixture | 座舱 HMI 全流程 | 发版前 |
| 负载 | k6(WS) / locust(HTTP) | 并发会话、首字 P95 | 性能门禁 |
| 混沌 | `toxiproxy` 注入延迟/断网 | 熔断/降级验证 | 每周 |
| 安全 | 自写 safety/ 用例表 | L2/L3 拒绝矩阵 | 每次改安全闸 |

### 15.2 离线评估套件（`scripts/bench_e2e.py`）

| 评估项 | 指标 | 数据集 |
|--------|------|--------|
| 意图分类 | Macro-F1 / 每类 P/R | 自建 200 条车控+闲聊 |
| 槽位提取 | Exact-match 率 | 同上 |
| 检索召回 | Recall@5 / nDCG@5 | 50 条 query + 知识库 |
| 记忆冲突裁决 | 四类裁决准确率 | README 中 4 场景 + 扩 20 条 |
| 端到端延迟 | P50/P95/P99 首字&完整 | 100 轮音频 fixture |
| 安全闸 | L2/L3 拒绝率 / 误拒率 | 30 条边界场景 |

> 评估结果以 JSON 入 `evals/runs/<date>/`，并推 Prometheus 一个 `eval_*` gauge，Grafana 可见。这是「展示个人技术能力」时最有说服力的量化材料。

### 15.3 安全闸用例矩阵（节选）

| 场景 | 注入状态 | 指令 | 期望 |
|------|---------|------|------|
| 静止开窗 | speed=0 | open_window | L1 执行 |
| 高速开窗 | speed=80 | open_window | L2 need_confirm |
| 行驶解锁 | speed=40 | unlock_door | L3 reject |
| dry_run | speed=80 | open_window(dry_run=true) | 返回「将通过L2」但不执行 |

---

## 16. 分阶段落地路线（对齐 V2 计划）

在 V2 计划 Phase1-7 上插入混合语言与落地工程节点；★ 为本方案新增：

```
Phase 0 ★ 契约先行 (0.5d)
  └─ proto/ 四个 .proto + buf + make proto 生成 stub
     （先有契约，再写各语言实现，避免接口漂移）

Phase 1 基础设施 (1.5d)  [V2 Phase1]
  ├─ docker-compose.yml 全服务骨架（先起空壳）
  ├─ config.py → Pydantic Settings + .env 增量
  └─ PostgreSQL/Redis/MinIO/Milvus/Neo4j 起 healthy

Phase 2 ★ Rust 实时层 (2d)
  ├─ voiced: 采集/VAD/唤醒/推流（先不含AEC）
  ├─ vebridged: 安全闸 + MockVehicleBus + gRPC
  └─ 与 agentd 联调 ASR 流式 + 车控安全

Phase 3 ★ C++/Go 服务层 (2d)
  ├─ inferd: ONNX Runtime 跑 SenseVoice + CAM++ (先无TensorRT)
  ├─ gatewayd: TLS+JWT+限流+WS Hub
  └─ registrar: 服务注册发现（可选后置）

Phase 4 Agent 深化 (2-3d) [V2 Phase3]
  ├─ 多 Agent (Planner/Executor/Reviewer/Responder)
  ├─ GraphRAG + Reranker + 语义缓存
  └─ Outbox 一致性改造（替换裸双写）

Phase 5 API+前端 (3-4d) [V2 Phase4-5]
  ├─ api/ 模块化 + 依赖注入
  └─ web Next.js 全页面 + WS

Phase 6 可观测+安全 (1.5d) [V2 Phase2+6]
  ├─ OTel trace 贯穿四语言
  ├─ Prometheus/Grafana/Loki + Langfuse
  └─ 安全闸用例 + 审计落库

Phase 7 ★ 全双工增强 (1d)
  └─ AEC + Barge-in + 声纹流式

Phase 8 评估+发版 (1.5d) [V2 Phase7]
  ├─ bench_e2e 套件跑通
  ├─ 压测/混沌
  └─ 文档定稿 + 录制 Demo
```

**最小可演示子集（若时间紧，砍到这条线仍能展示核心）**：
`gatewayd(Go) + agentd(Python) + voiced(Rust,无AEC) + vebridged(Rust,Mock) + inferd(skip C++,直接Python推理,作为降级) + web(Next.js) + Milvus + Neo4j`。
即：Rust 两件 + Go 一件落地，C++ 可先用 Python 推理占位（通过 `INFER_BACKEND=transformers`），后续替换。

---

## 17. 风险与回退（FMEA 摘要）

| 失效模式 | 影响 | 检测 | 回退 |
|----------|------|------|------|
| 云端 LLM API 故障 | 主对话不可用 | 熔断器 OPEN | 本地 Qwen3-4B-INT4 swap-in |
| 显存 OOM | inferd 崩溃 | nvidia-smi 阈值告警 | unload 非必备模型，降级 Edge-TTS |
| voiceds 丢帧 | ASR 部分丢词 | 丢帧计数 | 帧计数告警；不影响其余链路 |
| Milvus/Neo4j 不一致 | 记忆错误 | 对账 gauge>0 | outbox 重放 + DLQ 人工 |
| vebridged 安全规则误拒 | 车控不可用 | 拒绝率突增告警 | 自动转 dry_run 模式 + 告警，不静默放行 |
| 唤醒误触发 | 隐私泄露/误执行 | 唤醒率指标 | 降级为按键唤醒 |
| 单机资源不足(全部容器) | 整体卡顿 | loadavg/mem 告警 | 裁剪到「最小子集」停 RabbitMQ/Loki/vLLM |
| WSL2 GPU 直通失败 | 推理退回 CPU | nvidia-smi 为空 | 原生 Windows CUDA；或全云端推理 |

---

## 附录 A：与 V2 计划的决策冲突点

| 冲突点 | V2 计划 | 本方案决策 | 理由 |
|--------|---------|-----------|------|
| Agent 间通信 | LangGraph(进程内) + RabbitMQ(事件总线) 双轨 | **LangGraph 管单轮内 DAG；Redis Streams 管跨进程异步**。RabbitMQ 降为可选展示件 | 单机 Demo 双重型中间件(RabbitMQ+Redis)收益<复杂度；Redis Streams 已够；RabbitMQ 仅在「展示消息中间件」专题启用 |
| 推理后端 | transformers(`privacy_llm.py` 现状) | **vLLM/SGLang + INT4**；transformers 仅作降级 | transformers 单条 generate 吞吐低，无法展示部署工程能力 |
| ASR 模式 | 「新增流式ASR」未细化 | **voiced(Rust) 推流 + inferd 流式 ASR(gRPC bidi)** | 明确进程与协议 |
| 车控调用 | 经 MCP-stdio 单路径 | **MCP 默认 + gRPC 直连可选**，共用安全闸 | 兼顾协议展示与低延迟 |
| 双写一致性 | 承认无事务，靠 flush/重试 | **Outbox + 消费者幂等 + 对账 gauge** | 把「已知问题」做成「已解决能力点」 |
| 车控安全 | 不分级，统一审计 | **L0-L3 分级 + 声明式 `_safety.denyIf`** | 车载行业必备，展示价值高 |
| 全双工 | 半双工互斥 | **AEC + Barge-in**(voiced) | 主流车载标配 |
| 消息总线 | RabbitMQ | **Redis Streams 默认；RabbitMQ 可选** | 见上 |
| 语言 | 纯 Python | **选型池 + 三档落地**：Python 骨架必备；Rust(voiced/vebridged) 标准档起；Go(gatewayd/registrar)/C++(inferd) 完整档才上，标档用 FastAPI/Python onnxruntime 兜底 | 语言是选型非全量用，按场景择优，每语言组件均有 Python 兜底，不强求四语言齐备 |
| **技术栈复用** | 一组件一职责（RabbitMQ+Celery+Nginx+独立审计+Loki 各司其职） | **一物多用换工时/成本**：Redis×7 兼 RabbitMQ+Celery；PostgreSQL 兼审计+Outbox+结构化；FastAPI 标档兼网关；MinIO 兼音频+权重 | 显式接受小幅性能损失换开发时长与运维成本，单机 Demo 性能非瓶颈 |
| **网关/网关中间件** | Nginx + gatewayd(Go) | 标档 **FastAPI + slowapi 直连**（无 Nginx 无 Go）；完整档才上 Nginx+Go | 单机 Demo 无需生产级网关；省两个组件 |
| **消息/异步** | RabbitMQ(事件) + Celery(任务) | **Redis Streams 兼事件+任务**；Celery 用 Redis 作 broker 仍可保留(可选) | 少一个重型中间件；Streams 吞吐够 Demo |

> 当本方案与 V2 计划冲突时，**以本方案附录 A 为准**；其余未冲突部分（前端设计、PostgreSQL 表、监控指标、云服务清单、技术栈对照表）继续沿用 V2 计划。
