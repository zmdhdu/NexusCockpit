# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""部署模式开关 + Reranker 配置。"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from nexus.config._common import _ENV_FILE


class ProvidersConfig(BaseSettings):
    """部署模式开关 — 控制各组件的 Provider 选择。

    本地化降级改造后，大部分 provider 固定为 local。
    保留配置项是为了后续灵活切换。
    """

    vector_store: str = Field(default="local", validation_alias="VECTOR_STORE_PROVIDER")
    graph_store: str = Field(default="local", validation_alias="GRAPH_STORE_PROVIDER")
    cache: str = Field(default="local", validation_alias="CACHE_PROVIDER")
    reranker: str = Field(default="local", validation_alias="RERANKER_PROVIDER")
    checkpoint: str = Field(default="sqlite", validation_alias="CHECKPOINT_PROVIDER")

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    def normalized(self) -> dict[str, str]:
        """返回归一化后的 provider 字典 (小写)。"""
        return {
            "vector_store": (self.vector_store or "local").lower(),
            "graph_store": (self.graph_store or "local").lower(),
            "cache": (self.cache or "local").lower(),
            "reranker": (self.reranker or "local").lower(),
            "checkpoint": (self.checkpoint or "sqlite").lower(),
        }


class RerankerConfig(BaseSettings):
    """Reranker 重排模型配置。"""

    model: str = Field(default="BAAI/bge-reranker-v2-m3", validation_alias="RERANK_MODEL")

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")
