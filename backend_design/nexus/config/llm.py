# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""LLM 配置 — 大语言模型连接参数管理。"""

from __future__ import annotations

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from nexus.config._common import _ENV_FILE


class LLMConfig(BaseSettings):
    """大语言模型 (LLM) 配置。

    管理与 LLM 供应商的连接参数。支持本地/云端一键切换:
      - LLM_PROVIDER=cloud: 使用云端 API (硅基流动/火山方舟)
      - LLM_PROVIDER=local: 使用本地 llama.cpp 子进程 (Qwen3.5-4B)
    """

    provider: str = Field(default="cloud", validation_alias="LLM_PROVIDER")
    ark_api_key: str = Field(default="", validation_alias="ARK_API_KEY")
    ark_base_url: str = Field(
        default="https://api.siliconflow.cn/v1", validation_alias="ARK_BASE_URL",
    )
    llm_model: str = Field(default="deepseek-ai/DeepSeek-V3", validation_alias="LLM_MODEL")
    embedding_model: str = Field(default="BAAI/bge-m3", validation_alias="EMBEDDING_MODEL")
    embedding_dim: int = Field(default=1024, validation_alias="EMBEDDING_DIM")
    temperature: float = Field(default=0.7)
    max_tokens: int = Field(default=512)
    timeout: float = Field(default=30.0)
    reflection_enabled: bool = Field(default=True, validation_alias="REFLECTION_ENABLED")
    memory_extraction_enabled: bool = Field(default=True, validation_alias="MEMORY_EXTRACTION_ENABLED")
    llm_concurrency_limit: int = Field(default=0, validation_alias="LLM_CONCURRENCY_LIMIT")

    # === 本地 LLM 配置 (llama.cpp OpenAI 兼容接口) ===
    fallback_enabled: bool = Field(default=False, validation_alias="LLM_FALLBACK_ENABLED")
    fallback_base_url: str = Field(
        default="http://127.0.0.1:8082/v1", validation_alias="LLM_FALLBACK_BASE_URL",
    )
    fallback_model: str = Field(default="qwen3.5-4b-local", validation_alias="LLM_FALLBACK_MODEL")
    fallback_api_key: str = Field(default="not-needed", validation_alias="LLM_FALLBACK_API_KEY")
    fallback_timeout: float = Field(default=60.0, validation_alias="LLM_FALLBACK_TIMEOUT")

    meituan_dev_token: str = Field(default="", validation_alias="MEITUAN_DEV_TOKEN")
    degradation_notify_user: bool = Field(default=True, validation_alias="DEGRADATION_NOTIFY_USER")
    degradation_notify_admin: bool = Field(default=True, validation_alias="DEGRADATION_NOTIFY_ADMIN")

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    def model_post_init(self, __context) -> None:
        """LLM_PROVIDER=local 时自动切换连接参数到本地 llama-server。"""
        if (self.provider or "cloud").strip().lower() == "local":
            self.ark_base_url = self.fallback_base_url
            self.ark_api_key = self.fallback_api_key or "not-needed"
            self.llm_model = self.fallback_model
            self.timeout = self.fallback_timeout

    @computed_field
    @property
    def embedding_url(self) -> str:
        """Embedding API 的完整 URL (base_url + /embeddings)"""
        return f"{self.ark_base_url}/embeddings"

    @computed_field
    @property
    def is_local(self) -> bool:
        """当前是否使用本地 LLM (llama.cpp)"""
        return (self.provider or "cloud").strip().lower() == "local"
