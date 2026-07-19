---
kind: error_handling
name: NexusCockpit 错误处理体系：分层异常与统一响应
category: error_handling
scope:
    - '**'
source_files:
    - backend_design/nexus/core/exceptions.py
    - backend_design/nexus/main.py
    - backend_design/nexus/core/auth.py
    - backend_design/nexus/core/circuit_breaker.py
    - backend_design/nexus/middleware/rate_limiter.py
    - backend_design/nexus/rag/embedding.py
    - backend_design/nexus_gate/internal/handlers/handlers.go
---

## 1. 整体架构与策略

本仓库采用 **Python FastAPI + Go Gin** 双后端架构，错误处理分为两层：

- **Go 网关层（nexus_gate）**：使用 Go 原生 `error` 返回值 + `fmt.Errorf`/`errors.New` 进行错误传播，通过 `gin.Context.JSON` 直接返回结构化 JSON 响应；健康检查与中间件状态以 `online/offline` 字符串描述。
- **Python AI 服务层（nexus）**：定义统一的自定义异常体系 `NexusError` 及其领域子类，在 `main.py` 中注册全局异常处理器，将业务异常映射为带 `error_code`、`message`、`details` 的 JSON 响应，并区分 HTTP 状态码（401/429/500）。

## 2. 核心文件与包

- **Python 自定义异常定义**：`backend_design/nexus/core/exceptions.py`
  - 基类 `NexusError` 携带 `message`、`code`、`details` 三字段
  - 领域子类：`ConfigError`、`LLMError`、`RAGError`、`VectorStoreError`、`GraphStoreError`、`MemoryError`、`SkillError`、`IntentError`、`VehicleError`、`CacheError`、`AuthError`、`RateLimitError`、`CircuitBreakerError`
- **全局异常处理器**：`backend_design/nexus/main.py`
  - `@app.exception_handler(RateLimitError)` → 429 + `Retry-After: 60`
  - `@app.exception_handler(AuthError)` → 401 + `WWW-Authenticate: Bearer`
  - `@app.exception_handler(NexusError)` → 500
- **认证模块抛出 AuthError**：`backend_design/nexus/core/auth.py`
- **熔断器抛出 CircuitBreakerError**：`backend_design/nexus/core/circuit_breaker.py`
- **限流器抛出 RateLimitError**：`backend_design/nexus/middleware/rate_limiter.py`
- **Embedding 调用 LLM 失败抛 LLMError**：`backend_design/nexus/rag/embedding.py`
- **Go 网关错误处理**：`backend_design/nexus_gate/internal/handlers/handlers.go`
  - 中间件连通性以 `MiddlewareStatus.Error` 字符串字段承载
  - 未知中间件返回 `{"error": "UNKNOWN_MIDDLEWARE", "message": ...}`
  - JWT 校验失败返回 `errors.New("invalid token")` 等原生 error

## 3. 设计约定与流程

```
业务代码 raise NexusError(子类)
    ↓
FastAPI 全局异常处理器匹配具体类型
    ↓
记录日志 (logger.warning/error)
    ↓
返回 JSONResponse { error, message, details } + 对应 HTTP 状态码
```

- **错误码规范**：每个异常子类固定 `code`（如 `"LLM_ERROR"`、`"AUTH_ERROR"`），前端可据此做差异化 UI 提示。
- **启动期容错**：`lifespan` 中对 Milvus、Neo4j、Agent Graph、MySQL、DataRetentionManager 等初始化均用 `try/except` 捕获并降级（记录 warning 后继续启动），保证服务可用性。
- **Go 侧风格**：不定义统一错误结构体，直接在 handler 中 `c.JSON(status, gin.H{"error": ..., "message": ...})` 返回，保持简洁。

## 4. 开发者应遵循的规则

1. **业务异常必须继承 `NexusError` 或其子类**，不要直接 `raise Exception` 或裸 `HTTPException`（路由层已有大量 `HTTPException` 用法，建议逐步迁移到自定义异常）。
2. **为新领域新增错误时**：在 `core/exceptions.py` 添加子类，指定有意义的 `code`，并在需要处 `raise`。
3. **不要在业务函数中 catch 并吞掉异常**，让上层全局处理器统一格式化输出。
4. **Go 网关新增错误路径**：沿用 `handlers.go` 风格，返回 `{error, message}` 结构的 JSON，避免 panic。
5. **对外暴露的错误信息不应包含敏感细节**，`details` 仅用于内部调试，生产环境可通过配置控制是否回传。

## 5. 已知不一致点

- 路由层（`cockpit.py`、`settings.py` 等）仍大量直接使用 `fastapi.HTTPException`，未走 `NexusError` 体系，导致这些路径不会触发全局异常处理器，也不会附带 `error_code` 字段。这是当前实现中的主要不一致之处。
- Go 网关与 Python 服务的错误响应格式不完全一致（Go 用 `error/message`，Python 用 `error/message/details`），前端需兼容两种结构。