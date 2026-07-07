"""
Langfuse Tracing — 可观测性追踪
未安装 Langfuse 或未配置时自动降级为空操作
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from contextlib import contextmanager

from nexus.config import get_config
from nexus.core.logger import get_logger

logger = get_logger(__name__)


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
