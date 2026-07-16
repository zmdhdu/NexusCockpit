---
kind: logging_system
name: 结构化日志系统（structlog + JSON 输出）
category: logging_system
scope:
    - '**'
source_files:
    - backend_design/nexus/core/logger.py
    - backend_design/nexus/config.py
    - backend_design/nexus/main.py
    - backend_design/nexus/api/websocket.py
---

## 1. 使用的框架与工具
- **核心库**：`structlog`，提供结构化、可组合的日志处理器链。
- **标准库桥接**：通过 `logging.basicConfig` 将第三方库（如 uvicorn/sqlalchemy）的标准 `logging` 输出也统一走 structlog 管道。
- **上下文追踪**：基于 `structlog.contextvars` 实现请求级/会话级上下文变量绑定（如 `request_id`、`user_id`、`client_id`），自动注入到后续所有日志中。
- **配置来源**：日志级别和输出格式由 `nexus.config.ServerConfig.log_level` 与 `ServerConfig.debug` 控制，默认从 `.env.local` / `.env.prod` 读取。

## 2. 关键文件与包
- `backend_design/nexus/core/logger.py` — 日志初始化、获取器、上下文绑定/清理入口。
- `backend_design/nexus/config.py` — `ServerConfig.log_level`、`ServerConfig.debug` 等日志相关配置项定义。
- `backend_design/nexus/main.py` — 应用启动时调用 `setup_logging()` 完成全局初始化。
- `backend_design/nexus/api/websocket.py` — 在 WebSocket 连接生命周期内使用 `bind_context(client_id=...)` / `clear_context()` 管理上下文。
- 各业务模块（agent、experts、planner、responder 等）通过 `from nexus.core.logger import get_logger` 获取 logger 实例并调用 `logger.info/debug/error/warning`。

## 3. 架构与约定
- **单点初始化**：`setup_logging()` 只应在应用启动阶段调用一次，它会同时配置 Python 标准 `logging` 和 `structlog`。
- **处理器流水线**：
  - `merge_contextvars` → `add_log_level` → `TimeStamper(fmt="iso")` → `StackInfoRenderer` → `format_exc_info` → 最终渲染器。
- **输出格式策略**：
  - `debug=True`：`ConsoleRenderer(colors=True)`，彩色控制台，便于本地调试。
  - `debug=False`：`JSONRenderer(ensure_ascii=False)`，每条日志为单行 JSON，包含 `time`、`level`、`event`、`module`、`stack_info`、`exc_info` 以及所有上下文变量字段，适合被 Loki/ELK 采集。
- **日志级别映射**：字符串级别（如 `"INFO"`）通过 `getattr(logging, level.upper(), logging.INFO)` 转换为标准常量，默认 `INFO`。
- **上下文变量**：通过 `bind_context(**kwargs)` 绑定任意键值对，所有后续日志自动携带；请求结束时调用 `clear_context()` 防止泄漏。WebSocket 层已按连接粒度做绑定/清理。
- **Logger 获取方式**：统一使用 `logger = get_logger(__name__)`，避免直接 `import logging.getLogger`，确保走 structlog 包装器。

## 4. 开发者应遵循的规则
1. **始终通过 `get_logger(__name__)` 获取 logger**，不要自行创建 `logging.Logger` 或 `structlog.get_logger` 绕过配置。
2. **在应用入口调用 `setup_logging()`**：新脚本（如 `init_milvus.py`、`init_neo4j.py`）需显式导入并调用，否则无法获得结构化输出。
3. **使用结构化字段而非拼接字符串**：推荐 `logger.info("User logged in", user_id="12345")`，让 structlog 把额外参数作为 JSON 字段输出。
4. **在请求/连接边界绑定上下文**：HTTP/WebSocket 进入时 `bind_context(request_id=..., user_id=...)`，退出时 `clear_context()`，保证链路追踪字段完整且不泄漏。
5. **合理选择日志级别**：
   - `debug`：仅开发环境可见的详细诊断信息（如缓存未命中、内部状态）。
   - `info`：关键业务流程节点（意图路由、专家执行开始/结束）。
   - `warning`：可恢复异常或降级路径（如 Redis 不可用回退）。
   - `error`：需要告警的错误（LLM 调用失败、数据库写入异常）。
6. **不要在日志中记录敏感信息**（密码、Token、PII），因为生产环境会输出 JSON 并被外部日志系统持久化。