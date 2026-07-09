"""
Reranker Factory — 重排服务工厂

根据 .env 的 RERANKER_PROVIDER 选择重排后端:
  - local: 本地 BGE CrossEncoder (需下载模型)
  - cloud: 硅基流动 Rerank API (免费 bge-reranker-v2-m3)
  - none:  跳过重排 (省成本)
"""

from __future__ import annotations

from typing import Optional

from nexus.config import get_config
from nexus.core.logger import get_logger
from nexus.rag.reranker_base import BaseReranker
from nexus.rag.reranker import LocalReranker
from nexus.rag.siliconflow_reranker import SiliconFlowReranker

logger = get_logger(__name__)


class NoneReranker(BaseReranker):
    """空重排器 — 直接原序返回前 top_k 条, 不做重排。

    对应 RERANKER_PROVIDER=none, 给"不想花钱也不想下模型"的场景。
    """

    def rerank(
        self,
        query: str,
        documents: list,
        text_field: str = "text",
        top_k: int = 5,
    ) -> list:
        return documents[:top_k]

    @property
    def is_available(self) -> bool:
        return True


def build_reranker() -> Optional[BaseReranker]:
    """根据 RERANKER_PROVIDER 配置选择重排后端。

    Returns:
        BaseReranker 实例, 或 None (provider=none 时返回 NoneReranker, 不返回 None 以保持调用方简单)
    """
    provider = get_config().providers.normalized()["reranker"]

    if provider == "none":
        logger.info("Reranker provider: none (disabled)")
        return NoneReranker()
    if provider == "cloud":
        logger.info("Reranker provider: SiliconFlow API")
        return SiliconFlowReranker()

    # 默认 local
    logger.info("Reranker provider: local BGE")
    return LocalReranker()
