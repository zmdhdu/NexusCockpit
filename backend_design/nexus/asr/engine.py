# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
ASR Engine — 语音识别引擎封装
基于 FunASR (SenseVoice) 实现端侧语音识别
"""

from __future__ import annotations

import os
from typing import Optional

from nexus.config import get_config
from nexus.core.logger import get_logger

logger = get_logger(__name__)


class ASREngine:
    """
    语音识别引擎
    封装 FunASR SenseVoice 模型
    """

    def __init__(self):
        self.config = get_config().asr
        self._model = None
        self._loaded = False

    def load(self) -> None:
        """加载 ASR 模型"""
        if self._loaded:
            return

        try:
            from funasr import AutoModel

            model_path = self.config.resolved_funasr_path()
            if not os.path.exists(model_path):
                logger.warning(f"ASR model path not found: {model_path}")
                return

            self._model = AutoModel(
                model=model_path,
                trust_remote_code=True,
                device="cuda:0" if _has_cuda() else "cpu",
            )
            self._loaded = True
            logger.info(f"ASR model loaded from {model_path}")
        except ImportError:
            logger.warning("funasr not installed, ASR disabled")
        except Exception as e:
            logger.error(f"ASR model load failed: {e}")

    def transcribe(self, audio_path: str) -> str:
        """
        识别音频文件为文本
        返回识别出的文本
        """
        if not self._loaded or not self._model:
            logger.error("ASR model not loaded")
            return ""

        try:
            from funasr.utils.postprocess_utils import rich_transcription_postprocess

            result = self._model.generate(
                input=audio_path,
                cache={},
                language="auto",
                use_itn=True,
            )
            if result and len(result) > 0:
                text = result[0].get("text", "")
                text = rich_transcription_postprocess(text)
                logger.info(f"ASR result: {text[:100]}")
                return text
            return ""
        except Exception as e:
            logger.error(f"ASR transcription failed: {e}")
            return ""

    def transcribe_bytes(self, audio_bytes: bytes, sample_rate: int = 16000) -> str:
        """
        识别音频字节流为文本
        (需要先将字节保存为临时文件)
        """
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            temp_path = f.name

        try:
            return self.transcribe(temp_path)
        finally:
            try:
                os.unlink(temp_path)
            except Exception:
                pass

    @property
    def is_loaded(self) -> bool:
        return self._loaded


def _has_cuda() -> bool:
    """检查是否有 CUDA 可用"""
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False
