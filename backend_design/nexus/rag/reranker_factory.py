# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Reranker Factory — 重排服务工厂

本地化降级改造后仅支持本地 BGE CrossEncoder 或跳过重排。
云端硅基流动 Reranker 实现已删除，provider 字段保留向后兼容但忽略 cloud 取值。

可选模式:
  - local: 本地 BGE CrossEncoder (需下载模型)
  - none:  跳过重排 (省资源)
"""

from __future__ import annotations

from nexus.config import get_config
from nexus.core.logger import get_logger
from nexus.rag.reranker import LocalReranker
from nexus.rag.reranker_base import BaseReranker

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


def build_reranker() -> BaseReranker | None:
    """构建重排服务实例。

    本地化降级后仅支持 local / none，cloud 取值自动降级为 local。

    Returns:
        BaseReranker 实例, 或 NoneReranker (provider=none)
    """
    provider = get_config().providers.normalized()["reranker"]

    if provider == "none":
        logger.info("Reranker provider: none (disabled)")
        return NoneReranker()

    # 默认 local（cloud 取值也已降级为 local）
    if provider == "cloud":
        logger.warning(
            "Reranker provider=cloud is deprecated after localization, "
            "falling back to local BGE"
        )
    logger.info("Reranker provider: local BGE (固定本地)")
    return LocalReranker()
