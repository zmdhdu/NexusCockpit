---
kind: error_handling
name: NexusCockpit 错误处理体系：分层异常与全局映射
category: error_handling
scope:
    - '**'
source_files:
    - backend_design/nexus/core/exceptions.py
    - backend_design/nexus/main.py
    - backend_design/nexus/core/auth.py
    - backend_design/nexus/middleware/rate_limiter.py
    - backend_design/nexus/core/circuit_breaker.py
    - backend_design/nexus/rag/embedding.py
    - backend_design/nexus/rag/graph_store.py
    - backend_design/nexus/rag/vector_store.py
    - backend_design/nexus_gate/internal/handlers/handlers.go
    - backend_design/nexus_gate/internal/auth/jwt.go
---

## 1. 采用的系统/方法

- **Python 侧**：基于 FastAPI 的自定义异常体系。所有业务异常继承自 `NexusError`，每个异常类携带统一的 `code`（字符串错误码）和 `details`（上下文字典），由 `main.py` 中的 `@app.exception_handler` 统一映射为 JSON 响应并设置 HTTP 状态码。
- **Go 网关侧**：使用 Go 原生 `error` + `fmt.Errorf` / `errors.New` 返回错误，在 handler 中直接构造结构化 JSON 响应（如 `MiddlewareStatus.Error` 字段），未定义统一错误类型或中间件级错误处理器。
- **前端侧**：通过捕获后端返回的 `{error, message, details}` 结构进行差异化展示，无专用错误拦截层。

## 2. 核心文件与包

| 层级 | 关键文件 | 职责 |
|---|---|---|
| 异常定义 | `backend_design/nexus/core/exceptions.py` | 定义 `NexusError` 基类及 `AuthError`、`LLMError`、`RAGError`、`VectorStoreError`、`GraphStoreError`、`MemoryError`、`SkillError`、`IntentError`、`VehicleError`、`CacheError`、`RateLimitError`、`CircuitBreakerError` 等子类 |
| 全局映射 | `backend_design/nexus/main.py` (L383-L422) | 注册 `RateLimitError→429`、`AuthError→401`、`NexusError→500` 三个全局异常处理器，返回统一 JSON 格式 |
| 认证集成 | `backend_design/nexus/core/auth.py` | 将 `jwt.ExpiredSignatureError`/`InvalidTokenError` 转换为 `AuthError`，再由依赖注入层转为 `HTTPException(401)` |
| 熔断器集成 | `backend_design/nexus/core/circuit_breaker.py` | 熔断开启时抛出 `CircuitBreakerError` |
| 限流中间件 | `backend_design/nexus/middleware/rate_limiter.py` | 超限时抛出 `RateLimitError` |
| RAG 层 | `backend_design/nexus/rag/embedding.py`、`graph_store.py`、`vector_store.py` | 底层存储失败时抛出对应 `LLMError`/`GraphStoreError`/`VectorStoreError` |
| Go 网关 | `backend_design/nexus_gate/internal/handlers/handlers.go`、`internal/auth/jwt.go` | 使用 `fmt.Errorf`/`errors.New` 返回错误，handler 内自行组装 JSON 响应 |

## 3. 架构与约定

### 3.1 Python 异常层次

```
NexusError (base)
├── ConfigError          # .env 配置问题
├── AuthError            # JWT 无效/过期 → 401
├── RateLimitError       # 请求超限 → 429
├── CircuitBreakerError  # 熔断开启 → 500
├── LLMError             # 大模型调用失败
├── RAGError             # 检索路由失败
├── VectorStoreError     # Milvus 操作失败
├── GraphStoreError      # Neo4j 操作失败
├── MemoryError          # 记忆读写/冲突检测失败
├── SkillError           # 技能执行失败
├── IntentError          # 意图识别失败
└── VehicleError         # 车控指令发送失败
└── CacheError           # Redis 读写失败
```

每个异常实例化时固定传入 `code`（如 `"AUTH_ERROR"`、`"LLM_ERROR"`），供前端按 code 分支处理。

### 3.2 全局异常到 HTTP 的映射

| 异常类 | HTTP 状态码 | 额外响应头 |
|---|---|---|
| `RateLimitError` | 429 Too Many Requests | `Retry-After: 60` |
| `AuthError` | 401 Unauthorized | `WWW-Authenticate: Bearer` |
| `NexusError`（其他） | 500 Internal Server Error | — |

所有处理器均记录日志（warning/error）并以 `{"error": code, "message": str(exc), "details": exc.details}` 形式返回。

### 3.3 认证链路中的错误转换

- `decode_token()` 捕获 `jwt.ExpiredSignatureError`/`InvalidTokenError` → 抛出 `AuthError`
- `get_current_user()` 捕获 `AuthError` → 转为 `HTTPException(401)`，同时带上 `WWW-Authenticate` 头
- WebSocket 连接同样捕获 `AuthError` 做鉴权拒绝

### 3.4 Go 网关的错误风格

Go 侧未建立统一错误类型，各模块直接使用 `fmt.Errorf("...")` 或 `errors.New("...")`，并在 handler 中将错误信息放入结构化响应体（例如 `MiddlewareStatus.Error`）。JWT 校验失败时返回 `errors.New("invalid token")`，权限不足时返回 `fmt.Errorf("access denied: ...")`。

## 4. 开发者应遵循的规则

1. **业务异常必须继承 `NexusError`**：新增领域错误时，在 `core/exceptions.py` 中定义子类并赋予唯一 `code`，不要裸抛 `Exception`。
2. **不要在端点里 try/except 再 return JSON**：让异常冒泡到全局处理器，由 `main.py` 统一格式化；仅在需要区分 4xx/5xx 时才手动 raise `HTTPException`。
3. **底层库异常要包装成领域异常**：如 `rag/vector_store.py` 把 Milvus 异常包装为 `VectorStoreError`，保持上层调用方只感知领域语义。
4. **认证相关一律走 `AuthError`**：`auth.py` 已提供从 jwt 异常到 `AuthError` 的转换，新鉴权逻辑复用 `decode_token`/`get_current_user`。
5. **Go 网关新增错误时尽量保持结构化**：参考 `handlers.go` 中 `MiddlewareStatus.Error` 的做法，将错误信息作为 JSON 字段返回，便于前端统一解析。
6. **避免 panic/recover**：Python 侧未发现 `try/except Exception` 吞掉异常的模式，也未见 `panic`；Go 侧未见 `recover`，建议继续保持。
