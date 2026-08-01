# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
NexusCockpit 配置中心 — 统一入口

本包 (nexus.config) 替代原单文件 config.py (~805 行)。
按子系统拆分为 11 个配置文件，统一在此 __init__.py 聚合导出。

对外接口:
    from nexus.config import get_config       # 全局单例
    from nexus.config import get_llm_config   # LLM 快捷访问
    from nexus.config import get_milvus_config
    from nexus.config import get_redis_config

拆分文件清单:
    config/_common.py          路径常量 + _resolve_path() + 环境文件加载
    config/llm.py              LLMConfig
    config/database.py         MilvusConfig, Neo4jConfig, MySQLConfig
    config/cache.py            RedisConfig
    config/vehicle.py          VehicleConfig
    config/asr.py              ASRConfig
    config/observability.py    LangfuseConfig, ObservabilityConfig
    config/server.py           ServerConfig, JWTConfig
    config/providers.py        ProvidersConfig, RerankerConfig
    config/data.py             DataConfig, MemoryConfig
    config/cockpit.py          CockpitSettings, TavilyConfig, AmapConfig
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 子配置模块导入 (顺序: 先 _common, 再各子系统)
from nexus.config._common import _ENV_FILE, _PROJECT_ROOT, _resolve_path  # noqa: F401
from nexus.config.asr import ASRConfig
from nexus.config.cache import RedisConfig
from nexus.config.cockpit import AmapConfig, CockpitSettings, TavilyConfig
from nexus.config.data import DataConfig, MemoryConfig
from nexus.config.database import MilvusConfig, MySQLConfig, Neo4jConfig
from nexus.config.llm import LLMConfig
from nexus.config.observability import LangfuseConfig, ObservabilityConfig
from nexus.config.providers import ProvidersConfig, RerankerConfig
from nexus.config.server import JWTConfig, ServerConfig
from nexus.config.vehicle import VehicleConfig

__all__ = [
    # 聚合入口
    "AppConfig",
    "get_config",
    "get_llm_config",
    "get_milvus_config",
    "get_redis_config",
    # 路径工具
    "_resolve_path",
    "_PROJECT_ROOT",
    # 子配置类
    "LLMConfig",
    "MilvusConfig",
    "Neo4jConfig",
    "MySQLConfig",
    "RedisConfig",
    "VehicleConfig",
    "ASRConfig",
    "LangfuseConfig",
    "ObservabilityConfig",
    "ServerConfig",
    "JWTConfig",
    "TavilyConfig",
    "AmapConfig",
    "ProvidersConfig",
    "RerankerConfig",
    "DataConfig",
    "MemoryConfig",
    "CockpitSettings",
]


class AppConfig(BaseSettings):
    """NexusCockpit 全局应用配置 — 聚合所有子系统配置。

    所有子系统配置实例在此聚合，通过 get_config() 全局单例访问。
    每个子配置类独立管理自己的环境变量前缀和 .env 文件。
    """

    # === LLM / Agent ===
    llm: LLMConfig = Field(default_factory=LLMConfig)

    # === 数据库 ===
    milvus: MilvusConfig = Field(default_factory=MilvusConfig)
    neo4j: Neo4jConfig = Field(default_factory=Neo4jConfig)
    mysql: MySQLConfig = Field(default_factory=MySQLConfig)

    # === 缓存 / 中间件 ===
    redis: RedisConfig = Field(default_factory=RedisConfig)

    # === 车控 ===
    vehicle: VehicleConfig = Field(default_factory=VehicleConfig)

    # === 语音模型 ===
    asr: ASRConfig = Field(default_factory=ASRConfig)

    # === 可观测性 ===
    langfuse: LangfuseConfig = Field(default_factory=LangfuseConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)

    # === 服务器 + 认证 ===
    server: ServerConfig = Field(default_factory=ServerConfig)
    jwt: JWTConfig = Field(default_factory=JWTConfig)

    # === 第三方服务 ===
    tavily: TavilyConfig = Field(default_factory=TavilyConfig)
    amap: AmapConfig = Field(default_factory=AmapConfig)

    # === 部署模式 ===
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    reranker: RerankerConfig = Field(default_factory=RerankerConfig)

    # === 数据目录 + 记忆 ===
    data: DataConfig = Field(default_factory=DataConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)

    # === 多座舱 ===
    cockpit: CockpitSettings = Field(default_factory=CockpitSettings)

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")


# ============================================================
# 全局单例 + 快捷访问函数
# ============================================================

@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    """获取全局 AppConfig 单例 (线程安全, lru_cache 保证只创建一次)。

    Returns:
        AppConfig 实例，包含所有子系统配置
    """
    return AppConfig()


def get_llm_config() -> LLMConfig:
    """快捷访问 LLM 配置。"""
    return get_config().llm


def get_milvus_config() -> MilvusConfig:
    """快捷访问 Milvus 配置。"""
    return get_config().milvus


def get_redis_config() -> RedisConfig:
    """快捷访问 Redis 配置。"""
    return get_config().redis
