---
kind: logging_system
name: 结构化日志系统（Python structlog + Go 标准库）
category: logging_system
scope:
    - '**'
source_files:
    - backend_design/nexus/core/logger.py
    - backend_design/nexus/main.py
    - backend_design/nexus_gate/cmd/main.go
    - backend_design/nexus_gate/internal/ws/hub.go
    - config/loki/loki-config.yml
    - config/grafana/provisioning/dashboards/nexuscockpit-overview.json
---

## 系统概述

NexusCockpit 采用**双语言独立日志方案**：Python AI 后端使用 `structlog` 实现结构化 JSON 日志，Go 网关使用标准库 `log` 输出文本日志。两者均按日期分文件写入 `logs/` 目录，并通过中间件将请求上下文注入到日志中。

## Python 后端日志架构

### 核心组件
- **初始化入口**: `backend_design/nexus/core/logger.py` — 提供 `setup_logging()`、`get_logger()`、`bind_context()` 等统一接口
- **应用启动集成**: `backend_design/nexus/main.py` 的 `lifespan` 中调用 `setup_logging()`，确保在应用生命周期早期完成配置

### 日志格式与级别
- **开发环境** (`debug=True`): 彩色控制台输出，便于调试阅读
- **生产环境** (`debug=False`): JSON 格式输出，字段包含 `timestamp` (ISO 8601)、`level`、`logger_name`、`stack_info`、`exc_info` 以及业务自定义字段
- **日志级别**: 通过 `config.server.log_level` 配置，默认 INFO，支持 DEBUG/INFO/WARNING/ERROR 四级

### 结构化上下文绑定
```python
from nexus.core.logger import get_logger, bind_context
bind_context(request_id="abc123", user_id="user_001")
logger.info("Processing request")  # JSON 中包含 request_id 和 user_id 字段
```

### 输出目标
- **文件输出**: `logs/backend_logs/backend_YYYYMMDD_HHMMSS.log`，按时间戳命名
- **控制台输出**: 同时写入 stdout，便于容器化部署时采集
- **Uvicorn 兼容**: 显式为 `uvicorn`、`uvicorn.access`、`uvicorn.error` 添加 FileHandler，确保访问日志也写入文件

### 全局异常处理集成
FastAPI 全局异常处理器在捕获 `RateLimitError`、`AuthError`、`NexusError` 时记录对应级别的日志，并返回结构化错误响应。

## Go 网关日志方案

### 实现方式
- **标准库 log**: 使用 `log.SetOutput(io.MultiWriter(file, os.Stdout))` 同时输出到文件和标准输出
- **日志文件**: `logs/go_logs/gateway_YYYYMMDD_HHMMSS.log`，按日期分隔
- **日志格式**: 固定前缀 `time | file:line | level | message`，包含来源文件和行号信息

### 关键日志点
- 服务启动/关闭状态
- WebSocket 客户端连接/断开事件
- 后端连接失败重试
- 中间件健康检查结果

## 日志收集与存储

### 本地存储结构
```
logs/
├── backend_logs/     # Python 结构化日志 (JSON)
├── frontend_logs/    # 前端运行时日志
└── go_logs/          # Go 网关日志 (文本)
```

### 外部系统集成
- **Loki 配置**: `config/loki/loki-config.yml` 已预留配置文件位置
- **Grafana 仪表盘**: `config/grafana/provisioning/dashboards/nexuscockpit-overview.json` 提供日志概览面板
- **Prometheus 指标**: `/metrics` 端点暴露性能指标，与日志形成互补观测体系

## 开发者规范

1. **统一导入**: 所有模块通过 `from nexus.core.logger import get_logger` 获取日志器
2. **模块标识**: 使用 `logger = get_logger(__name__)` 自动携带模块名作为 logger 名称
3. **上下文追踪**: 在请求入口处使用 `bind_context(request_id=...)` 绑定请求级上下文
4. **结构化字段**: 使用关键字参数传递业务字段，如 `logger.info("User login", user_id="123")`
5. **级别选择**: 使用 `debug/info/warning/error` 方法，避免直接调用 `logging` 模块
6. **敏感信息**: 禁止在日志中输出密码、密钥等敏感数据，参考 main.py 中的 API Key 脱敏示例