# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Session Store — 基于 Redis 的会话历史持久化

将会话历史从内存 dict 迁移到 Redis，解决:
  1. 多实例部署下会话不共享
  2. 服务重启后会话丢失

降级策略: Redis 不可用时自动降级为内存 dict，保证服务可用。
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional

import redis.asyncio as aioredis

from nexus.config import get_config
from nexus.core.logger import get_logger

logger = get_logger(__name__)

# 会话历史在 Redis 中的前缀
_SESSION_PREFIX = "nexus:session:"
# 默认保留最近 20 条对话历史
_MAX_HISTORY = 20
# 会话过期时间 (秒)，默认 24 小时
_SESSION_TTL = 86400


class SessionStore:
    """Redis 会话历史存储 (带内存降级)。

    优先使用 Redis 持久化会话历史，Redis 不可用时降级为内存 dict。
    每个会话保留最近 _MAX_HISTORY 条对话，超时自动过期。

    Attributes:
        _redis: Redis 客户端
        _fallback: 内存降级存储 (Redis 不可用时使用)
    """

    def __init__(self, redis_client: Optional[aioredis.Redis] = None):
        self._redis: Optional[aioredis.Redis] = redis_client
        self._fallback: Dict[str, List[Dict[str, str]]] = {}

    async def connect(self) -> None:
        """连接 Redis"""
        if self._redis:
            return
        try:
            config = get_config().redis
            self._redis = aioredis.from_url(config.url, decode_responses=True)
            await self._redis.ping()
            logger.info("SessionStore connected to Redis")
        except Exception as e:
            logger.warning(f"SessionStore Redis connection failed, using memory fallback: {e}")
            self._redis = None

    def get(self, session_key: str) -> List[Dict[str, str]]:
        """同步获取会话历史 (内存降级模式)。

        Redis 模式请使用 async_get。
        """
        if not self._redis:
            return self._fallback.get(session_key, [])
        return []  # Redis 模式下不应调用此方法

    async def async_get(self, session_key: str) -> List[Dict[str, str]]:
        """异步获取会话历史。

        Args:
            session_key: 会话标识 (session_id 或 user_id)

        Returns:
            对话历史列表，格式为 [{"role": "user", "content": "..."}, ...]
        """
        if not self._redis:
            return self._fallback.get(session_key, [])

        try:
            data = await self._redis.get(_SESSION_PREFIX + session_key)
            if data:
                return json.loads(data)
            return []
        except Exception as e:
            logger.error(f"SessionStore get failed: {e}")
            return self._fallback.get(session_key, [])

    async def async_set(self, session_key: str, history: List[Dict[str, str]]) -> None:
        """异步保存会话历史 (只保留最近 _MAX_HISTORY 条)。

        Args:
            session_key: 会话标识
            history: 对话历史列表
        """
        # 截断到最近 _MAX_HISTORY 条
        trimmed = history[-_MAX_HISTORY:]

        if not self._redis:
            self._fallback[session_key] = trimmed
            return

        try:
            await self._redis.setex(
                _SESSION_PREFIX + session_key,
                _SESSION_TTL,
                json.dumps(trimmed, ensure_ascii=False),
            )
        except Exception as e:
            logger.error(f"SessionStore set failed: {e}")
            self._fallback[session_key] = trimmed

    async def list_sessions(self) -> Dict[str, dict]:
        """列出所有活跃会话 (用于管理接口)"""
        if not self._redis:
            return {
                key: {
                    "message_count": len(history),
                    "last_message": history[-1].get("content", "")[:50] if history else "",
                }
                for key, history in self._fallback.items()
            }

        try:
            keys = await self._redis.keys(_SESSION_PREFIX + "*")
            sessions = {}
            for key in keys:
                session_key = key.replace(_SESSION_PREFIX, "")
                data = await self._redis.get(key)
                if data:
                    history = json.loads(data)
                    sessions[session_key] = {
                        "message_count": len(history),
                        "last_message": history[-1].get("content", "")[:50] if history else "",
                    }
            return sessions
        except Exception as e:
            logger.error(f"SessionStore list failed: {e}")
            return {}

    async def close(self) -> None:
        """关闭 Redis 连接"""
        if self._redis:
            await self._redis.close()

    @property
    def is_redis_mode(self) -> bool:
        """是否使用 Redis 模式"""
        return self._redis is not None
