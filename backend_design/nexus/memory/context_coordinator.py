# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Context Coordinator — 统一上下文管理门面 (Facade)

痛点解决:
  原架构中上下文管理分散在 4 个文件中:
    - memory/manager.py     → 长期记忆召回 (GraphRAG)
    - memory/compressor.py → 上下文压缩/滚动摘要
    - middleware/session_store.py   → 短期对话历史 (Redis)
    - middleware/redis_cache.py     → 语义缓存 (Redis KNN)

  调用方（supervisor_graph.py）需要分别 import 并协调这 4 个组件，
  跨模块状态传递复杂，压缩时机不一致可能导致上下文丢失。

改进方案:
  ContextCoordinator 作为门面，统一暴露 4 个核心操作:
    1. load_session() — 加载短期历史 + 滚动摘要
    2. recall() — 长期记忆召回 (委托 MemoryManager)
    3. build_context() — 组装 LLM 上下文消息 (委托 ContextCompressor)
    4. save_session() — 保存更新后的历史 + 摘要 + 语义缓存

  调用方只需 import ContextCoordinator，不再直接引用 4 个底层模块。
  Redis 降级时，SessionStore 自动切换内存模式，ContextCoordinator 透明处理。

Usage:
    from nexus.memory.context_coordinator import ContextCoordinator

    coordinator = ContextCoordinator(
        memory_manager=memory_manager,
        compressor=compressor,
        session_store=session_store,
        semantic_cache=semantic_cache,
    )

    # 1. 加载会话上下文
    history, summary = await coordinator.load_session(session_key)

    # 2. 召回长期记忆
    memories = await coordinator.recall(query, user_id)

    # 3. 组装 LLM 上下文消息
    messages, new_summary = await coordinator.build_context(
        system_prompt, user_input, history, summary, memory_str, search_ctx
    )

    # 4. 保存会话 + 写入语义缓存
    await coordinator.save_session(session_key, updated_history, new_summary)
    await coordinator.cache_response(query, response, user_id, has_side_effect=False)
"""

from __future__ import annotations

from typing import Any

from nexus.core.logger import get_logger
from nexus.memory.compressor import ContextCompressor
from nexus.memory.manager import MemoryManager
from nexus.middleware.redis_cache import SemanticCache
from nexus.middleware.session_store import SessionStore

logger = get_logger(__name__)


class ContextCoordinator:
    """统一上下文管理门面。

    协调 4 个底层组件，对外提供统一的上下文管理接口:
      - SessionStore: 短期对话历史 + 滚动摘要持久化
      - MemoryManager: 长期记忆召回 (GraphRAG 三路融合)
      - ContextCompressor: 上下文压缩 + 阈值摘要
      - SemanticCache: 语义缓存 (Redis KNN)

    设计原则:
      - Facade 模式: 不修改底层组件接口，仅统一调度
      - 降级透明: Redis 不可用时 SessionStore 自动降级内存模式
      - 状态一致: 压缩后的历史和摘要同步保存，确保跨轮次一致

    Args:
        memory_manager: 记忆管理器（长期记忆召回）
        compressor: 上下文压缩器
        session_store: 会话历史存储
        semantic_cache: 语义缓存
    """

    def __init__(
        self,
        memory_manager: MemoryManager | None = None,
        compressor: ContextCompressor | None = None,
        session_store: SessionStore | None = None,
        semantic_cache: SemanticCache | None = None,
    ):
        self.memory_manager = memory_manager
        self.compressor = compressor
        self.session_store = session_store
        self.semantic_cache = semantic_cache

    async def load_session(self, session_key: str) -> tuple[list[dict[str, str]], str]:
        """加载会话上下文: 短期历史 + 滚动摘要。

        统一从 SessionStore 获取，Redis 不可用时自动降级内存模式。

        Args:
            session_key: 会话标识 (session_id 或 user_id)

        Returns:
            (对话历史列表, 滚动摘要字符串)
        """
        if not self.session_store:
            return [], ""

        history = await self.session_store.async_get(session_key)
        summary = await self.session_store.async_get_summary(session_key)

        if summary:
            logger.debug(f"Session loaded: key={session_key}, history={len(history)} msgs, summary={len(summary)} chars")
        else:
            logger.debug(f"Session loaded: key={session_key}, history={len(history)} msgs, no summary")

        return history, summary

    async def recall(self, query: str, user_id: str, top_k: int = 5) -> list[str]:
        """长期记忆召回 (委托 MemoryManager)。

        使用 GraphRAG 三路融合（向量 + 图谱 + BM25）+ Rerank。
        渐进式披露: 简单查询返回 3 条，复杂查询返回 8 条。

        Args:
            query: 用户输入文本
            user_id: 用户 ID
            top_k: 返回记忆条数

        Returns:
            格式化的记忆字符串列表
        """
        if not self.memory_manager:
            return []

        try:
            return await self.memory_manager.recall(query, user_id, top_k)
        except Exception as e:
            logger.error(f"ContextCoordinator recall failed: {e}")
            return []

    def extract_key_context(self, history: list[dict[str, str]]) -> dict[str, str]:
        """从对话历史中提取关键上下文 (委托 ContextCompressor, 零 LLM 调用)。

        Args:
            history: 对话历史

        Returns:
            关键上下文字典 (location / preferences / identity)
        """
        if not self.compressor:
            return {}
        return self.compressor.extract_key_context(history)

    async def build_context(
        self,
        system_prompt: str,
        user_input: str,
        history: list[dict[str, str]],
        running_summary: str = "",
        memory_str: str = "",
        search_ctx: str = "",
    ) -> tuple[list[dict[str, str]], str]:
        """组装 LLM 上下文消息 (委托 ContextCompressor)。

        分级预算组装:
          Level 0: 未超标直接返回
          Level 1: 压缩检索上下文
          Level 2: trim_messages 裁剪历史 + LLM 摘要
          Level 3: 压缩记忆上下文

        Args:
            system_prompt: 系统提示词
            user_input: 用户输入
            history: 对话历史
            running_summary: 滚动摘要
            memory_str: 记忆字符串
            search_ctx: 检索上下文

        Returns:
            (组装后的消息列表, 更新后的滚动摘要)
        """
        if not self.compressor:
            # 无压缩器时简单组装
            messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
            if running_summary:
                messages.append({"role": "system", "content": f"【历史摘要】:\n{running_summary}"})
            if memory_str:
                messages[0]["content"] += f"\n{memory_str}"
            if search_ctx:
                messages.append({"role": "system", "content": f"【检索上下文】:\n{search_ctx}"})
            messages.extend(history)
            messages.append({"role": "user", "content": user_input})
            return messages, running_summary

        return await self.compressor.build_context(
            system_prompt, user_input, history, running_summary, memory_str, search_ctx
        )

    async def save_session(
        self,
        session_key: str,
        history: list[dict[str, str]],
        summary: str = "",
    ) -> None:
        """保存会话上下文: 短期历史 + 滚动摘要。

        统一写入 SessionStore，确保历史和摘要同步保存。
        Redis 不可用时自动降级内存模式。

        Args:
            session_key: 会话标识
            history: 更新后的对话历史
            summary: 更新后的滚动摘要
        """
        if not self.session_store:
            return

        try:
            await self.session_store.async_set(session_key, history)
            if summary:
                await self.session_store.async_set_summary(session_key, summary)
        except Exception as e:
            logger.error(f"ContextCoordinator save_session failed: {e}")

    async def check_cache(
        self, query: str, user_id: str = ""
    ) -> dict[str, Any] | None:
        """检查语义缓存 (委托 SemanticCache)。

        Args:
            query: 用户查询
            user_id: 用户 ID

        Returns:
            缓存命中时返回响应字典，未命中返回 None
        """
        if not self.semantic_cache or not self.semantic_cache.is_enabled:
            return None

        try:
            return await self.semantic_cache.get(query, user_id)
        except Exception as e:
            logger.error(f"ContextCoordinator cache check failed: {e}")
            return None

    async def cache_response(
        self,
        query: str,
        response: dict[str, Any],
        user_id: str = "",
        has_side_effect: bool = False,
        ttl: int = 0,
    ) -> None:
        """写入语义缓存 (委托 SemanticCache)。

        安全设计: has_side_effect=True 的响应（车控指令）永不写入缓存。

        Args:
            query: 用户查询
            response: 响应字典
            user_id: 用户 ID
            has_side_effect: 是否有副作用 (车控=True 时禁止缓存)
            ttl: 缓存 TTL 秒数
        """
        if not self.semantic_cache or not self.semantic_cache.is_enabled:
            return

        try:
            await self.semantic_cache.set(
                query, response, user_id, ttl=ttl, has_side_effect=has_side_effect
            )
        except Exception as e:
            logger.error(f"ContextCoordinator cache_response failed: {e}")

    async def delete_session(self, session_key: str, user_id: str = "") -> None:
        """删除会话: 清理短期历史 + 摘要 + 语义缓存。

        统一清理，确保用户删除对话时所有相关数据被清除。

        Args:
            session_key: 会话标识
            user_id: 用户 ID (用于清理语义缓存)
        """
        if self.session_store:
            try:
                await self.session_store.async_delete(session_key)
            except Exception as e:
                logger.error(f"ContextCoordinator delete session failed: {e}")

        if self.semantic_cache and user_id:
            try:
                await self.semantic_cache.delete_by_user(user_id)
            except Exception as e:
                logger.error(f"ContextCoordinator delete cache failed: {e}")
