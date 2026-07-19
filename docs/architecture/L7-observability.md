# L7 可观测层 (Observability)

> 对应代码: `nexus/observability/`

## 职责

提供全链路可观测性：
- **追踪 (Tracing)** — Langfuse 记录 LLM 调用链
- **指标 (Metrics)** — Prometheus 采集业务指标
- **面板 (Dashboard)** — Grafana 可视化
- **日志 (Logging)** — structlog 结构化日志

## 追踪 (langfuse.py)

```python
from nexus.observability.langfuse import LangfuseMonitor, trace_llm, trace_agent

# API 层创建 trace (在 chat.py 中)
monitor = LangfuseMonitor()
trace = monitor.start_trace(user_id="u1", input_text="打开空调")
span = monitor.start_span(trace_id=trace.id, name="supervisor")
monitor.end_observation(span, output=result)
monitor.end_trace(trace, output=response)

# Agent 层装饰器追踪
@trace_agent(name="supervisor")
async def supervise(input: str):
    ...

@trace_llm(name="chat_completion")
async def call_llm(prompt: str):
    ...
```

### 追踪范围

| 追踪点 | 说明 |
|--------|------|
| API 入口 | chat.py 创建顶层 trace，贯穿整个请求生命周期 |
| Agent 节点 | Supervisor / Experts / Responder / Reflection / Reviewer |
| LLM 调用 | 每次 LLM API 调用的输入/输出/延迟 |
| RAG 检索 | 向量搜索 + 图谱查询 |
| 技能执行 | 每个技能的执行结果 |
| 缓存 | 命中/未命中 |

### 配置

| 环境变量 | 说明 |
|----------|------|
| `LANGFUSE_PUBLIC_KEY` | Langfuse 公钥 |
| `LANGFUSE_SECRET_KEY` | Langfuse 密钥 |
| `LANGFUSE_HOST` | Langfuse 服务地址 |

> 未配置 Key 时，追踪自动关闭。

## 指标 (metrics.py)

```python
from nexus.observability.metrics import (
    record_request,
    record_cache_hit,
    record_llm_call,
    record_agent_latency,
)

# 在业务代码中记录
record_request(user_id="u1", intent="climate")
record_cache_hit(hit=True)
record_llm_call(model="deepseek-v3", latency_ms=350)
record_agent_latency(node="supervisor", latency_ms=120)
```

### 指标清单

| 指标 | 类型 | 说明 |
|------|------|------|
| `nexus_requests_total` | Counter | 请求总数 (按 intent 分) |
| `nexus_cache_hits_total` | Counter | 缓存命中次数 |
| `nexus_cache_misses_total` | Counter | 缓存未命中次数 |
| `nexus_llm_calls_total` | Counter | LLM 调用次数 |
| `nexus_llm_latency_ms` | Histogram | LLM 调用延迟 |
| `nexus_agent_latency_ms` | Histogram | Agent 节点延迟 |
| `nexus_vehicle_commands_total` | Counter | 车控命令次数 |
| `nexus_errors_total` | Counter | 错误总数 |

## 面板 (Grafana)

### 访问

```
http://localhost:3001  (admin/admin)
```

### 预置面板

| 面板 | 说明 |
|------|------|
| Overview | 请求量、错误率、平均延迟 |
| Agent Performance | 各 Agent 节点延迟分布 |
| Cache Performance | 缓存命中率、缓存大小 |
| LLM Metrics | LLM 调用次数、延迟、Token 消耗 |
| Vehicle Commands | 车控命令统计 |

## 日志 (core/logger.py)

```python
logger.info("chat_request",
    user_id="u1",
    text="把空调调到24度",
    intent="climate",
    trace_id="abc-123",
)
```

### 日志格式

```json
{
    "timestamp": "2026-07-07T12:00:00Z",
    "level": "info",
    "event": "chat_request",
    "user_id": "u1",
    "intent": "climate",
    "trace_id": "abc-123"
}
```

## 设计原则

1. **非侵入** — 追踪和指标通过装饰器实现，不侵入业务代码
2. **可降级** — Langfuse/Prometheus 不可用时，自动降级
3. **统一 trace_id** — 从 API 入口生成 trace_id，贯穿全链路
4. **指标即文档** — 指标名称自解释，便于查询
