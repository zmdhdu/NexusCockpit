---
kind: error_handling
name: NexusCockpit 错误处理体系：分层异常与全局处理器
category: error_handling
scope:
    - '**'
source_files:
    - backend_design/nexus/core/exceptions.py
    - backend_design/nexus/main.py
    - backend_design/nexus/core/auth.py
    - backend_design/nexus/core/circuit_breaker.py
    - backend_design/nexus/api/websocket.py
    - backend_design/nexus_gate/internal/auth/jwt.go
---

## 1. 采用的系统/方法
- Python (FastAPI)：采用「自定义异常类 + FastAPI @app.exception_handler」模式，所有业务异常继承统一基类 NexusError，在应用启动时注册全局处理器，将异常映射为统一的 JSON 响应 {error, message, details}。
- Go (nexus_gate 网关)：使用 Go 原生 error 返回值 + errors.New，无统一错误码体系，由调用方自行判断并返回 HTTP 状态。
- 前端：未定义专用错误类型，通过 fetch / WebSocket 的 catch 分支处理网络层异常。

## 2. 核心文件与包
- backend_design/nexus/core/exceptions.py — 全部自定义异常定义（NexusError 基类及 10+ 子类）
- backend_design/nexus/main.py — FastAPI 应用入口，集中注册 RateLimitError、AuthError、NexusError 三个全局异常处理器
- backend_design/nexus/core/auth.py — JWT 认证模块，抛出 AuthError 并在依赖中转为 HTTPException(401)
- backend_design/nexus/core/circuit_breaker.py — 熔断器抛出 CircuitBreakerError
- backend_design/nexus/api/websocket.py — WebSocket 层捕获 AuthError 做连接级鉴权失败处理
- backend_design/nexus_gate/internal/auth/jwt.go — Go 侧使用 errors.New("invalid token") 等原生 error

## 3. 架构与约定
### 异常层次结构
NexusError (base)
├── ConfigError          # .env 配置错误
├── LLMError             # 大模型 API 调用失败
├── RAGError             # 向量检索/图谱查询失败
├── VectorStoreError     # Milvus 操作失败
├── GraphStoreError      # Neo4j 操作失败
├── MemoryError          # 记忆存储/检索/冲突检测失败
├── SkillError           # 技能执行失败
├── IntentError          # 意图路由失败
├── VehicleError         # 车控指令发送失败
├── CacheError           # Redis 读写失败
├── AuthError            # JWT Token 无效/过期
├── RateLimitError       # 请求频率超限
└── CircuitBreakerError  # 熔断器开启

每个异常均携带 code（如 "LLM_ERROR"、"AUTH_ERROR"）和可选 details 字典，供前端按 code 差异化处理。

### 全局异常处理流程
1. 业务代码抛出具体 NexusError 子类
2. FastAPI 根据注册的 @app.exception_handler 匹配处理器
3. 处理器记录日志并返回统一 JSON 响应：
   - RateLimitError → 429 + Retry-After: 60
   - AuthError → 401 + WWW-Authenticate: Bearer
   - 其他 NexusError → 500
4. 未匹配的 Python 内置异常（如 FileNotFoundError、ImportError）在各路由中以裸 except 捕获后直接返回，未走统一格式。

### 认证链路中的双重策略
- decode_token 内部抛 AuthError（带中文 message）
- get_current_user 依赖将其转换为 HTTPException(401)，以便 FastAPI 默认 401 行为生效
- websocket.py 中则直接 except AuthError 关闭 WebSocket 连接

### Go 网关的差异
Go 侧未复用 Python 的错误码体系，仅用 errors.New 返回字符串错误，由 handler 自行决定 HTTP 状态码，与 Python 端存在语义不一致风险。

## 4. 开发者应遵循的规则
1. 不要直接 raise 裸 Exception：所有业务异常必须继承 NexusError 并使用对应子类，确保 code 字段可被前端识别。
2. 不要在路由里写裸 except：优先让异常冒泡到全局处理器；仅在需要降级（如可选依赖缺失）时才 catch 并返回友好提示。
3. 认证相关一律抛 AuthError：由 auth.get_current_user 负责转成 401，不要在业务层手动 raise HTTPException(401)。
4. 限流/熔断异常使用专用类型：RateLimitError、CircuitBreakerError 能触发 429/503 特定响应头，避免混入通用 500。
5. Go 网关如需新增错误码：建议定义统一 ErrorCode 常量并与 Python 端对齐，避免前后端对同一错误的理解分歧。
6. WebSocket 场景：参考 api/websocket.py，在连接建立阶段捕获 AuthError 主动关闭连接，而非等待消息处理阶段。