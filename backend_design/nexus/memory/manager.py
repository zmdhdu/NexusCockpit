# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Memory Manager — 统一记忆管理器

核心特性:
  - recall 使用 GraphRAGRetriever 的三路融合（向量+图谱+BM25）+ Rerank
  - 对话历史向量化存储：将重要对话片段嵌入 Milvus，支持语义检索
  - 渐进式披露：根据 query 复杂度动态调整召回数量
  - 用户习惯注入：从 MySQL user_habits 表加载习惯，丰富记忆上下文

架构:
  短期记忆 (Redis SessionStore) → 原始对话历史，即时上下文
  长期记忆 (Milvus + Neo4j)     → 语义向量召回 + 关系图谱
  习惯记忆 (MySQL user_habits)  → 用户偏好统计，频次加权
  检索管道: 三路召回 → RRF 融合 → Rerank 重排 → 渐进式披露
"""

from __future__ import annotations

import asyncio
from typing import Any

from openai import AsyncOpenAI

from nexus.config import get_config
from nexus.core.logger import get_logger
from nexus.memory.conflict import ConflictDetector, MemoryExtractor
from nexus.rag.graph_store import Neo4jGraphStore
from nexus.rag.reranker_base import BaseReranker
from nexus.rag.reranker_factory import build_reranker
from nexus.rag.retriever import GraphRAGRetriever
from nexus.rag.vector_store import MilvusVectorStore

logger = get_logger(__name__)


class MemoryManager:
    """统一记忆管理器。

    协调三层记忆：
    - 短期记忆: Redis SessionStore（由外部 chat.py 管理，传入 history）
    - 长期记忆: Milvus 向量 + Neo4j 图谱（本类管理）
    - 习惯记忆: MySQL user_habits（本类管理读取）

    检索管道:
        1. GraphRAGRetriever 三路召回（向量+图谱+BM25）
        2. RRF 融合排序
        3. Rerank 重排（bge-reranker-v2-m3）
        4. 渐进式披露：简单 query 返回 3 条，复杂 query 返回 8 条

    Args:
        vector_store: Milvus 向量存储
        graph_store: Neo4j 图谱存储
        llm_client: LLM 客户端（记忆提取用）
        reranker: Rerank 服务（可选，自动初始化）
    """

    def __init__(
        self,
        vector_store: MilvusVectorStore | None = None,
        graph_store: Neo4jGraphStore | None = None,
        llm_client: AsyncOpenAI | None = None,
        reranker: BaseReranker | None = None,
    ):
        self.config = get_config().llm
        self.vector_store = vector_store or MilvusVectorStore()
        self.graph_store = graph_store or Neo4jGraphStore()
        self.llm_client = llm_client or AsyncOpenAI(
            api_key=self.config.ark_api_key,
            base_url=self.config.ark_base_url,
        )
        self.extractor = MemoryExtractor(self.llm_client)
        self.conflict_detector = ConflictDetector(self.llm_client)

        # 使用 GraphRAGRetriever 的三路融合+Rerank 管道
        self.reranker = reranker or build_reranker()
        self.retriever = GraphRAGRetriever(
            vector_store=self.vector_store,
            graph_store=self.graph_store,
            reranker=self.reranker,
            enable_rerank=True,
            enable_bm25=True,
        )

    def connect(self) -> None:
        """连接所有存储后端。"""
        self.vector_store.connect()
        self.graph_store.connect()
        logger.info("Memory manager connected (GraphRAG + Rerank pipeline)")

    async def recall(
        self, query: str, user_id: str, top_k: int = 5
    ) -> list[str]:
        """记忆召回 — 使用 GraphRAG 三路融合 + Rerank。

        渐进式披露策略:
            - 简单查询（车控/导航指令）: top_k=3，快速返回
            - 复杂查询（闲聊/搜索/习惯）: top_k=8，深度召回
            - 默认: top_k=5

        Args:
            query: 用户输入文本
            user_id: 用户 ID
            top_k: 返回记忆条数

        Returns:
            格式化的记忆字符串列表
        """
        # 渐进式披露：根据 query 复杂度调整召回深度
        adjusted_k = self._progressive_disclosure(query, top_k)

        # 使用 GraphRAGRetriever 的三路融合 + Rerank 管道
        try:
            results = await self.retriever.retrieve_memories(
                query, user_id, top_k=adjusted_k, graph_depth=1
            )
        except Exception as e:
            logger.error(f"GraphRAG recall failed, falling back to vector-only: {e}")
            results = await self.vector_store.search_memory(query, user_id, top_k=adjusted_k)

        # 格式化记忆
        memories: list[str] = []
        for r in results:
            text = r.get("text", "") or r.get("item_name", "")
            source = r.get("source", "vector")
            score = r.get("rerank_score", r.get("rrf_score", r.get("score", 0)))
            if text:
                if source == "vector":
                    tag = "语义"
                elif source == "graph":
                    tag = "图谱"
                elif source == "bm25":
                    tag = "全文"
                else:
                    tag = source
                memories.append(f"[{tag}] {text} (score={score:.3f})")

        # 追加用户习惯记忆（从 MySQL 加载）
        habits = await self._load_user_habits(user_id)
        if habits:
            memories.extend(habits)

        return memories

    def _progressive_disclosure(self, query: str, default_k: int) -> int:
        """渐进式披露：根据查询复杂度动态调整召回数量。

        简单指令（车控/导航）不需要深度记忆召回，减少延迟。
        复杂查询（闲聊/搜索/习惯）需要更多上下文。

        Args:
            query: 用户输入
            default_k: 默认召回数

        Returns:
            调整后的召回数
        """
        _query_lower = query.lower()

        # 简单指令：车控、导航 → 快速返回 3 条
        simple_keywords = (
            "空调", "车窗", "座椅", "音量", "播放", "暂停", "下一首",
            "导航到", "带我", "去", "车况", "胎压",
        )
        if any(k in query for k in simple_keywords) and len(query) < 20:
            return min(3, default_k)

        # 复杂查询：闲聊、搜索、习惯 → 深度召回 8 条
        complex_keywords = (
            "我喜欢", "习惯", "记得", "上次", "之前", "推荐",
            "为什么", "怎么样", "帮我", "搜索", "查一下",
        )
        if any(k in query for k in complex_keywords):
            return max(8, default_k)

        return default_k

    async def _load_user_habits(self, user_id: str) -> list[str]:
        """从 MySQL 加载用户习惯，格式化为记忆字符串。

        习惯记忆是频次加权的，高频操作会被优先注入。

        Args:
            user_id: 用户 ID

        Returns:
            习惯记忆字符串列表
        """
        try:
            from nexus.core.db_manager import get_db_manager
            db = get_db_manager()
            if not db.is_connected:
                return []
            habits = await db.get_user_habits(user_id)
            result = []
            for h in habits[:5]:  # 最多注入 5 条习惯
                key = h.get("habit_key", "")
                value = h.get("habit_value", "")
                count = h.get("hit_count", 0)
                if key and value and count > 0:
                    result.append(f"[习惯] {key}: {value} (使用{count}次)")
            return result
        except Exception as e:
            logger.error(f"Failed to load user habits: {e}")
            return []

    async def store_from_text(self, user_text: str, user_id: str) -> int:
        """从用户文本中提取记忆并存储到 Milvus + Neo4j。

        流程:
            1. LLM 提取三元组（主体-关系-客体）
            2. 冲突检测（新记忆 vs 现有记忆）
            3. 冲突裁决：DELETE 旧 / IGNORE 新 / NONE 无冲突
            4. 双向写入：Milvus 向量 + Neo4j 图谱

        注: 可通过 MEMORY_EXTRACTION_ENABLED=false 关闭以减少 LLM 调用。

        Args:
            user_text: 用户输入文本
            user_id: 用户 ID

        Returns:
            存储的记忆数量
        """
        # 记忆提取开关 — 关闭时跳过 LLM 提取和冲突检测
        from nexus.config import get_config
        if not get_config().llm.memory_extraction_enabled:
            logger.debug("Memory extraction skipped (disabled by config)")
            return 0

        triplets = await self.extractor.extract(user_text)
        if not triplets:
            return 0

        stored_count = 0
        for t in triplets:
            relation = t.get("relation", "")
            target = t.get("target", "")
            t_type = t.get("type", "Entity")

            if not relation or not target:
                continue

            fact_text = f"用户 {relation} {target}"

            # 检查冲突
            existing = await self.vector_store.search_memory(fact_text, user_id, top_k=10)

            # 如果是喜好类，额外检查过敏记忆
            if t_type == "Food" and relation == "LIKES":
                allergy_res = await self.vector_store.search_memory(
                    f"用户 ALLERGY {target}", user_id, top_k=3
                )
                existing_ids = {m["id"] for m in existing}
                for am in allergy_res:
                    if am["id"] not in existing_ids:
                        existing.append(am)

            decision = await self.conflict_detector.detect_conflict(
                fact_text, existing, user_input=user_text
            )

            if decision.get("action") == "IGNORE":
                continue

            # 联动删除冲突记忆
            ids_to_delete = decision.get("ids", [])
            if decision.get("action") == "DELETE" and ids_to_delete:
                self.vector_store.delete_memory_by_ids(ids_to_delete, user_id)
                for mid in ids_to_delete:
                    self.graph_store.delete_relation_by_mid(mid)

            # 双向写入
            milvus_id = await self.vector_store.insert_memory(fact_text, user_id)
            if milvus_id:
                self.graph_store.upsert_relation(user_id, relation, target, t_type, milvus_id)
                stored_count += 1

        if stored_count:
            logger.info(f"Stored {stored_count} memories for user={user_id}")

        return stored_count

    async def store_conversation(
        self, user_input: str, assistant_response: str, user_id: str, cockpit_id: str = ""
    ) -> None:
        """将完整对话向量化存储到 Milvus，支持后续语义检索。

        与 store_from_text 不同，这里存储的是完整对话上下文，
        而非提取后的三元组。适用于"用户之前问过类似问题"的场景。

        Args:
            user_input: 用户输入
            assistant_response: 助手回复
            user_id: 用户 ID
            cockpit_id: 座舱 ID（多租户隔离）
        """
        # 只存储有意义的对话（过滤短指令和纯车控）
        if len(user_input) < 5 or len(assistant_response) < 5:
            return
        # 跳过纯车控指令（这些通过 store_from_text 处理）
        if user_input.startswith(("打开", "关闭", "调高", "调低", "播放", "暂停")):
            return

        conversation_text = f"用户: {user_input[:500]}\n助手: {assistant_response[:500]}"
        try:
            await self.vector_store.insert_memory(conversation_text, user_id)
            logger.debug(f"Conversation vectorized and stored for user={user_id}")
        except Exception as e:
            logger.error(f"Failed to store conversation vector: {e}")

    def store_from_text_async(self, user_text: str, user_id: str) -> asyncio.Task | None:
        """在当前事件循环中非阻塞存储记忆（fire-and-forget）。

        注: 使用 asyncio.create_task() 在当前事件循环中调度，
        与 EmbeddingService 共享同一事件循环，避免跨循环错误。

        Args:
            user_text: 用户输入文本
            user_id: 用户 ID

        Returns:
            asyncio.Task 对象（可能为 None 如果无法获取事件循环）
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("No running event loop for store_from_text_async, skipping")
            return None

        task = loop.create_task(self._store_from_text_safe(user_text, user_id))
        task.add_done_callback(self._task_done_callback("memory_storage"))
        return task

    def store_conversation_async(
        self, user_input: str, assistant_response: str, user_id: str, cockpit_id: str = ""
    ) -> asyncio.Task | None:
        """非阻塞存储对话向量（fire-and-forget）。

        注: 使用 asyncio.create_task() 替代线程+新事件循环方案。

        Args:
            user_input: 用户输入
            assistant_response: 助手回复
            user_id: 用户 ID
            cockpit_id: 座舱 ID

        Returns:
            asyncio.Task 对象（可能为 None）
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("No running event loop for store_conversation_async, skipping")
            return None

        task = loop.create_task(
            self._store_conversation_safe(user_input, assistant_response, user_id, cockpit_id)
        )
        task.add_done_callback(self._task_done_callback("conversation_storage"))
        return task

    async def _store_from_text_safe(self, user_text: str, user_id: str) -> None:
        """store_from_text 的安全包装，捕获所有异常防止任务静默失败。"""
        try:
            await self.store_from_text(user_text, user_id)
        except Exception as e:
            logger.error(f"Background memory storage failed: {e}")

    async def _store_conversation_safe(
        self, user_input: str, assistant_response: str, user_id: str, cockpit_id: str
    ) -> None:
        """store_conversation 的安全包装，捕获所有异常防止任务静默失败。"""
        try:
            await self.store_conversation(user_input, assistant_response, user_id, cockpit_id)
        except Exception as e:
            logger.error(f"Background conversation storage failed: {e}")

    @staticmethod
    def _task_done_callback(label: str):
        """创建 task 完成回调，记录未捕获的异常。"""
        def _callback(task: asyncio.Task) -> None:
            if task.cancelled():
                return
            exc = task.exception()
            if exc:
                logger.error(f"Background task '{label}' failed: {exc}")
        return _callback

    def get_user_profile(self, user_id: str) -> dict[str, Any]:
        """获取用户完整画像（从 Neo4j 图谱）。"""
        return self.graph_store.get_user_profile(user_id)

    def close(self) -> None:
        """关闭所有连接。"""
        self.vector_store.disconnect()
        self.graph_store.close()
        logger.info("Memory manager closed")
