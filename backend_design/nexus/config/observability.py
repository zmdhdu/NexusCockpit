# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""可观测性配置 — Langfuse 追踪 + Prometheus 指标。"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from nexus.config._common import _ENV_FILE


class LangfuseConfig(BaseSettings):
    """Langfuse LLM 追踪平台配置 (本地 Docker 自托管)。"""

    public_key: str = Field(default="", validation_alias="LANGFUSE_PUBLIC_KEY")
    secret_key: str = Field(default="", validation_alias="LANGFUSE_SECRET_KEY")
    host: str = Field(default="http://127.0.0.1:3101", validation_alias="LANGFUSE_HOST")
    db_password: str = Field(default="langfuse", validation_alias="LANGFUSE_DB_PASSWORD")
    nextauth_secret: str = Field(
        default="changeme-langfuse-secret", validation_alias="LANGFUSE_NEXTAUTH_SECRET",
    )
    salt: str = Field(default="changeme-langfuse-salt", validation_alias="LANGFUSE_SALT")

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    @property
    def is_enabled(self) -> bool:
        """是否启用 Langfuse 追踪 (需要 public_key 和 secret_key)"""
        return bool(self.public_key and self.secret_key)


class ObservabilityConfig(BaseSettings):
    """Prometheus 指标采集配置。"""

    prometheus_url: str = Field(
        default="http://127.0.0.1:9200", validation_alias="PROMETHEUS_URL",
    )
    # Grafana 地址（仅用于日志输出，不影响功能）
    grafana_url: str = Field(
        default="http://127.0.0.1:3001", validation_alias="GRAFANA_URL",
    )

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")
