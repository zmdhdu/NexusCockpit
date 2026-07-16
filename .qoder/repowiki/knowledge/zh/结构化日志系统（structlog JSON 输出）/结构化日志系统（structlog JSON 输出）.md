---
kind: logging_system
name: 结构化日志系统（structlog JSON 输出）
category: logging_system
scope:
    - '**'
source_files:
    - backend_design/nexus/core/logger.py
    - backend_design/nexus/config.py
    - backend_design/nexus/main.py
    - backend_design/pyproject.toml
    - backend_design/requirements.txt
---

## 1. 使用的系统与框架
- Python 后端统一采用 structlog（>=24.1.0）作为结构化日志库，通过 nexus.core.logger 模块集中初始化。
- 标准库 logging 仅用于为第三方组件（uvicorn、SQLAlchemy 等）提供基础配置，业务代码不直接使用。
- Go 网关（backend_design/nexus_gate）未使用 structlog，由 Go 自身 log 包处理，与 Python 端日志体系解耦。

## 2. 核心文件与入口
- backend_design/nexus/core/logger.py：唯一日志基础设施，提供 setup_logging()、get_logger()、bind_context()、clear_context()。
- backend_design/nexus/config.py：ServerConfig.log_level（环境变量 LOG_LEVEL）驱动日志级别；ServerConfig.debug 控制开发/生产输出格式。
- backend_design/nexus/main.py：在 FastAPI lifespan 启动阶段调用 setup_logging()，确保所有子模块获取到已配置的 logger。
- 依赖声明：pyproject.toml / requirements.txt / requirements_no_torch.txt 均包含 structlog>=24.1.0。

## 3. 架构与约定
### 3.1 处理器链（processors）
merge_contextvars → add_log_level → TimeStamper("iso") → StackInfoRenderer → format_exc_info → {JSONRenderer | ConsoleRenderer}
- 上下文变量自动合并：支持 request_id、user_id 等跨层追踪字段。
- 时间戳 ISO 8601 格式，便于 ELK/Loki 解析。
- 异常信息经 format_exc_info 格式化后嵌入日志。
- 输出格式切换：
  - debug=True：ConsoleRenderer(colors=True) 彩色控制台，适合本地调试。
  - debug=False：JSONRenderer(ensure_ascii=False) 纯 JSON，供日志采集系统消费。

### 3.2 日志级别过滤
- 通过 structlog.make_filtering_bound_logger(log_level) 包装，级别来自 config.server.log_level（默认 INFO），映射到 logging.INFO/WARNING/ERROR/DEBUG 常量。

### 3.3 上下文绑定
- bind_context(**kwargs)：将任意键值对绑定到当前协程上下文，后续所有日志自动携带这些字段。
- clear_context()：请求结束时清理，防止上下文泄漏。
- 典型用法：在 API 中间件或 WebSocket 连接建立时绑定 request_id、cockpit_id、user_id 等。

### 3.4 使用模式（全仓库一致）
from nexus.core.logger import get_logger
logger = get_logger(__name__)
logger.info("事件描述", field1="value1", field2=123)
logger.error("错误消息", exc_info=True)
- 所有模块通过 get_logger(__name__) 获取 logger，避免直接实例化。
- 日志调用集中在 agent/ 各专家、main.py 启动流程等处，遵循 info/debug/warning/error 语义。

## 4. 开发者应遵守的规则
1. 禁止使用 print() / logging.getLogger()：统一通过 nexus.core.logger.get_logger(__name__) 获取 logger。
2. 结构化字段以关键字参数传递：如 logger.info("login", user_id=user.id, ip=request.client.host)，不要拼接字符串。
3. 在请求边界绑定上下文：在 API 中间件或 WebSocket 握手处调用 bind_context(request_id=...)，在响应/关闭时调用 clear_context()。
4. 日志级别选择：
   - debug：详细调试信息（仅本地 debug 模式可见）。
   - info：关键业务流程节点（启动、连接成功、意图路由结果等）。
   - warning：可恢复异常或降级路径（如 Redis 不可用回退内存）。
   - error：失败且需要告警的错误（LLM 调用失败、数据库连接异常等）。
5. 敏感信息脱敏：不要在日志中输出密码、AK/SK、完整 token；示例中仅打印末 4 位和长度。
6. 异常必须带 exc_info：logger.error("msg", exc_info=True) 以便捕获堆栈。
7. Go 网关侧：如需与 Python 端关联，可通过 HTTP Header 透传 X-Request-ID，并在 Go 侧记录同一 ID。