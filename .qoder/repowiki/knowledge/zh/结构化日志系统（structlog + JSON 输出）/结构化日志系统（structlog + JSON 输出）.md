---
kind: logging_system
name: 结构化日志系统（structlog + JSON 输出）
category: logging_system
scope:
    - '**'
source_files:
    - backend_design/nexus/core/logger.py
    - backend_design/nexus/config.py
    - backend_design/nexus/api/websocket.py
    - backend_design/nexus_gate/cmd/main.go
    - backend_design/nexus_gate/internal/ws/hub.go
---

## 1. 使用的框架与工具
- Python 后端统一采用 **structlog** 作为结构化日志框架，所有业务模块通过 `nexus.core.logger` 提供的 `get_logger()` 获取 logger 实例。
- Go 网关（`backend_design/nexus_gate`）使用标准库 `log` 包进行简单文本日志输出，未集成结构化日志框架。
- 日志输出目标为 **stdout**，由上层容器/编排系统采集到 ELK/Loki/Promtail 等日志系统。

## 2. 核心文件与入口
- `backend_design/nexus/core/logger.py`：定义 `setup_logging()`、`get_logger()`、`bind_context()`、`clear_context()`，是 Python 端唯一日志初始化与上下文绑定入口。
- `backend_design/nexus/config.py`：`ServerConfig.log_level` 与 `ServerConfig.debug` 控制日志级别与输出格式（JSON vs ConsoleRenderer）。
- `backend_design/nexus/api/websocket.py`：在 WebSocket 连接建立时调用 `bind_context(client_id=...)`，连接结束时调用 `clear_context()`，实现请求级上下文隔离。
- `backend_design/nexus_gate/cmd/main.go`、`backend_design/nexus_gate/internal/ws/hub.go`：Go 网关使用 `log.Printf` / `log.Fatalf` 输出启动、WS 连接状态等信息。

## 3. 架构与设计约定
- **全局初始化**：应用启动时调用 `setup_logging()`，根据 `config.server.debug` 选择输出格式：
  - debug=True → `structlog.dev.ConsoleRenderer(colors=True)`，彩色控制台便于开发调试。
  - debug=False → `structlog.processors.JSONRenderer(ensure_ascii=False)`，每条日志为单行 JSON，包含 `time`、`level`、`event`、`logger`、`stack_info`、`exc_info` 等字段。
- **日志级别**：从配置项 `LOG_LEVEL`（默认 INFO）映射到 `logging.INFO/WARNING/ERROR/DEBUG`，并通过 `structlog.make_filtering_bound_logger` 过滤低于该级别的日志。
- **上下文变量（Context Vars）**：通过 `bind_context(**kwargs)` 将 `request_id`、`user_id`、`client_id` 等追踪信息绑定到当前协程上下文，后续所有日志自动携带这些字段；`clear_context()` 在请求结束清理，防止上下文泄漏。
- **第三方库兼容**：同时调用 `logging.basicConfig(format="%(message)s", stream=sys.stdout, level=log_level)`，使 uvicorn/sqlalchemy 等依赖标准 logging 的库也能被 structlog 处理器统一格式化。
- **Go 网关独立日志**：Go 侧未复用 Python 日志体系，仅用标准库 `log` 打印关键生命周期事件（启动、监听、WS 连接/断开、错误），无结构化字段、无上下文传递。

## 4. 开发者应遵循的规则
- **统一导入**：所有 Python 模块通过 `from nexus.core.logger import get_logger` 获取 logger，禁止直接使用 `print()` 或 `logging.getLogger(__name__)`。
- **结构化字段**：使用关键字参数记录业务数据，如 `logger.info("User logged in", user_id="12345")`，避免拼接字符串。
- **上下文绑定**：在 HTTP/WebSocket 请求入口处调用 `bind_context(request_id=..., user_id=...)`，在 finally 块中调用 `clear_context()` 确保隔离。
- **日志级别规范**：
  - `debug`：详细调试信息（缓存命中、SQL 等），生产环境默认不输出。
  - `info`：正常业务流程关键点（用户登录、专家执行、响应完成）。
  - `warning`：可恢复异常或降级路径（云端 LLM 不可用回退本地）。
  - `error`：不可恢复错误或需要告警的场景（LLM 调用失败、数据库连接异常）。
- **敏感信息脱敏**：不要在日志中直接输出密码、Token、完整手机号等敏感字段，必要时做掩码处理。
- **Go 网关日志**：保持现有 `log.Printf` 风格即可，如需结构化可在未来引入 `slog` 或 `zap` 并统一接入 Loki。