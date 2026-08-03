# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""ASR / TTS / 声纹模型路径配置。"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from nexus.config._common import _ENV_FILE, _resolve_path


class ASRConfig(BaseSettings):
    """语音处理模型路径配置。

    管理离线语音模型文件的路径:
      - FunASR SenseVoice (ASR)
      - CosyVoice (TTS)
      - CAM++ (声纹识别)
    """

    funasr_model_path: str = Field(
        default="./models/asr/sensevoice", validation_alias="FUNASR_MODEL_PATH",
    )
    cam_model_path: str = Field(
        default="./models/sv/cam_plus", validation_alias="CAM_MODEL_PATH",
    )
    cosyvoice_model_path: str = Field(
        default="./models/tts/cosyvoice", validation_alias="COSYVOICE_MODEL_PATH",
    )
    speaker_enroll_dir: str = Field(
        default="./assets/speaker/enroll_wav", validation_alias="SPEAKER_ENROLL_DIR",
    )
    speaker_users_dir: str = Field(
        default="./assets/speaker/users", validation_alias="SPEAKER_USERS_DIR",
    )

    # 声纹参数
    voiceprint_model: str = Field(default="cam_plus", validation_alias="VOICEPRINT_MODEL")
    voiceprint_threshold: float = Field(default=0.7, validation_alias="VOICEPRINT_THRESHOLD")
    voiceprint_enroll_count: int = Field(default=3, validation_alias="VOICEPRINT_ENROLL_COUNT")

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    def model_post_init(self, __context) -> None:
        """将相对路径解析为绝对路径。"""
        self.funasr_model_path = _resolve_path(self.funasr_model_path)
        self.cam_model_path = _resolve_path(self.cam_model_path)
        self.cosyvoice_model_path = _resolve_path(self.cosyvoice_model_path)
        self.speaker_enroll_dir = _resolve_path(self.speaker_enroll_dir)
        self.speaker_users_dir = _resolve_path(self.speaker_users_dir)

    def resolved_funasr_path(self) -> str:
        """返回已解析为绝对路径的 FunASR 模型路径。"""
        return self.funasr_model_path

    def resolved_cosyvoice_path(self) -> str:
        """返回已解析为绝对路径的 CosyVoice 模型路径。"""
        return self.cosyvoice_model_path

    def resolved_cam_path(self) -> str:
        """返回已解析为绝对路径的 CAM++ 声纹模型路径。"""
        return self.cam_model_path
