---
kind: logging_system
name: 结构化日志系统（structlog + Loki + Prometheus）
category: logging_system
scope:
    - '**'
source_files:
    - backend_design/nexus/core/logger.py
    - backend_design/nexus/config/server.py
    - backend_design/nexus/main.py
    - config/loki/loki-config.yml
    - backend_design/nexus_gate/cmd/main.go
    - backend_design/nexus/observability/langfuse.py
    - backend_design/nexus/observability/metrics.py
---

NexusCockpit 在后端 Python 服务与 Go 网关中采用分层、结构化的日志体系：Python 侧基于 structlog 输出 JSON 结构化日志，Go 侧使用标准库 log 输出文本日志，统一通过 Docker Compose 编排的 Loki 进行聚合，Prometheus/Grafana 提供指标与可视化。后端日志同时写入本地文件，便于离线排查。

1. 使用的框架与工具
- Python 后端：structlog（结构化日志）、logging（stdlib 过滤器与 FileHandler/StreamHandler）、prometheus_client（指标暴露）
- Go 网关：标准库 log（log.Printf/log.Fatalf），输出到 stdout 与文件
- 日志聚合：Loki（单机模式，schema v12，保留 168h）
- 指标与可视化：Prometheus + Grafana（预置 dashboard）
- Langfuse：可选的 LLM 追踪平台（通过 ObservabilityConfig 控制开关）

2. 核心文件与位置
- nexus/core/logger.py：结构化日志初始化、敏感字段脱敏处理器、上下文绑定 API
- nexus/config/server.py：ServerConfig.log_level 控制日志级别
- nexus/main.py：应用启动时调用 setup_logging()，并打印当前日志文件路径
- config/loki/loki-config.yml：Loki 配置（端口 3100/9096，文件系统存储，7 天保留）
- backend_design/nexus_gate/cmd/main.go：Go 网关日志输出到文件+stdout
- backend_design/nexus/observability/langfuse.py / metrics.py：Langfuse 追踪与 Prometheus 指标

3. 架构与设计决策
- 双通道输出：structlog 负责业务结构化日志（JSON），stdlib logging 负责 uvicorn/access/error 等框架日志，两者共享同一个 FileHandler 写入同一文件
- 环境自适应格式：config.server.debug=True 时 structlog 输出彩色控制台；生产环境输出 JSON（ensure_ascii=False），便于 Loki/ELK 解析
- 统一日志级别：由 ServerConfig.log_level（默认 INFO）驱动，通过 getattr(logging, level.upper()) 映射为 stdlib 常量
- 日志文件命名：logs/backend_logs/backend_YYYYMMDD_HHMMSS.log，每次启动生成新文件
- 上下文追踪：通过 bind_context(request_id, user_id) 将请求级上下文自动注入后续所有日志，clear_context() 在请求结束时清理
- 敏感数据脱敏：sanitize_log_processor 对 event_dict 中的 key（api_key/secret/token/password/jwt/bearer 等）和 value（Bearer token、长密钥字符串）进行 ***REDACTED*** 掩码；stdlib 过滤器同步处理消息体
- 第三方日志降噪：redis.asyncio.connection、neo4j、aiosqlite、openai、httpcore、python_multipart 等库的 DEBUG 日志被降级至 INFO/WARNING/ERROR，避免刷屏与敏感信息泄露
- uvicorn 访问日志：显式为 uvicorn、uvicorn.access、uvicorn.error 添加共享 FileHandler，确保 HTTP 访问记录也写入文件

4. 约定与约束
- 模块内日志获取方式固定为 `from nexus.core.logger import get_logger; logger = get_logger(__name__)`，已在 agent/experts、agent/nodes、agent/generation_task_pool 等大量文件中统一使用
- 结构化日志字段必须包含时间戳（ISO 格式）、级别、模块名，额外字段通过关键字参数传入（如 user_id、request_id）
- 禁止直接 print()/logging.getLogger() 绕过脱敏流程；如需 stdlib 日志，需经 SensitiveDataFilter 过滤
- 日志级别通过 .env.local 的 LOG_LEVEL 配置，DEBUG 仅用于开发环境
- Go 网关日志使用 log.Printf，不接入 structlog，但遵循相同的“日志文件路径”输出约定，便于集中查看
- Loki 保留策略强制 168h（7 天），reject_old_samples=true，防止磁盘无限增长