# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""多座舱配置 + 第三方服务密钥 (美团/高德/和风天气)。"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from nexus.config._common import _ENV_FILE


class CockpitSettings(BaseSettings):
    """多座舱配置。

    控制多座舱行为，包括座舱数量、隔离模式等。
    """

    # 默认座舱数量
    default_cockpit_count: int = Field(default=1, validation_alias="COCKPIT_COUNT")
    # Go 网关配置
    gate_host: str = Field(default="0.0.0.0", validation_alias="NEXUS_GATE_HOST")
    gate_port: int = Field(default=8080, validation_alias="NEXUS_GATE_PORT")
    gate_mode: str = Field(default="proxy", validation_alias="NEXUS_GATE_MODE")
    # RBAC 配置
    rbac_default_role: str = Field(default="cockpit_user", validation_alias="RBAC_DEFAULT_ROLE")
    rbac_admin_username: str = Field(default="admin", validation_alias="RBAC_ADMIN_USERNAME")
    # 声纹配置
    voiceprint_model: str = Field(default="cam_plus", validation_alias="VOICEPRINT_MODEL")
    voiceprint_threshold: float = Field(default=0.7, validation_alias="VOICEPRINT_THRESHOLD")
    voiceprint_enroll_count: int = Field(default=3, validation_alias="VOICEPRINT_ENROLL_COUNT")

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")


class TavilyConfig(BaseSettings):
    """Tavily 搜索配置。

    Tavily 是专为 AI 设计的搜索引擎，用于联网搜索技能 (如查天气、查新闻)。
    """

    api_key: str = Field(default="", validation_alias="TAVILY_API_KEY")

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")


class AmapConfig(BaseSettings):
    """高德地图 API 配置。

    用于逆地理编码（坐标→地址）和 POI 周边搜索（周边美食/加油站/停车场等）。
    申请: https://lbs.amap.com/api/webservice/guide/create-project/get-key
    """

    api_key: str = Field(default="", validation_alias="AMAP_KEY")

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")
