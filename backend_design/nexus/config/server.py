# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""服务器 + 认证配置。"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from nexus.config._common import _ENV_FILE


class ServerConfig(BaseSettings):
    """FastAPI 服务器配置。"""

    # 监听地址 (0.0.0.0 表示所有网卡)
    host: str = Field(default="0.0.0.0", validation_alias="HOST")
    # 监听端口
    port: int = Field(default=8000, validation_alias="PORT")
    # 调试模式 (开启热重载)
    debug: bool = Field(default=True, validation_alias="DEBUG")
    # 日志级别
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    # CORS 允许的来源 (逗号分隔字符串, 生产环境必须指定具体域名)
    # 默认允许 localhost:3000 (开发环境前端)
    cors_origins: str = Field(default="http://localhost:3000", validation_alias="CORS_ORIGINS")
    # 会话并发锁最大数量（超过时清理空闲锁防内存泄漏）
    session_locks_max: int = Field(default=500, validation_alias="SESSION_LOCKS_MAX")
    # SSE 心跳间隔秒数（防止代理/防火墙超时断连）
    sse_heartbeat_interval: float = Field(default=15.0, validation_alias="SSE_HEARTBEAT_INTERVAL")

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        """CORS 允许来源列表 (逗号分隔字符串 → 列表)"""
        if self.cors_origins == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


class JWTConfig(BaseSettings):
    """JWT 认证配置。"""

    secret_key: str = Field(
        default="nexuscockpit_secure_secret_key_2026", validation_alias="JWT_SECRET_KEY",
    )
    algorithm: str = Field(default="HS256", validation_alias="JWT_ALGORITHM")
    expire_minutes: int = Field(default=1440, validation_alias="JWT_EXPIRE_MINUTES")
    expire_hours: int = Field(default=24, validation_alias="JWT_EXPIRE_HOURS")

    # RBAC
    default_role: str = Field(default="cockpit_user", validation_alias="RBAC_DEFAULT_ROLE")
    admin_username: str = Field(default="admin", validation_alias="RBAC_ADMIN_USERNAME")
    admin_password: str = Field(default="admin123", validation_alias="RBAC_ADMIN_PASSWORD")
    user_password: str = Field(default="cockpit_user_2026", validation_alias="RBAC_USER_PASSWORD")

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")
