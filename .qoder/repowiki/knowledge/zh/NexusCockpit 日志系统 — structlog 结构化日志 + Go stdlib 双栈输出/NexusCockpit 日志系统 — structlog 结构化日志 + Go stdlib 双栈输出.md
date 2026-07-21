---
kind: logging_system
name: NexusCockpit 日志系统 — structlog 结构化日志 + Go stdlib 双栈输出
category: logging_system
scope:
    - '**'
source_files:
    - backend_design/nexus/core/logger.py
    - backend_design/nexus/main.py
    - backend_design/nexus_gate/cmd/main.go
    - config/loki/loki-config.yml
---

## 1. 系统概览

本项目采用双语言、双栈日志体系：
- Python FastAPI 后端：基于 structlog 的结构化 JSON 日志，统一通过 nexus.core.logger 初始化与获取。
- Go NexusGate 网关：使用标准库 log，按进程/日期生成文件，同时输出到 stdout。
- 前端 Next.js：未引入专用日志框架，仅以控制台输出为主。

所有服务均遵循开发彩色控制台 + 生产 JSON 文件的格式策略，并内置敏感字段脱敏能力。

## 2. 核心文件与包

- backend_design/nexus/core/logger.py：structlog 配置、脱敏处理器、上下文绑定、日志文件路径管理
- backend_design/nexus/main.py：启动时调用 setup_logging()，打印日志文件路径
- backend_design/nexus_gate/cmd/main.go：创建 logs/go_logs/gateway_YYYYMMDD_HHMMSS.log，MultiWriter 输出到文件+stdout
- logs/backend_logs/ / logs/go_logs/ / logs/frontend_logs/：按服务分目录、按天命名
- config/loki/loki-config.yml：日志聚合采集配置（供外部 Loki 使用）

## 3. 架构与设计决策

### Python 侧：structlog 结构化日志
- 初始化时机：FastAPI lifespan 中优先执行 setup_logging()，确保后续所有模块均可用。
- 输出目标：
  - 控制台：StreamHandler，开发环境启用 ConsoleRenderer(colors=True)。
  - 文件：FileHandler，写入 logs/backend_logs/backend_YYYYMMDD_HHMMSS.log，UTF-8 编码。
- uvicorn 兼容：显式为 uvicorn / uvicorn.access / uvicorn.error 添加共享 FileHandler，避免 uvicorn 覆盖 root logger 导致访问日志不落地。
- 结构化字段：每条日志自动携带 timestamp (ISO)、level、logger_name、stack_info、exc_info；支持通过 bind_context(request_id=...) 注入链路追踪字段。
- 敏感数据脱敏：
  - key 匹配 api_key|secret|token|password|jwt|bearer → 值替换为 ***REDACTED***。
  - value 字符串中的 Bearer token、长密钥（sk- 前缀或 32+ 字符）被部分掩码。
  - 对 stdlib logging 和 structlog 两条通道分别实现过滤器/处理器。
- 日志级别：从配置 server.log_level 读取（如 "INFO"），映射到 logging.INFO 等常量。

### Go 侧：std log 简单可靠
- 启动时创建 logs/go_logs/gateway_<时间戳>.log，io.MultiWriter(file, os.Stdout) 同时输出。
- 无结构化字段、无级别过滤，全部 log.Printf 输出到同一文件。
- 优雅关闭时打印 shutdown 信息。

### 前端侧：无专用日志框架
- 前端代码未发现集中式日志初始化逻辑，logs/frontend_logs/ 由外部脚本生成，不属于运行时日志系统的一部分。

## 4. 开发者约定与规则

- Python 模块必须通过 get_logger(__name__) 获取日志器，禁止直接 import structlog，统一走 nexus.core.logger 以保证全局配置生效。
- 使用关键字参数记录结构化字段：logger.info("User logged in", user_id="12345")，不要拼接字符串。
- 在请求入口处绑定上下文：使用 bind_context(request_id=..., cockpit_id=...)，请求结束调用 clear_context() 防止泄漏。
- 禁止在日志中明文输出密码、Token、API Key。现有脱敏处理器会处理常见字段名，但最好主动避免传入敏感键名。
- Go 网关新增日志使用 log.Printf，保持与现有风格一致，如需结构化可考虑迁移至 slog。
- 日志文件路径变更需同步更新 setup_logging 与文档，当前硬编码在项目根 logs/ 下，跨平台部署时需确认路径正确性。

## 5. 与可观测性生态的集成
- Loki：config/loki/loki-config.yml 提供采集配置，Python 侧 JSON 输出天然适配 Loki 解析。
- Prometheus：通过 /metrics 端点暴露指标，与日志形成互补（指标看趋势，日志查细节）。
- Langfuse：独立于日志系统的 LLM 调用追踪，可在 nexus.observability.langfuse 中扩展关联 trace_id 到日志上下文。

## 6. 已知局限
- Go 网关尚未采用结构化日志，难以与 Loki 进行字段级检索。
- 前端无统一日志收集方案，依赖浏览器控制台或外部工具。
- 日志轮转/保留策略由 data_retention 模块后台任务负责，但未集成 logrotate 等系统级工具。