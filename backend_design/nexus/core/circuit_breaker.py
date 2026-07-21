# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
熔断器模块 (Circuit Breaker)

熔断器是一种保护机制，防止故障级联扩散。工作原理类似电路中的保险丝:
  1. CLOSED (闭合): 正常工作，记录失败次数
  2. OPEN (断开): 连续失败超过阈值，拒绝所有请求，等待恢复
  3. HALF_OPEN (半开): 恢复期过后，放行一个试探请求; 成功则恢复，失败则继续断开

在 NexusCockpit 中的应用场景:
  - 云端 LLM API 连续失败 → 自动降级到本地模型
  - Milvus 连续不可用 → 降级到无向量检索模式
  - 车控服务连续超时 → 降级到 Mock 模式
"""

from __future__ import annotations

import time
from collections.abc import Callable
from enum import Enum
from typing import Any, TypeVar

from nexus.core.exceptions import CircuitBreakerError
from nexus.core.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    """熔断器状态枚举。

    Attributes:
        CLOSED: 闭合状态 — 正常放行请求
        OPEN: 断开状态 — 拒绝所有请求
        HALF_OPEN: 半开状态 — 放行试探性请求
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """异步熔断器实现。

    三状态转换逻辑:
        CLOSED --(失败次数>=阈值)--> OPEN
        OPEN --(等待 recovery_period)--> HALF_OPEN
        HALF_OPEN --(试探成功)--> CLOSED
        HALF_OPEN --(试探失败)--> OPEN

    Args:
        name: 熔断器名称 (用于日志标识)
        failure_threshold: 连续失败多少次后熔断 (默认 5 次)
        recovery_period: 熔断后等待多久才试探恢复 (秒，默认 30)
        half_open_max_calls: 半开状态最多放行几个请求 (默认 1)
    """

    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        recovery_period: float = 30.0,
        half_open_max_calls: int = 1,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_period = recovery_period
        self.half_open_max_calls = half_open_max_calls

        # 内部状态
        self._state = CircuitState.CLOSED
        self._failure_count = 0       # 连续失败计数
        self._success_count = 0       # 半开状态连续成功计数
        self._last_failure_time: float = 0  # 最近一次失败的时间戳
        self._half_open_calls = 0     # 半开状态已放行的请求数

    @property
    def state(self) -> CircuitState:
        """获取当前熔断器状态。

        如果当前是 OPEN 且已过恢复期，自动转为 HALF_OPEN。
        """
        if self._state == CircuitState.OPEN:
            # 检查是否已过恢复期
            if time.monotonic() - self._last_failure_time >= self.recovery_period:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                logger.info(f"CircuitBreaker[{self.name}] OPEN -> HALF_OPEN")
        return self._state

    async def call(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """执行受熔断器保护的异步调用。

        Args:
            func: 要执行的异步函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            func 的返回值

        Raises:
            CircuitBreakerError: 熔断器开启时拒绝请求
        """
        # OPEN 状态: 直接拒绝
        if self.state == CircuitState.OPEN:
            raise CircuitBreakerError(
                f"CircuitBreaker[{self.name}] is OPEN, rejecting request"
            )

        # HALF_OPEN 状态: 限制并发试探请求数
        if self.state == CircuitState.HALF_OPEN:
            if self._half_open_calls >= self.half_open_max_calls:
                raise CircuitBreakerError(
                    f"CircuitBreaker[{self.name}] HALF_OPEN limit reached"
                )
            self._half_open_calls += 1

        try:
            # 执行被保护的函数
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception:
            # 记录失败并可能触发熔断
            self._on_failure()
            raise

    def _on_success(self) -> None:
        """调用成功时的处理逻辑。"""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            # 半开状态下一次成功就恢复
            if self._success_count >= 1:
                self._reset()
                logger.info(f"CircuitBreaker[{self.name}] HALF_OPEN -> CLOSED (recovered)")
        else:
            # 闭合状态下成功，重置失败计数
            self._failure_count = 0

    def _on_failure(self) -> None:
        """调用失败时的处理逻辑。"""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._state == CircuitState.HALF_OPEN:
            # 半开状态试探失败，重新熔断
            self._state = CircuitState.OPEN
            self._success_count = 0
            logger.warning(f"CircuitBreaker[{self.name}] HALF_OPEN -> OPEN (probe failed)")
        elif self._failure_count >= self.failure_threshold:
            # 连续失败达到阈值，触发熔断
            self._state = CircuitState.OPEN
            logger.warning(
                f"CircuitBreaker[{self.name}] CLOSED -> OPEN "
                f"(failures={self._failure_count}/{self.failure_threshold})"
            )

    def _reset(self) -> None:
        """重置熔断器到闭合状态。"""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0

    def __repr__(self) -> str:
        return (
            f"CircuitBreaker(name={self.name}, state={self.state.value}, "
            f"failures={self._failure_count}/{self.failure_threshold})"
        )
