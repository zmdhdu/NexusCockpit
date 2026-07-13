# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Zilliz Cloud Vector Store — Zilliz 云端向量存储

Zilliz 是 Milvus 的官方云托管, pymilvus 客户端完全通用。
与 MilvusVectorStore 的唯一区别: connect() 使用云端 URI + Token。

配置 (.env, VECTOR_STORE_PROVIDER=cloud):
    MILVUS_URI=https://<cluster>.zillizcloud.com
    MILVUS_TOKEN=<zilliz api key>
"""

from __future__ import annotations

from nexus.core.logger import get_logger
from nexus.rag.vector_store import MilvusVectorStore

logger = get_logger(__name__)


class ZillizVectorStore(MilvusVectorStore):
    """Zilliz Cloud 向量存储。

    继承 MilvusVectorStore 的全部逻辑, 仅在 connect() 时使用云端连接参数。
    Zilliz 与 Milvus 协议一致, 无需重写任何检索/写入方法。
    """

    def connect(self) -> None:
        """连接 Zilliz Cloud。

        复用父类 connect(), 但日志标注为 Zilliz 云端。
        连接参数 (uri/token) 来自 config.milvus, 由 .env 的 MILVUS_URI/MILVUS_TOKEN 提供。
        """
        logger.info(
            "Connecting to Zilliz Cloud",
            uri=self.config.uri,
            has_token=bool(self.config.token),
        )
        # 父类 connect() 已处理连接 + 集合初始化 + 异常
        super().connect()
        if self.is_connected:
            logger.info("Zilliz Cloud vector store connected")
