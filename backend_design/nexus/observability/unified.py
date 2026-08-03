# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Unified Observability — 统一可观测性门面

痛点解决:
  原架构中可观测性分散在 4 个文件中:
    - core/logger.py              → structlog 结构化日志
    - observability/langfuse.py    → LLM 调用链路追踪
    - observability/metrics.py      → Prometheus 指标采集
    - observability/data_retention.py → 数据保留策略自动清理

  日志格式未完全统一: structlog (JSON/Console) 和 stdlib logging (uvicorn)
  使用不同的 Formatter，导致 Loki 采集时格式不一致。

改进方案:
  ObservabilityHub 作为统一门面，提供:
    1. 统一初始化: setup() 一次性配置日志 + 指标 + 追踪 + 数据保留
    2. 统一日志入口: log() 方法，自动携带 trace_id 和上下文
    3. 统一追踪入口: trace() / span() 上下文管理器
    4. 统一指标入口: record_agent_call() / record_skill_exec() 等便捷方法
    5. 统一关闭: shutdown() 刷新所有缓冲区

  日志格式统一: structlog 和 stdlib logging 统一使用相同的时间戳格式和字段结构。

Usage:
    from nexus.observability.unified import get_observability

    obs = get_observability()
    obs.setup()  # 初始化（在 main.py 启动时调用一次）

    # 日志
    obs.log("info", "User request received", user_id="12345")

    # 追踪
    with obs.trace("supervisor-node"):
        ...

    # 指标
    obs.record_agent_call("supervisor", "ok", latency_ms=120)

    # 关闭
    await obs.shutdown()
"""

from __future__ import annotations

import contextlib
from collections.abc import Generator
from typing import Any

from nexus.core.logger import (
    bind_context,
    clear_context,
    get_logger,
    setup_logging,
)
from nexus.observability.data_retention import DataRetentionManager, get_retention_manager
from nexus.observability.langfuse import LangfuseMonitor, observe, update_current_span
from nexus.observability.metrics import (
    AGENT_INVOCATIONS,
    AGENT_LATENCY,
    CACHE_HITS,
    CACHE_MISSES,
    LLM_CALLS,
    LLM_LATENCY,
    RAG_LATENCY,
    RAG_RETRIEVALS,
    REQUEST_COUNT,
    REQUEST_LATENCY,
    SKILL_EXECUTIONS,
    init_metrics,
)


class ObservabilityHub:
    """统一可观测性门面。

    统一管理日志 (structlog)、追踪 (Langfuse)、指标 (Prometheus)、数据保留。

    设计原则:
      - 门面模式: 不修改底层组件接口，仅统一调度
      - 降级透明: Langfuse 未配置时自动降级为空操作
      - 上下文绑定: request_id / user_id 自动传播到日志和追踪

    Attributes:
        logger: structlog 日志器
        langfuse: Langfuse 追踪监控器
        retention: 数据保留管理器
    """

    def __init__(self) -> None:
        self.logger = get_logger("nexus.observability")
        self.langfuse = LangfuseMonitor()
        self.retention: DataRetentionManager | None = None
        self._initialized = False

    def setup(self) -> None:
        """一次性初始化所有可观测性组件。

        在 main.py 启动时调用:
          1. 初始化 structlog 日志配置 (统一 JSON 格式)
          2. 初始化 Prometheus 指标
          3. Langfuse 追踪自动检测配置（在 LangfuseMonitor.__init__ 中完成）
        """
        if self._initialized:
            return

        # 1. 日志初始化（统一 structlog + stdlib 格式）
        setup_logging()

        # 2. 指标初始化
        init_metrics()

        self._initialized = True
        self.logger.info("Observability hub initialized (logging + metrics + tracing)")

    async def start_retention(self) -> None:
        """启动数据保留策略后台清理任务。"""
        if self.retention is None:
            self.retention = get_retention_manager()
            await self.retention.start()
            self.logger.info("Data retention manager started")

    async def shutdown(self) -> None:
        """关闭所有可观测性组件，刷新缓冲区。"""
        if self.retention:
            await self.retention.stop()

        if self.langfuse.enabled:
            self.langfuse.flush()

        self.logger.info("Observability hub shutdown complete")

    # ============================================================
    # 统一日志入口
    # ============================================================

    def log(self, level: str, event: str, **kwargs: Any) -> None:
        """统一日志入口。

        自动通过 structlog 输出，携带上下文变量 (request_id / user_id)。

        Args:
            level: 日志级别 (debug / info / warning / error)
            event: 日志事件描述
            **kwargs: 附加字段
        """
        log_fn = getattr(self.logger, level.lower(), self.logger.info)
        log_fn(event, **kwargs)

    def bind(self, **kwargs: Any) -> None:
        """绑定日志上下文变量（自动携带到后续所有日志）。

        常用于绑定 request_id、user_id、session_id 等追踪信息。

        Args:
            **kwargs: 上下文键值对
        """
        bind_context(**kwargs)

    def clear(self) -> None:
        """清除所有日志上下文变量。

        在请求结束时调用，防止上下文泄漏到下一个请求。
        """
        clear_context()

    # ============================================================
    # 统一追踪入口
    # ============================================================

    @contextlib.contextmanager
    def trace(self, name: str, **kwargs: Any) -> Generator[None, None, None]:
        """追踪上下文管理器。

        自动创建 Langfuse trace，未配置时降级为空操作。
        同时绑定日志上下文，使日志中自动携带 trace 信息。

        Args:
            name: 追踪名称
            **kwargs: 追踪元数据
        """
        trace = self.langfuse.start_trace(name=name, **kwargs)
        if trace and hasattr(trace, "id") and trace.id:
            self.bind(trace_id=trace.id)

        try:
            yield
        finally:
            if trace:
                self.langfuse.end_observation(trace)
            self.clear()

    def span(self, trace: Any = None, name: str = "", **kwargs: Any) -> Any:
        """开始一个追踪 span。"""
        return self.langfuse.start_span(trace=trace, name=name, **kwargs)

    def end_span(self, span: Any, output: Any = None, **kwargs: Any) -> None:
        """结束一个追踪 span。"""
        self.langfuse.end_observation(span, output=output, **kwargs)

    def update_span(self, metadata: dict | None = None, **kwargs: Any) -> None:
        """更新当前 span 的 metadata。"""
        update_current_span(metadata=metadata, **kwargs)

    # ============================================================
    # 统一指标入口
    # ============================================================

    def record_request(self, endpoint: str, method: str, status: str, latency_sec: float = 0) -> None:
        """记录 HTTP 请求指标。"""
        REQUEST_COUNT.labels(endpoint=endpoint, method=method, status=status).inc()
        if latency_sec > 0:
            REQUEST_LATENCY.labels(endpoint=endpoint).observe(latency_sec)

    def record_agent_call(self, agent_name: str, status: str, latency_sec: float = 0) -> None:
        """记录 Agent 节点调用指标。"""
        AGENT_INVOCATIONS.labels(agent_name=agent_name, status=status).inc()
        if latency_sec > 0:
            AGENT_LATENCY.labels(agent_name=agent_name).observe(latency_sec)

    def record_skill_exec(self, skill_name: str, status: str) -> None:
        """记录技能执行指标。"""
        SKILL_EXECUTIONS.labels(skill_name=skill_name, status=status).inc()

    def record_llm_call(self, model: str, status: str, latency_sec: float = 0) -> None:
        """记录 LLM 调用指标。"""
        LLM_CALLS.labels(model=model, status=status).inc()
        if latency_sec > 0:
            LLM_LATENCY.observe(latency_sec)

    def record_rag_retrieval(self, source: str, latency_sec: float = 0) -> None:
        """记录 RAG 检索指标。"""
        RAG_RETRIEVALS.labels(source=source).inc()
        if latency_sec > 0:
            RAG_LATENCY.observe(latency_sec)

    def record_cache_hit(self) -> None:
        """记录缓存命中。"""
        CACHE_HITS.inc()

    def record_cache_miss(self) -> None:
        """记录缓存未命中。"""
        CACHE_MISSES.inc()

    # ============================================================
    # observe 装饰器透传
    # ============================================================

    @staticmethod
    def observe(name: str | None = None, as_type: str | None = None, **kwargs: Any):
        """Langfuse observe 装饰器（透传）。"""
        return observe(name=name, as_type=as_type, **kwargs)


# 全局单例
_hub: ObservabilityHub | None = None


def get_observability() -> ObservabilityHub:
    """获取统一可观测性门面全局单例。"""
    global _hub
    if _hub is None:
        _hub = ObservabilityHub()
    return _hub
