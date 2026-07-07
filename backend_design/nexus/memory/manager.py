"""
Memory Manager — 统一记忆管理器
协调向量记忆、图谱记忆、冲突检测和后台异步存储
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from nexus.config import get_config
from nexus.core.logger import get_logger
from nexus.memory.conflict import ConflictDetector, MemoryExtractor
from nexus.rag.graph_store import Neo4jGraphStore
from nexus.rag.vector_store import MilvusVectorStore

logger = get_logger(__name__)


class MemoryManager:
    """
    统一记忆管理器
    - recall: 双路召回 (向量 + 图谱)
    - store: 异步提取 → 冲突检测 → 向量+图谱双向写入
    - delete: 联动删除 (Milvus ID 绑定)
    """

    def __init__(
        self,
        vector_store: Optional[MilvusVectorStore] = None,
        graph_store: Optional[Neo4jGraphStore] = None,
        llm_client: Optional[AsyncOpenAI] = None,
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

    def connect(self) -> None:
        """连接所有存储后端"""
        self.vector_store.connect()
        self.graph_store.connect()
        logger.info("Memory manager connected to all backends")

    async def recall(self, query: str, user_id: str, top_k: int = 5) -> List[str]:
        """
        双路召回用户记忆
        返回格式化的记忆字符串列表
        """
        # 向量路
        vec_results = await self.vector_store.search_memory(query, user_id, top_k=top_k)
        # 图谱路
        graph_results = self.graph_store.search_user_graph(user_id, depth=1)

        # 合并去重
        memories: List[str] = []
        seen = set()

        for r in vec_results:
            text = r.get("text", "")
            if text and text not in seen:
                memories.append(f"[语义] {text}")
                seen.add(text)

        for r in graph_results:
            if r not in seen:
                memories.append(f"[图谱] {r}")
                seen.add(r)

        return memories

    async def store_from_text(self, user_text: str, user_id: str) -> int:
        """
        从用户文本中提取记忆并存储
        返回存储的记忆数量
        """
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

    def store_from_text_async(self, user_text: str, user_id: str) -> threading.Thread:
        """
        在守护线程中异步存储记忆（非阻塞）
        返回线程对象供调用方管理
        """

        def _run():
            try:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(self.store_from_text(user_text, user_id))
                loop.close()
            except Exception as e:
                logger.error(f"Background memory storage failed: {e}")

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return thread

    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """获取用户完整画像"""
        return self.graph_store.get_user_profile(user_id)

    def close(self) -> None:
        """关闭所有连接"""
        self.vector_store.disconnect()
        self.graph_store.close()
        logger.info("Memory manager closed")
