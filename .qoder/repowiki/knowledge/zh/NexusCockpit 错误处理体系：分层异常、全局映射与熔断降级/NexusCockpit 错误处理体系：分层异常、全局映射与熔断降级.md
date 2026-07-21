---
kind: error_handling
name: NexusCockpit 错误处理体系：分层异常、全局映射与熔断降级
category: error_handling
scope:
    - '**'
source_files:
    - backend_design/nexus/core/exceptions.py
    - backend_design/nexus/main.py
    - backend_design/nexus/core/auth.py
    - backend_design/nexus/middleware/rate_limiter.py
    - backend_design/nexus/core/circuit_breaker.py
    - backend_design/nexus_gate/internal/handlers/handlers.go
    - backend_design/nexus_gate/internal/auth/jwt.go
---

## 1. 采用的系统与方法
- Python 后端（FastAPI）采用「自定义异常类 + 全局异常处理器」模式，所有业务异常统一继承 `NexusError`，由 FastAPI 的 `@app.exception_handler` 映射为带 `error_code`、`message`、`details` 字段的 JSON 响应。
- Go 网关（Gin）使用原生 `error` 返回值 + `c.JSON(status, gin.H{"error":..., "message":...})` 直接返回结构化错误体，未定义统一的 error 类型或中间件统一包装。
- 前端（Next.js）通过 `fetch`/`axios` 调用 API，按 HTTP 状态码和返回体中的 `error` 字段做差异化提示，无集中错误拦截器。

## 2. 核心文件与包
- Python 异常定义与全局映射
  - `backend_design/nexus/core/exceptions.py` — 所有业务异常基类 `NexusError` 及领域子类（ConfigError、LLMError、RAGError、VectorStoreError、GraphStoreError、MemoryError、SkillError、IntentError、VehicleError、CacheError、AuthError、RateLimitError、CircuitBreakerError）
  - `backend_design/nexus/main.py` — 在 `create_app()` 中注册三个全局异常处理器：`RateLimitError→429`、`AuthError→401`、`NexusError→500`
- 认证与限流错误路径
  - `backend_design/nexus/core/auth.py` — JWT 校验失败抛出 `AuthError`，依赖 `get_current_user` 将其转为 `HTTPException(401)`
  - `backend_design/nexus/middleware/rate_limiter.py` — Redis 滑动窗口限流，超限抛 `RateLimitError`，被全局处理器映射为 429
- 熔断器错误
  - `backend_design/nexus/core/circuit_breaker.py` — 三态熔断器，OPEN/HALF_OPEN 限制时抛 `CircuitBreakerError`，最终由 `NexusError` 处理器返回 500
- Go 网关错误处理
  - `backend_design/nexus_gate/internal/handlers/handlers.go` — 健康检查、中间件状态、数据中台等接口直接用 `c.JSON(404/500, gin.H{"error":..., "message":...})` 返回错误体；`internal/auth/jwt.go` 使用标准库 `errors.New` 返回错误字符串

## 3. 架构与约定
- 异常分层
  - 基类 `NexusError` 强制携带 `code`（如 `"LLM_ERROR"`、`"RATE_LIMIT_ERROR"`），便于前端按 code 分支处理；`details` 字典承载调试上下文。
  - 每个子系统（LLM/RAG/向量存储/图谱/记忆/技能/意图/车控/缓存/认证/限流/熔断）都有专属异常子类，语义清晰且可被全局处理器统一捕获。
- 全局映射策略
  - `main.py` 仅注册三类处理器：限流 429、认证 401、其他 NexusError 500。路由层不再重复 try/except，保持端点简洁。
  - 纯 ASGI 中间件 `CockpitContextMiddleware` 同时注入 Prometheus 指标并透传座舱上下文，确保错误路径也能记录请求计数与延迟。
- 容错与降级
  - 启动阶段对 Milvus/Neo4j/Agent/Cherry KB/MySQL/DataRetentionManager 等外部依赖均使用 try/except 包裹，失败仅告警不阻断服务启动，运行时再按需重试或降级。
  - 熔断器 `CircuitBreaker.call` 在 OPEN/HALF_OPEN 状态下主动抛 `CircuitBreakerError`，调用方可据此切换本地模型、Mock 车控等降级逻辑。
  - 限流器 Redis 不可用时默认放行（fail-open），避免单点故障导致全局限流失效。
- Go 网关侧约定
  - 非 AI 请求（健康检查、中间件探测、数据中台概览）由 Go 直接处理，错误以 `gin.H{"error":..., "message":...}` 形式返回，状态码由具体场景决定（404/500 等）。
  - JWT 解析失败返回 `errors.New("invalid token")`，上层根据 error 是否为 nil 判断鉴权结果。

## 4. 开发者应遵循的规则
- 业务异常必须从 `NexusError` 派生，并设置明确的 `code`（建议沿用已有常量风格，如 `"VEHICLE_ERROR"`），不要直接 raise 裸 `Exception`。
- 需要返回 401/429 的场景优先抛 `AuthError` / `RateLimitError`，让全局处理器自动映射；其他业务错误抛对应子类，由 `NexusError` 处理器统一返回 500。
- 路由层尽量只写 happy path，把参数校验、权限检查、限流、熔断等横切逻辑下沉到依赖注入或中间件，不要在每个端点里手写 try/except。
- 对外部依赖（Redis/Milvus/Neo4j/LLM API）的调用应包裹熔断器或显式 try/except，失败时记录日志并返回用户友好的 message，必要时触发降级流程。
- Go 网关新增接口时，错误体结构应与现有 `gin.H{"error":..., "message":...}` 保持一致，方便前端统一解析。
- 前端在处理 API 错误时，优先检查 HTTP 状态码，其次读取返回体中的 `error` 字段进行分支处理，`details` 仅用于开发调试，不应作为用户可见文案。