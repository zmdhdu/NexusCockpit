# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
多租户上下文 — 在请求级别传递 cockpit_id，实现自动隔离

使用 contextvars 实现协程安全的上下文传递，
所有中间件（缓存/限流/会话）自动读取当前 cockpit_id 做隔离。
"""

from __future__ import annotations

import contextvars

# 协程安全的上下文变量
_current_cockpit_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "cockpit_id", default="cockpit-01"
)

_current_user_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "user_id", default="default"
)


def set_cockpit_id(cockpit_id: str) -> None:
    """设置当前请求的座舱 ID。

    Args:
        cockpit_id: 座舱唯一标识，如 "cockpit-01"
    """
    _current_cockpit_id.set(cockpit_id)


def get_cockpit_id() -> str:
    """获取当前请求的座舱 ID。

    Returns:
        当前上下文中的座舱 ID，默认 "cockpit-01"
    """
    return _current_cockpit_id.get()


def set_user_id(user_id: str) -> None:
    """设置当前请求的用户 ID。

    Args:
        user_id: 用户唯一标识
    """
    _current_user_id.set(user_id)


def get_user_id() -> str:
    """获取当前请求的用户 ID。

    Returns:
        当前上下文中的用户 ID
    """
    return _current_user_id.get()


def get_cache_prefix() -> str:
    """获取当前座舱的 Redis key 前缀。

    Returns:
        如 "cockpit-01:" 用于 Redis key 隔离
    """
    return f"{get_cockpit_id()}:"


class CockpitContext:
    """上下文管理器 — 在 with/async with 中自动设置和恢复 cockpit_id。

    用法:
        async with CockpitContext("cockpit-02", "user_02"):
            # 在此作用域内，get_cockpit_id() 返回 "cockpit-02"
            await cache.get(query)
    """

    def __init__(self, cockpit_id: str, user_id: str = ""):
        self._cockpit_id = cockpit_id
        self._user_id = user_id
        self._token_cockpit: contextvars.Token | None = None
        self._token_user: contextvars.Token | None = None

    def __enter__(self):
        self._token_cockpit = _current_cockpit_id.set(self._cockpit_id)
        if self._user_id:
            self._token_user = _current_user_id.set(self._user_id)
        return self

    def __exit__(self, *args):
        if self._token_cockpit:
            _current_cockpit_id.reset(self._token_cockpit)
        if self._token_user:
            _current_user_id.reset(self._token_user)

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, *args):
        self.__exit__(*args)
