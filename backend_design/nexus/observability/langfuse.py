# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Langfuse Tracing — 可观测性追踪
未安装 Langfuse 或未配置时自动降级为空操作

导出:
  - LangfuseMonitor: 手动 trace/span/generation 管理器
  - observe: 装饰器，自动追踪函数调用 (Langfuse v4 SDK)
  - update_current_span: 更新当前 span 的 metadata
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

from nexus.config import get_config
from nexus.core.logger import get_logger

logger = get_logger(__name__)

# ============================================================
# observe 装饰器 — 自动追踪函数调用
# ============================================================
# Langfuse v4 SDK 提供 @observe 装饰器，用于自动追踪 async/sync 函数。
# 当 Langfuse 未安装或未配置时，降级为透传装饰器（不影响函数执行）。

# 尝试从 langfuse 包导入 observe
_langfuse_observe: Callable | None = None
_langfuse_update_current_span: Callable | None = None

try:
    from langfuse import observe as _langfuse_observe  # type: ignore
    from langfuse import update_current_span as _langfuse_update_current_span  # type: ignore
    _LANGFUSE_SDK_AVAILABLE = True
except ImportError:
    _LANGFUSE_SDK_AVAILABLE = False


def observe(name: str | None = None, as_type: str | None = None, **kwargs: Any) -> Callable:
    """Langfuse observe 装饰器（兼容包装）。

    当 Langfuse SDK 可用且已配置时，使用真实装饰器进行追踪；
    否则返回透传装饰器，函数正常执行但不做追踪。

    Args:
        name: 追踪名称（默认使用函数名）
        as_type: 观察类型 ("span" / "generation" / "agent")
        **kwargs: 传递给 Langfuse observe 的额外参数

    Usage:
        @observe(name="supervisor-node")
        async def _supervisor_node(self, state): ...

        @observe(name="llm-tool-synthesis", as_type="generation")
        async def _synthesize_tool_response(self, state): ...
    """
    config = get_config().langfuse

    # Langfuse SDK 可用且已配置 → 使用真实装饰器
    if _langfuse_observe is not None and config.enabled:
        # as_type 参数映射: Langfuse v4 SDK 使用 as_type 参数
        if as_type:
            return _langfuse_observe(name=name, as_type=as_type, **kwargs)
        return _langfuse_observe(name=name, **kwargs)

    # 降级: 透传装饰器（不做任何追踪）
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **fkwargs):
            return await func(*args, **fkwargs)

        @functools.wraps(func)
        def sync_wrapper(*args, **fkwargs):
            return func(*args, **fkwargs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def update_current_span(metadata: dict | None = None, **kwargs: Any) -> None:
    """更新当前 Langfuse span 的 metadata。

    当 Langfuse SDK 可用且已配置时，更新当前 span；
    否则为空操作。

    Args:
        metadata: 要更新的 metadata 字典
        **kwargs: 额外参数（如 output, level 等）

    Usage:
        update_current_span(metadata={"model": "qwen", "latency_ms": 120})
    """
    config = get_config().langfuse

    if _langfuse_update_current_span is not None and config.enabled:
        try:
            if metadata:
                _langfuse_update_current_span(metadata=metadata, **kwargs)
            else:
                _langfuse_update_current_span(**kwargs)
        except Exception as e:
            logger.debug(f"update_current_span failed (non-critical): {e}")


class NullTrace:
    """空 Trace 对象 (Langfuse 未配置时的降级)"""

    def __init__(self, **kwargs: Any):
        self.id = ""

    def end(self, **kwargs: Any) -> None:
        pass


class NullSpan:
    """空 Span 对象"""

    def __init__(self, **kwargs: Any):
        self.id = ""

    def end(self, **kwargs: Any) -> None:
        pass


class NullGeneration:
    """空 Generation 对象"""

    def __init__(self, **kwargs: Any):
        self.id = ""

    def end(self, **kwargs: Any) -> None:
        pass


class LangfuseMonitor:
    """
    Langfuse 可观测性监控器
    自动检测配置，未配置时降级为空操作
    """

    def __init__(self, service_name: str = "nexus-cockpit"):
        self.config = get_config().langfuse
        self.service_name = service_name
        self._client = None

        if self.config.enabled:
            try:
                from langfuse import Langfuse
                self._client = Langfuse(
                    public_key=self.config.public_key,
                    secret_key=self.config.secret_key,
                    host=self.config.host,
                )
                logger.info("Langfuse tracing enabled")
            except ImportError:
                logger.warning("langfuse not installed, tracing disabled")
            except Exception as e:
                logger.warning(f"Langfuse init failed: {e}")

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def start_trace(self, name: str = "", **kwargs: Any) -> Any:
        """开始一个 trace"""
        if not self._client:
            return NullTrace(**kwargs)
        try:
            return self._client.trace(name=name, **kwargs)
        except Exception as e:
            logger.error(f"Langfuse trace start failed: {e}")
            return NullTrace(**kwargs)

    def start_span(self, trace: Any = None, name: str = "", **kwargs: Any) -> Any:
        """开始一个 span"""
        if not self._client or isinstance(trace, NullTrace):
            return NullSpan(**kwargs)
        try:
            return trace.span(name=name, **kwargs)
        except Exception as e:
            logger.error(f"Langfuse span start failed: {e}")
            return NullSpan(**kwargs)

    def start_generation(self, trace: Any = None, name: str = "", **kwargs: Any) -> Any:
        """开始一个 generation 记录"""
        if not self._client or isinstance(trace, NullTrace):
            return NullGeneration(**kwargs)
        try:
            return trace.generation(name=name, **kwargs)
        except Exception as e:
            logger.error(f"Langfuse generation start failed: {e}")
            return NullGeneration(**kwargs)

    @staticmethod
    def end_observation(observation: Any, output: Any = None, **kwargs: Any) -> None:
        """结束一个观察 (span/generation/trace)"""
        if observation is None or isinstance(observation, (NullTrace, NullSpan, NullGeneration)):
            return
        try:
            if hasattr(observation, "end"):
                observation.end(output=output, **kwargs)
        except Exception as e:
            logger.error(f"Langfuse end observation failed: {e}")

    def flush(self) -> None:
        """刷新缓冲区"""
        if self._client:
            try:
                self._client.flush()
            except Exception:
                pass
