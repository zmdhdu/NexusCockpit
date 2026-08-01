# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""数据库配置 — Milvus / Neo4j / MySQL 连接参数。"""

from __future__ import annotations

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from nexus.config._common import _ENV_FILE


class MilvusConfig(BaseSettings):
    """Milvus 向量数据库配置。"""

    host: str = Field(default="127.0.0.1", validation_alias="MILVUS_HOST")
    port: int = Field(default=19530, validation_alias="MILVUS_PORT")
    uri: str = Field(default="http://127.0.0.1:19530", validation_alias="MILVUS_URI")
    collection_food: str = Field(default="Food_List", validation_alias="MILVUS_COLLECTION_FOOD")
    collection_memory: str = Field(default="User_Memory", validation_alias="MILVUS_COLLECTION_MEMORY")
    alias: str = "nexus_link"
    index_type: str = "HNSW"
    metric_type: str = "IP"
    index_params: dict = Field(default_factory=lambda: {"M": 16, "efConstruction": 200})
    search_params: dict = Field(default_factory=lambda: {"ef": 64})

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")


class Neo4jConfig(BaseSettings):
    """Neo4j 知识图谱配置。"""

    uri: str = Field(default="bolt://127.0.0.1:17687", validation_alias="NEO4J_URI")
    user: str = Field(default="neo4j", validation_alias="NEO4J_USER")
    password: str = Field(default="nexuscockpit", validation_alias="NEO4J_PASSWORD")

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")


class MySQLConfig(BaseSettings):
    """MySQL 数据库配置。"""

    host: str = Field(default="127.0.0.1", validation_alias="MYSQL_HOST")
    port: int = Field(default=13306, validation_alias="MYSQL_PORT")
    user: str = Field(default="root", validation_alias="MYSQL_USER")
    password: str = Field(default="nexuscockpit", validation_alias="MYSQL_PASSWORD")
    database: str = Field(default="nexus_cockpit", validation_alias="MYSQL_DATABASE")

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    @computed_field
    @property
    def url(self) -> str:
        """异步 MySQL 连接 URL (使用 aiomysql 驱动)"""
        return (
            f"mysql+aiomysql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}?charset=utf8mb4"
        )
