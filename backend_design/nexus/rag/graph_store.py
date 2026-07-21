# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Neo4j Knowledge Graph Store — 知识图谱存储与检索
管理用户画像关系图谱，支持 Milvus ID 双向绑定
"""

from __future__ import annotations

from typing import Any

from neo4j import GraphDatabase

from nexus.config import get_config
from nexus.core.exceptions import GraphStoreError
from nexus.core.logger import get_logger
from nexus.rag.graph_base import BaseGraphStore

logger = get_logger(__name__)


class Neo4jGraphStore(BaseGraphStore):
    """Neo4j 知识图谱管理器"""

    def __init__(self):
        self.config = get_config().neo4j
        self.driver = None

    def connect(self) -> None:
        """连接 Neo4j"""
        try:
            self.driver = GraphDatabase.driver(
                self.config.uri,
                auth=(self.config.user, self.config.password),
            )
            self.driver.verify_connectivity()
            self._init_constraints()
            logger.info("Neo4j connected", uri=self.config.uri)
        except Exception as e:
            logger.error(f"Neo4j connection failed: {e}")
            raise GraphStoreError(f"Failed to connect to Neo4j: {e}")

    def _init_constraints(self) -> None:
        """初始化约束和索引"""
        queries = [
            "CREATE CONSTRAINT user_id_unique IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE",
            "CREATE INDEX entity_name_index IF NOT EXISTS FOR (e:Entity) ON (e.name)",
        ]
        with self.driver.session() as session:
            for q in queries:
                session.run(q)

    def upsert_relation(
        self,
        user_id: str,
        relation: str,
        target: str,
        target_type: str,
        milvus_id: int,
    ) -> None:
        """
        插入/更新图谱关系，绑定 Milvus ID
        结构: (User)-[:RELATION {mid: milvus_id}]->(Entity)
        """
        cypher = f"""
        MERGE (u:User {{id: $user_id}})
        MERGE (t:{target_type} {{name: $target}})
        MERGE (u)-[r:{relation.upper()}]->(t)
        SET r.mid = $milvus_id
        SET r.timestamp = timestamp()
        """
        try:
            with self.driver.session() as session:
                session.run(cypher, user_id=user_id, target=target, milvus_id=milvus_id)
            logger.info(
                f"Relation upserted: {user_id} -[{relation.upper()}]-> {target} (mid={milvus_id})"
            )
        except Exception as e:
            logger.error(f"Relation upsert failed: {e}")
            raise GraphStoreError(f"Failed to upsert relation: {e}")

    def delete_relation_by_mid(self, milvus_id: int) -> None:
        """根据 Milvus ID 联动删除关系"""
        cypher = """
        MATCH (u:User)-[r]->(t)
        WHERE r.mid = $milvus_id
        DELETE r
        """
        try:
            with self.driver.session() as session:
                session.run(cypher, milvus_id=milvus_id)
            logger.info(f"Relation deleted by mid: {milvus_id}")
        except Exception as e:
            logger.error(f"Relation delete failed: {e}")

    def search_user_graph(self, user_id: str, depth: int = 1) -> list[str]:
        """查询用户的 N 阶关系"""
        if depth == 1:
            cypher = """
            MATCH (u:User {id: $user_id})-[r]->(t)
            RETURN type(r) as relation, t.name as target, labels(t) as labels
            """
        else:
            cypher = f"""
            MATCH path = (u:User {{id: $user_id}})-[r*1..{depth}]->(t)
            RETURN [rel in relationships(path) | type(rel)] as relations,
                   [node in nodes(path) | coalesce(node.name, node.id)] as nodes
            """

        results: list[str] = []
        try:
            with self.driver.session() as session:
                if depth == 1:
                    for record in session.run(cypher, user_id=user_id):
                        relation = record["relation"]
                        target = record["target"]
                        labels = record["labels"]
                        type_label = labels[0] if labels else "Entity"
                        results.append(f"[图谱] {relation} → {target} ({type_label})")
                else:
                    for record in session.run(cypher, user_id=user_id):
                        relations = record["relations"]
                        nodes = record["nodes"]
                        path_str = " → ".join(
                            f"{nodes[i]} -[{relations[i]}]->" for i in range(len(relations))
                        ) + f" {nodes[-1]}"
                        results.append(f"[图谱深层] {path_str}")
            return results
        except Exception as e:
            logger.error(f"Graph search failed: {e}")
            return results

    def search_food(self, food_name: str) -> str | None:
        """在图谱中搜索食材"""
        cypher = """
        MATCH (f:Food {name: $name})
        RETURN f.name as name, f.category as category
        LIMIT 1
        """
        try:
            with self.driver.session() as session:
                result = session.run(cypher, name=food_name)
                record = result.single()
                if record:
                    return record["name"]
                return None
        except Exception as e:
            logger.error(f"Food graph search failed: {e}")
            return None

    def get_user_profile(self, user_id: str) -> dict[str, Any]:
        """获取用户完整画像"""
        cypher = """
        MATCH (u:User {id: $user_id})-[r]->(t)
        RETURN type(r) as relation, t.name as target, labels(t) as labels, coalesce(r.mid, -1) as mid
        """
        profile: dict[str, Any] = {"user_id": user_id, "relations": []}
        try:
            with self.driver.session() as session:
                for record in session.run(cypher, user_id=user_id):
                    profile["relations"].append({
                        "relation": record["relation"],
                        "target": record["target"],
                        "type": record["labels"][0] if record["labels"] else "Entity",
                        "milvus_id": record["mid"],
                    })
            return profile
        except Exception as e:
            logger.error(f"Profile query failed: {e}")
            return profile

    def clear_database(self) -> None:
        """清空数据库（仅用于开发环境）"""
        try:
            with self.driver.session() as session:
                session.run("MATCH (n) DETACH DELETE n")
                session.run("DROP INDEX entity_name_index IF EXISTS")
                session.run("DROP CONSTRAINT user_id_unique IF EXISTS")
            logger.warning("Neo4j database cleared!")
        except Exception as e:
            logger.error(f"Clear database failed: {e}")

    def close(self) -> None:
        """关闭连接"""
        if self.driver:
            self.driver.close()
            logger.info("Neo4j disconnected")
