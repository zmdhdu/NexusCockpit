"""
AuraDB Graph Store — Neo4j AuraDB 云端图谱存储

AuraDB 是 Neo4j 官方云托管, 使用同一个 neo4j Python driver。
与 Neo4jGraphStore 的唯一区别: connect() 使用 neo4j+s:// 加密 URI + 云端密码。

配置 (.env, GRAPH_STORE_PROVIDER=cloud):
    NEO4J_URI=neo4j+s://<your-db-id>.databases.neo4j.io
    NEO4J_PASSWORD=<aura password>
"""

from __future__ import annotations

from nexus.core.logger import get_logger
from nexus.rag.graph_store import Neo4jGraphStore

logger = get_logger(__name__)


class AuraGraphStore(Neo4jGraphStore):
    """Neo4j AuraDB 云端图谱存储。

    继承 Neo4jGraphStore 的全部 Cypher 逻辑, 仅连接参数走云端。
    AuraDB 使用 neo4j+s 协议 (TLS 加密), driver 自动处理, 无需额外代码。
    """

    def connect(self) -> None:
        """连接 AuraDB 云端。"""
        logger.info(
            "Connecting to Neo4j AuraDB",
            uri=self.config.uri,
            user=self.config.user,
        )
        # 父类 connect() 已处理 driver 创建 + verify_connectivity + 约束初始化
        super().connect()
        logger.info("AuraDB graph store connected")
