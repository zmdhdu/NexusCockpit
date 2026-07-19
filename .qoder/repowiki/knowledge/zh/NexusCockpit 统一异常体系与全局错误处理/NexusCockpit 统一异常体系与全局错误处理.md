---
kind: error_handling
name: NexusCockpit 统一异常体系与全局错误处理
category: error_handling
scope:
    - '**'
source_files:
    - backend_design/nexus/core/exceptions.py
    - backend_design/nexus/main.py
    - backend_design/nexus/middleware/rate_limiter.py
    - backend_design/nexus/core/circuit_breaker.py
    - backend_design/nexus/core/auth.py
    - backend_design/nexus/rag/vector_store.py
    - backend_design/nexus/rag/graph_store.py
    - backend_design/nexus/rag/embedding.py
---

## 1. 采用的系统/方法
- Python 后端基于 FastAPI，采用**自定义异常类 + 全局异常处理器**的统一错误模型。
- 所有业务异常均继承自 `NexusError`，每个异常携带 `code`（字符串错误码）和 `details`（上下文字典），由全局处理器统一映射为 JSON `{error, message, details}` 响应体。
- Go 网关层通过独立日志文件输出错误，未复用 Python 异常体系。前端无集中错误拦截逻辑，主要依赖 HTTP 状态码与返回体中的 `error` 字段做展示判断。

## 2. 核心文件与包
- 异常定义：`backend_design/nexus/core/exceptions.py`
- 全局异常处理器注册：`backend_design/nexus/main.py`（`@app.exception_handler`）
- 限流中间件抛出限流异常：`backend_design/nexus/middleware/rate_limiter.py`
- 熔断器组件抛出熔断异常：`backend_design/nexus/core/circuit_breaker.py`
- 认证模块抛出认证异常：`backend_design/nexus/core/auth.py`
- RAG/存储层抛出领域异常：`backend_design/nexus/rag/vector_store.py`、`backend_design/nexus/rag/graph_store.py`、`backend_design/nexus/rag/embedding.py`

## 3. 架构与约定
- **异常层次结构**：`NexusError` 为根，派生出 `ConfigError`、`LLMError`、`RAGError`、`VectorStoreError`、`GraphStoreError`、`MemoryError`、`SkillError`、`IntentError`、`VehicleError`、`CacheError`、`AuthError`、`RateLimitError`、`CircuitBreakerError` 等按领域划分的子类，每个子类固定一个 `code` 值（如 `LLM_ERROR`、`RATE_LIMIT_ERROR`）。
- **全局映射规则**（在 `main.py` 中注册）：
  - `RateLimitError` → HTTP 429，并附带 `Retry-After: 60` 头；
  - `AuthError` → HTTP 401，附带 `WWW-Authenticate: Bearer` 头；
  - 其他 `NexusError` 子类 → HTTP 500。
- **降级策略**：限流检查失败时直接放行（`return True`），避免 Redis 故障导致服务不可用；向量/图谱连接失败仅记录警告，不阻止应用启动，后续请求再重试或走降级路径。
- **可观测性**：所有异常在处理器中通过结构化 logger 记录 `code` 与 `message`，便于 Prometheus/Grafana/Loki 采集分析。

## 4. 开发者应遵循的规则
- **抛错规范**：业务层遇到可预期错误时，必须 raise 对应领域的 `*Error` 子类，不要直接 raise 裸 `Exception` 或返回错误码字符串。
- **错误码一致性**：新增异常需同时完成三件事——定义子类、赋予唯一 `code`、在文档/测试中覆盖该 code 的语义。
- **禁止吞异常**：不要在业务函数内 `except Exception` 后静默 return，如需降级应在调用方（如中间件、lifespan）显式处理并记录日志。
- **WebSocket 场景**：当前 WebSocket 路由仅对 `AuthError` 做了 import，尚未注册专用 WS 异常处理器；若扩展需在 `websocket.py` 中补充对应的 `send_error` 封装。
- **Go 网关侧**：错误以结构化日志落盘（`logs/go_logs/gateway_*.log`），如需与 Python 端对齐，可在 gateway handlers 中统一返回 JSON error 结构并在 Nginx 层透传状态码。