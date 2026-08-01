# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""Redis 缓存配置 — 语义缓存 / 限流 / 会话存储。"""

from __future__ import annotations

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from nexus.config._common import _ENV_FILE


class RedisConfig(BaseSettings):
    """Redis 缓存配置。

    管理与 Redis 服务器的连接参数，以及语义缓存的行为参数。
    """

    host: str = Field(default="127.0.0.1", validation_alias="REDIS_HOST")
    port: int = Field(default=16379, validation_alias="REDIS_PORT")
    password: str = Field(default="", validation_alias="REDIS_PASSWORD")
    db: int = Field(default=0, validation_alias="REDIS_DB")

    # 语义缓存
    cache_enabled: bool = Field(default=True, validation_alias="SEMANTIC_CACHE_ENABLED")
    cache_similarity_threshold: float = Field(
        default=0.92, validation_alias="SEMANTIC_CACHE_SIMILARITY_THRESHOLD",
    )
    cache_ttl: int = Field(default=3600, validation_alias="SEMANTIC_CACHE_TTL_SECONDS")

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    @computed_field
    @property
    def url(self) -> str:
        """完整的 Redis 连接 URL"""
        auth = f":{self.password}@" if self.password else ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"
