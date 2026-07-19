---
kind: error_handling
name: NexusCockpit 全栈错误处理体系
category: error_handling
scope:
    - '**'
source_files:
    - backend_design/nexus/core/exceptions.py
    - backend_design/nexus/main.py
    - backend_design/nexus/middleware/rate_limiter.py
    - backend_design/nexus_gate/internal/auth/jwt.go
    - backend_design/nexus_gate/internal/handlers/handlers.go
    - frontend_design/src/lib/api.ts
    - frontend_design/src/hooks/use-async.ts
    - backend_design/nexus/core/logger.py
---

# NexusCockpit 全栈错误处理体系

## 系统架构概览

NexusCockpit 采用分层错误处理架构，在 Python FastAPI 后端、Go 网关和 Next.js 前端三个层面分别实现了统一的错误处理机制。

## Python 后端错误处理

### 自定义异常体系

核心位于 `backend_design/nexus/core/exceptions.py`，定义了完整的异常层次结构：

- **基类**: `NexusError` - 所有业务异常的根类，包含 `message`、`code`、`details` 三个属性
- **领域异常**: 针对特定业务域的错误类型，如 `LLMError`、`RAGError`、`VehicleError`、`AuthError` 等
- **基础设施异常**: 如 `ConfigError`、`CacheError`、`RateLimitError`、`CircuitBreakerError`

每个异常都携带标准化的错误码（如 `"LLM_ERROR"`、`"AUTH_ERROR"`），便于前端根据 code 进行差异化处理。

### FastAPI 全局异常处理器

在 `main.py` 中注册了三个全局异常处理器：

```python
@app.exception_handler(RateLimitError)  # 返回 429 Too Many Requests
@app.exception_handler(AuthError)       # 返回 401 Unauthorized  
@app.exception_handler(NexusError)      # 返回 500 Internal Server Error
```

统一响应格式：
```json
{
  "error": "错误码",
  "message": "人类可读的错误描述",
  "details": {"额外上下文信息"}
}
```

### 中间件错误处理

**限流器** (`middleware/rate_limiter.py`) 使用 Redis Lua 脚本实现原子性滑动窗口算法，超限请求抛出 `RateLimitError`。

**降级策略**: 当 Redis 不可用时，限流器会记录警告日志并放行请求，确保服务可用性。

### 启动期容错

应用启动时对各组件连接失败采用宽容策略：
- Milvus/Neo4j 连接失败仅记录错误日志，不阻止服务启动
- Agent 初始化失败将 `agent_graph` 设为 None，聊天功能不可用但服务继续运行
- 数据库管理器初始化失败记录警告，不影响其他功能

## Go 网关错误处理

### JWT 认证错误

`internal/auth/jwt.go` 使用标准 Go error 模式：
- `ParseToken` 返回详细的解析错误信息
- `ValidateCockpitAccess` 返回权限拒绝错误
- 使用 `errors.New()` 和 `fmt.Errorf()` 构造结构化错误消息

### HTTP 错误响应

网关使用 Gin 框架的 JSON 响应模式，错误响应格式：
```go
c.JSON(404, gin.H{"error": "UNKNOWN_MIDDLEWARE", "message": "Middleware 'xxx' not found"})
```

### 健康检查错误状态

`HealthCheck` 函数根据依赖服务状态返回不同的整体健康状态：
- `healthy`: 所有服务正常
- `degraded`: AI 服务离线但基础功能可用
- `offline`: 关键依赖完全不可用

## 前端错误处理

### Axios 拦截器

`src/lib/api.ts` 实现了统一的请求/响应拦截器：

**请求拦截器**:
- 自动附加 JWT Token 到 Authorization 头
- 附加座舱 ID 到 X-Cockpit-Id 头
- 支持开发环境自动获取 Token

**响应拦截器**:
- 401 错误自动刷新 Token 并重试请求
- 统一错误日志输出
- 网络错误和超时处理

### 流式请求错误处理

自定义 `StreamError` 类携带 HTTP 状态码，支持 SSE 流式响应的错误处理：
```typescript
export class StreamError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "StreamError";
    this.status = status;
  }
}
```

### React Hook 错误封装

`useAsync` hook 提供统一的异步操作错误处理：
- 自动管理 loading 状态
- 捕获并存储错误对象
- 防止组件卸载时的竞态条件
- 提供 refetch 重试机制

## 设计原则与约定

### 错误分类原则
1. **业务错误**: 使用自定义异常，携带语义化错误码
2. **系统错误**: 使用标准异常，记录详细堆栈信息
3. **网络错误**: 区分超时、连接失败、HTTP 状态码
4. **用户输入错误**: 返回具体的验证错误信息

### 错误传播策略
1. **向上冒泡**: 底层异常向上传播到控制器层
2. **统一转换**: 控制器层转换为标准 HTTP 响应
3. **前端适配**: 前端根据错误码和用户友好提示

### 降级与容错
1. **非致命错误**: 记录日志但不中断主流程
2. **依赖降级**: 外部服务不可用时提供降级方案
3. **优雅退出**: 应用关闭时清理资源，记录退出原因

### 可观测性集成
- 所有错误都通过结构化日志记录
- 错误信息包含请求 ID、用户 ID 等上下文
- 支持 ELK/Loki 等日志系统采集分析

这个错误处理体系确保了在多语言、多服务的复杂架构中，错误能够被一致地定义、传播和处理，同时提供了良好的用户体验和运维可观测性。