# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Session Store — 基于 Redis 的会话历史持久化

将会话历史从内存 dict 迁移到 Redis，解决:
  1. 多实例部署下会话不共享
  2. 服务重启后会话丢失

降级策略: Redis 不可用时自动降级为内存 dict，保证服务可用。

增强功能:
  - 新增 running_summary（滚动摘要）持久化
  - 对话历史被阈值压缩后，摘要跨轮次保存，不丢失上下文
  - 摘要与历史共享同一 session_key，独立存储互不干扰
"""

from __future__ import annotations

import json

import redis.asyncio as aioredis

from nexus.config import get_config
from nexus.core.logger import get_logger

logger = get_logger(__name__)

# 会话历史在 Redis 中的前缀
_SESSION_PREFIX = "nexus:session:"
# 滚动摘要在 Redis 中的前缀
_SUMMARY_PREFIX = "nexus:summary:"
# 默认保留最近 20 条对话历史（实际值从 MemoryConfig.max_history_len 读取）
_DEFAULT_MAX_HISTORY = 20
# 会话过期时间 (秒)，默认 24 小时
_SESSION_TTL = 86400


class SessionStore:
    """Redis 会话历史存储 (带内存降级)。

    优先使用 Redis 持久化会话历史，Redis 不可用时降级为内存 dict。
    每个会话保留最近 max_history_len 条对话（从 MemoryConfig 读取），超时自动过期。

    同时管理滚动摘要 (running_summary)，对话历史被阈值压缩后
    产生的摘要跨轮次持久化，确保压缩后的上下文不丢失。

    Attributes:
        _redis: Redis 客户端
        _fallback: 内存降级存储 (Redis 不可用时使用)
        _summary_fallback: 摘要的内存降级存储
    """

    def __init__(self, redis_client: aioredis.Redis | None = None):
        self._redis: aioredis.Redis | None = redis_client
        self._fallback: dict[str, list[dict[str, str]]] = {}
        # 滚动摘要的内存降级存储
        self._summary_fallback: dict[str, str] = {}
        # 从 MemoryConfig 读取历史保留条数（可通过 .env 调整）
        try:
            self._max_history = get_config().memory.max_history_len
        except Exception:
            self._max_history = _DEFAULT_MAX_HISTORY

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

    def get(self, session_key: str) -> list[dict[str, str]]:
        """同步获取会话历史 (内存降级模式)。

        Redis 模式请使用 async_get。
        """
        if not self._redis:
            return self._fallback.get(session_key, [])
        return []  # Redis 模式下不应调用此方法

    async def async_get(self, session_key: str) -> list[dict[str, str]]:
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

    async def async_delete(self, session_key: str) -> bool:
        """异步删除会话历史和滚动摘要（用户删除对话时调用）。

        清理 Redis 中的短期记忆和滚动摘要，同时清理内存降级存储中的对应数据。
        释放该会话占用的所有短期记忆资源。

        Args:
            session_key: 会话标识 (session_id)

        Returns:
            是否成功删除（True=已删除，False=不存在或失败）
        """
        deleted = False

        # 清理 Redis 中的短期记忆
        if self._redis:
            try:
                result = await self._redis.delete(_SESSION_PREFIX + session_key)
                # 同时清理滚动摘要
                await self._redis.delete(_SUMMARY_PREFIX + session_key)
                deleted = result > 0
            except Exception as e:
                logger.error(f"SessionStore delete (redis) failed: {e}")

        # 清理内存降级存储
        if session_key in self._fallback:
            del self._fallback[session_key]
            deleted = True
        # 清理摘要的内存降级存储
        if session_key in self._summary_fallback:
            del self._summary_fallback[session_key]

        if deleted:
            logger.info(f"SessionStore: short-term memory deleted for session '{session_key}'")

        return deleted

    async def async_set(self, session_key: str, history: list[dict[str, str]]) -> None:
        """异步保存会话历史 (只保留最近 max_history_len 条)。

        Args:
            session_key: 会话标识
            history: 对话历史列表
        """
        # 截断到最近 max_history_len 条（从 MemoryConfig 读取）
        trimmed = history[-self._max_history:]

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

    async def list_sessions(self) -> dict[str, dict]:
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

    # ============================================================
    # 滚动摘要 (running_summary) 持久化
    # ============================================================

    async def async_get_summary(self, session_key: str) -> str:
        """异步获取会话的滚动摘要。

        滚动摘要是阈值压缩后产生的对话摘要，跨轮次持久化。
        当对话历史被压缩后，摘要保留了旧对话的关键信息。

        Args:
            session_key: 会话标识 (session_id 或 user_id)

        Returns:
            滚动摘要字符串，无摘要时返回空字符串
        """
        if not self._redis:
            return self._summary_fallback.get(session_key, "")

        try:
            data = await self._redis.get(_SUMMARY_PREFIX + session_key)
            if data:
                return data
            return ""
        except Exception as e:
            logger.error(f"SessionStore get_summary failed: {e}")
            return self._summary_fallback.get(session_key, "")

    async def async_set_summary(self, session_key: str, summary: str) -> None:
        """异步保存会话的滚动摘要。

        将阈值压缩后产生的滚动摘要持久化到 Redis，
        与会话历史共享相同的 TTL，确保同步过期。

        Args:
            session_key: 会话标识
            summary: 滚动摘要文本
        """
        if not summary:
            # 空摘要时删除已有摘要
            if self._redis:
                try:
                    await self._redis.delete(_SUMMARY_PREFIX + session_key)
                except Exception:
                    pass
            self._summary_fallback.pop(session_key, None)
            return

        if not self._redis:
            self._summary_fallback[session_key] = summary
            return

        try:
            await self._redis.setex(
                _SUMMARY_PREFIX + session_key,
                _SESSION_TTL,
                summary,
            )
        except Exception as e:
            logger.error(f"SessionStore set_summary failed: {e}")
            self._summary_fallback[session_key] = summary

    @property
    def is_redis_mode(self) -> bool:
        """是否使用 Redis 模式"""
        return self._redis is not None
