---
kind: logging_system
name: 结构化日志系统 — structlog + 标准库双通道输出
category: logging_system
scope:
    - '**'
source_files:
    - backend_design/nexus/core/logger.py
    - backend_design/nexus/main.py
    - backend_design/nexus/api/websocket.py
    - backend_design/nexus_gate/cmd/main.go
---

## 1. 系统与框架
- Python 后端：基于 `structlog` 提供 JSON 结构化日志，同时通过 `logging` 标准库向控制台与文件输出；生产环境 JSON、开发环境彩色控制台。
- Go 网关（NexusGate）：使用 Go 标准库 `log`，将输出同时写入 `logs/go_logs/` 下的按时间命名的文件与 stdout。
- 前端未实现独立日志子系统，主要依赖浏览器控制台与后端日志。

## 2. 核心文件与包
- `backend_design/nexus/core/logger.py`：Python 日志初始化、处理器配置、structlog 管道、上下文绑定/清理 API。
- `backend_design/nexus/main.py`：应用启动时调用 `setup_logging()`，并打印当前日志文件路径。
- `backend_design/nexus_gate/cmd/main.go`：Go 网关入口，创建 `logs/go_logs/gateway_YYYYMMDD_HHMMSS.log` 并设置 `io.MultiWriter(file, os.Stdout)`。
- `backend_design/nexus/api/websocket.py`：在 WebSocket 连接建立/关闭处调用 `bind_context(client_id=...)` / `clear_context()`，实现请求级上下文传播。

## 3. 架构与约定
- **统一初始化**：`main.lifespan` 中优先执行 `setup_logging()`，再初始化其他组件，确保所有模块均可立即使用 logger。
- **双通道输出**：
  - Python：`FileHandler` → `logs/backend_logs/backend_YYYYMMDD_HHMMSS.log`；`StreamHandler` → stdout；uvicorn 的 `uvicorn`/`uvicorn.access`/`uvicorn.error` 额外挂载同一 FileHandler，避免访问日志只落终端。
  - Go：`io.MultiWriter(file, os.Stdout)`，日志文件位于 `logs/go_logs/gateway_YYYYMMDD_HHMMSS.log`。
- **结构化字段**：structlog 处理器链包含 `merge_contextvars`、`add_log_level`、`TimeStamper(fmt="iso")`、`StackInfoRenderer`、`format_exc_info`，最终由 `JSONRenderer(ensure_ascii=False)` 输出 JSON；开发模式切换为 `ConsoleRenderer(colors=True)`。
- **上下文追踪**：通过 `bind_context(**kwargs)` 绑定如 `client_id`、`request_id`、`user_id` 等字段，后续所有日志自动携带；`clear_context()` 在请求结束时清理，防止跨请求泄漏。WebSocket 中间件已示范该用法。
- **日志级别策略**：从配置 `config.server.log_level`（字符串如 "INFO"）映射到 `logging.INFO` 等常量，并通过 `make_filtering_bound_logger(log_level)` 控制 structlog 过滤阈值。
- **可观测性集成**：`nexus.observability.langfuse.LangfuseMonitor` 在生命周期内 flush，用于 LLM 调用链路追踪；Prometheus `/metrics` 端点由 `prometheus_client.make_asgi_app` 挂载，与日志互补但不混用。

## 4. 开发者规范
- **获取日志器**：在模块顶部 `from nexus.core.logger import get_logger; logger = get_logger(__name__)`，不要直接 `import logging` 或 `print`。
- **记录结构化信息**：以关键字参数传递业务字段，例如 `logger.info("User logged in", user_id="12345")`，便于 JSON 检索。
- **上下文变量**：在请求/会话边界使用 `bind_context(...)` 绑定 `client_id`、`request_id`、`cockpit_id` 等，并在结束处调用 `clear_context()`。
- **级别选择**：调试细节用 `debug`，正常流程用 `info`，可恢复异常用 `warning`，不可恢复错误用 `error`；避免滥用 `fatal`。
- **敏感信息**：严禁记录密码、API Key 明文；示例中仅记录末 4 位与长度。
- **Go 侧**：在 `nexus_gate/internal/*` 中使用 `log.Printf`/`log.Println` 即可，无需引入第三方库；如需结构化字段，建议仿照 Python 模式封装。
- **日志轮转**：当前按启动时间命名新文件，未实现自动轮转；可通过外部工具（如 logrotate）或扩展 `setup_logging` 增加轮转逻辑。