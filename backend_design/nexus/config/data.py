# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""数据目录 + 记忆管理参数配置。"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from nexus.config._common import _ENV_FILE, _resolve_path


class DataConfig(BaseSettings):
    """数据目录配置 — 食物知识库 / 上传文件 / 临时文件等路径。"""

    food_data_dir: str = Field(default="./data/food", validation_alias="FOOD_DATA_DIR")
    knowledge_data_dir: str = Field(default="./data/knowledge", validation_alias="KNOWLEDGE_DATA_DIR")
    upload_dir: str = Field(default="./data/uploads", validation_alias="UPLOAD_DIR")
    temp_dir: str = Field(default="./data/temp", validation_alias="TEMP_DIR")
    preferences_dir: str = Field(default="./data/preferences", validation_alias="PREFERENCES_DIR")

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    def resolved_food_dir(self) -> str:
        """食物数据目录的绝对路径"""
        return _resolve_path(self.food_data_dir)

    def resolved_knowledge_dir(self) -> str:
        """知识文档目录的绝对路径"""
        return _resolve_path(self.knowledge_data_dir)

    def resolved_upload_dir(self) -> str:
        """上传文件目录的绝对路径"""
        return _resolve_path(self.upload_dir)

    def resolved_temp_dir(self) -> str:
        """临时文件目录的绝对路径"""
        return _resolve_path(self.temp_dir)

    def resolved_preferences_dir(self) -> str:
        """用户偏好数据目录的绝对路径"""
        return _resolve_path(self.preferences_dir)


class MemoryConfig(BaseSettings):
    """智能上下文记忆管理参数。

    控制对话历史的压缩、摘要、窗口大小等行为。
    """

    compress_threshold_turns: int = Field(
        default=8, validation_alias="MEMORY_COMPRESS_THRESHOLD_TURNS",
    )
    keep_recent_turns: int = Field(default=5, validation_alias="MEMORY_KEEP_RECENT_TURNS")
    max_summary_chars: int = Field(default=1000, validation_alias="MEMORY_MAX_SUMMARY_CHARS")
    max_history_len: int = Field(default=20, validation_alias="MEMORY_MAX_HISTORY_LEN")
    context_token_ratio: float = Field(default=0.7, validation_alias="MEMORY_CONTEXT_TOKEN_RATIO")
    context_token_hard_cap: int = Field(default=4096, validation_alias="MEMORY_CONTEXT_TOKEN_HARD_CAP")

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")
