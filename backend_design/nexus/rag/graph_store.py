# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Neo4j Knowledge Graph Store — 知识图谱存储与检索

框架替换: 使用 langchain_community.graphs.Neo4jGraph 替代手写 GraphDatabase.driver + session.run。
Neo4jGraph 自动管理连接池、Cypher 查询执行、schema 刷新。

接口保持不变，调用方（memory/manager.py 等）无需修改。
"""

from __future__ import annotations

from typing import Any

from nexus.config import get_config
from nexus.core.exceptions import GraphStoreError
from nexus.core.logger import get_logger
from nexus.rag.graph_base import BaseGraphStore

logger = get_logger(__name__)


class Neo4jGraphStore(BaseGraphStore):
    """Neo4j 知识图谱管理器（框架委托实现）。"""

    def __init__(self):
        self.config = get_config().neo4j
        self._graph = None
        self._driver = None  # 底层 neo4j driver（供 health/admin 路由检查连接状态）

    @property
    def driver(self):
        """底层 neo4j driver（health/admin 路由通过此属性检查连接状态）。"""
        return self._driver

    def connect(self) -> None:
        """连接 Neo4j（使用 langchain_community Neo4jGraph）。"""
        try:
            from langchain_neo4j import Neo4jGraph
            self._graph = Neo4jGraph(
                url=self.config.uri,
                username=self.config.user,
                password=self.config.password,
            )
            # 获取底层 driver（供 health/admin 路由检查连接状态）
            self._driver = self._graph._driver
            self._init_constraints()
            logger.info("Neo4j connected", uri=self.config.uri)
        except Exception as e:
            logger.error(f"Neo4j connection failed: {e}")
            raise GraphStoreError(f"Failed to connect to Neo4j: {e}")

    def _init_constraints(self) -> None:
        """初始化约束和索引。"""
        queries = [
            "CREATE CONSTRAINT user_id_unique IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE",
            "CREATE INDEX entity_name_index IF NOT EXISTS FOR (e:Entity) ON (e.name)",
        ]
        for q in queries:
            self._graph.query(q)

    def _query(self, cypher: str, **params) -> list[dict[str, Any]]:
        """执行 Cypher 查询（封装 Neo4jGraph.query）。"""
        return self._graph.query(cypher, params)

    def upsert_relation(
        self, user_id: str, relation: str, target: str, target_type: str, milvus_id: int,
    ) -> None:
        """插入/更新图谱关系，绑定 Milvus ID。"""
        cypher = f"""
        MERGE (u:User {{id: $user_id}})
        MERGE (t:{target_type} {{name: $target}})
        MERGE (u)-[r:{relation.upper()}]->(t)
        SET r.mid = $milvus_id
        SET r.timestamp = timestamp()
        """
        try:
            self._query(cypher, user_id=user_id, target=target, milvus_id=milvus_id)
            logger.info(f"Relation upserted: {user_id} -[{relation.upper()}]-> {target} (mid={milvus_id})")
        except Exception as e:
            logger.error(f"Relation upsert failed: {e}")
            raise GraphStoreError(f"Failed to upsert relation: {e}")

    def delete_relation_by_mid(self, milvus_id: int) -> None:
        """根据 Milvus ID 联动删除关系。"""
        try:
            self._query(
                "MATCH (u:User)-[r]->(t) WHERE r.mid = $milvus_id DELETE r",
                milvus_id=milvus_id,
            )
            logger.info(f"Relation deleted by mid: {milvus_id}")
        except Exception as e:
            logger.error(f"Relation delete failed: {e}")

    def search_user_graph(self, user_id: str, depth: int = 1) -> list[str]:
        """查询用户的 N 阶关系。"""
        results: list[str] = []
        try:
            if depth == 1:
                records = self._query(
                    "MATCH (u:User {id: $user_id})-[r]->(t) "
                    "RETURN type(r) as relation, t.name as target, labels(t) as labels",
                    user_id=user_id,
                )
                for record in records:
                    labels = record.get("labels", [])
                    type_label = labels[0] if labels else "Entity"
                    results.append(f"[图谱] {record['relation']} → {record['target']} ({type_label})")
            else:
                cypher = (
                    f"MATCH path = (u:User {{id: $user_id}})-[r*1..{depth}]->(t) "
                    "RETURN [rel in relationships(path) | type(rel)] as relations, "
                    "[node in nodes(path) | coalesce(node.name, node.id)] as nodes"
                )
                records = self._query(cypher, user_id=user_id)
                for record in records:
                    relations = record.get("relations", [])
                    nodes = record.get("nodes", [])
                    path_str = " → ".join(f"{nodes[i]} -[{relations[i]}]->" for i in range(len(relations))) + f" {nodes[-1]}"
                    results.append(f"[图谱深层] {path_str}")
            return results
        except Exception as e:
            logger.error(f"Graph search failed: {e}")
            return results

    def search_food(self, food_name: str) -> str | None:
        """在图谱中搜索食材。"""
        try:
            records = self._query(
                "MATCH (f:Food {name: $name}) RETURN f.name as name LIMIT 1",
                name=food_name,
            )
            return records[0]["name"] if records else None
        except Exception as e:
            logger.error(f"Food graph search failed: {e}")
            return None

    def get_user_profile(self, user_id: str) -> dict[str, Any]:
        """获取用户完整画像。"""
        profile: dict[str, Any] = {"user_id": user_id, "relations": []}
        try:
            records = self._query(
                "MATCH (u:User {id: $user_id})-[r]->(t) "
                "RETURN type(r) as relation, t.name as target, labels(t) as labels, coalesce(r.mid, -1) as mid",
                user_id=user_id,
            )
            for record in records:
                labels = record.get("labels", [])
                profile["relations"].append({
                    "relation": record["relation"],
                    "target": record["target"],
                    "type": labels[0] if labels else "Entity",
                    "milvus_id": record["mid"],
                })
            return profile
        except Exception as e:
            logger.error(f"Profile query failed: {e}")
            return profile

    def clear_database(self) -> None:
        """清空数据库（仅用于开发环境）。"""
        try:
            self._graph.query("MATCH (n) DETACH DELETE n")
            self._graph.query("DROP INDEX entity_name_index IF EXISTS")
            self._graph.query("DROP CONSTRAINT user_id_unique IF EXISTS")
            logger.warning("Neo4j database cleared!")
        except Exception as e:
            logger.error(f"Clear database failed: {e}")

    def close(self) -> None:
        """关闭连接。"""
        if self._driver:
            self._driver.close()
            logger.info("Neo4j disconnected")
