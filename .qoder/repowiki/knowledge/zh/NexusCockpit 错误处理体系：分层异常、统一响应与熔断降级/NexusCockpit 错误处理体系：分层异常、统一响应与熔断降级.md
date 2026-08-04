---
kind: error_handling
name: NexusCockpit 错误处理体系：分层异常、统一响应与熔断降级
category: error_handling
scope:
    - '**'
source_files:
    - backend_design/nexus/core/exceptions.py
    - backend_design/nexus/main.py
    - backend_design/nexus/core/circuit_breaker.py
    - backend_design/nexus_gate/internal/router/router.go
    - frontend_design/src/app/error.tsx
    - frontend_design/src/app/global-error.tsx
    - frontend_design/src/hooks/use-async.ts
---

## 1. 系统/方法概述
- Python 后端（FastAPI）采用「自定义异常类 + 全局异常处理器」模式，所有业务异常继承自 `NexusError`，由 `main.py` 中注册的多个 `@app.exception_handler` 统一转换为 `{error, message, details}` 格式的 JSON 响应。
- Go 网关（Gin）使用 `fmt.Errorf` / `errors.New` 返回错误，并通过自定义 Recovery 中间件捕获 panic，将非预期的 `http.ErrAbortHandler` 重新抛出以正确关闭连接，其余 panic 转为 500 JSON。
- 前端 Next.js 通过 `error.tsx`（路由级）和 `global-error.tsx`（根布局级）两个错误边界组件捕获渲染期未处理异常，提供重试/返回首页等恢复操作。
- 外部依赖故障通过 `core/circuit_breaker.py` 的三状态熔断器（CLOSED/OPEN/HALF_OPEN）进行隔离与自动降级（如 LLM 云端失败回退本地模型、Milvus 不可用跳过向量检索等）。

## 2. 关键文件与包
- 异常定义：`backend_design/nexus/core/exceptions.py`（`NexusError` 基类及 `AuthError`、`LLMError`、`RAGError`、`VectorStoreError`、`GraphStoreError`、`MemoryError`、`SkillError`、`IntentError`、`VehicleError`、`CacheError`、`RateLimitError`、`CircuitBreakerError` 等子类）
- FastAPI 应用入口与全局异常处理器：`backend_design/nexus/main.py`（注册 RateLimitError→429、AuthError→401、NexusError→500、HTTPException、RequestValidationError、兜底 Exception 处理器）
- 熔断器实现：`backend_design/nexus/core/circuit_breaker.py`（`CircuitBreaker` 类，配合 `CircuitBreakerError` 触发降级）
- Go 网关路由与 Recovery：`backend_design/nexus_gate/internal/router/router.go`（自定义 `recover()` 中间件、`AuthMiddleware`、`OptionalAuthMiddleware`、`RequireRole`、`RateLimitMiddleware`）
- 前端错误边界：`frontend_design/src/app/error.tsx`、`frontend_design/src/app/global-error.tsx`
- 前端异步 Hook 错误封装：`frontend_design/src/hooks/use-async.ts`（统一 `data/loading/error/refetch` 结构）

## 3. 架构与约定
- 异常分类与错误码：每个 `NexusError` 子类携带 `code`（如 `"AUTH_ERROR"`、`"RATE_LIMIT_ERROR"`、`"CIRCUIT_BREAKER_ERROR"`），便于前端按 code 做差异化处理。
- 统一响应格式：所有 HTTP 异常最终返回 `{ error: string, message: string, details: dict }`，包括 FastAPI 内置的 `HTTPException` 和 `RequestValidationError` 也被转换为此格式。
- 启动期容错：`lifespan` 中对 Milvus/Neo4j/Agent/MCP/ReminderScanner/llama.cpp 等初始化均使用 try/except 包裹，失败仅记录 warning 并继续启动，运行时再按需降级。
- 网关层鉴权与限流：Go 侧通过中间件统一处理 JWT 校验、座舱权限、优先级限流，错误以 `{error, message}` JSON 返回，避免泄露内部堆栈。
- 前端错误边界分层：`error.tsx` 捕获页面渲染异常（保留 layout），`global-error.tsx` 捕获根布局异常（替换整个 html/body），并提供重试/刷新按钮。

## 4. 约定与约束
- 业务异常必须继承 `NexusError` 或其子类，禁止直接 raise 裸 `Exception`；否则会被兜底处理器包装为 `INTERNAL_ERROR`。
- 限流异常统一抛 `RateLimitError`，由处理器返回 429 并附带 `Retry-After` 头。
- 认证失败统一抛 `AuthError`，返回 401 并附带 `WWW-Authenticate: Bearer` 头。
- 熔断器在 OPEN 状态下调用受保护函数会直接抛出 `CircuitBreakerError`，调用方应据此执行降级逻辑（如切换本地 LLM、跳过向量检索）。
- Go 网关中 `http.ErrAbortHandler` panic 必须重新抛出，不得被 Recovery 吞掉，以保证 net/http 能正确关闭客户端断开的连接。
- 前端通过 `use-async` hook 获取 `{ data, loading, error, refetch }`，组件内 catch 到的错误需转换为标准 Error 对象以便统一展示。
- 所有未处理的 Python 异常都会被 `unhandled_exception_handler` 捕获，记录完整堆栈后返回 500 且不含内部细节，防止信息泄露。