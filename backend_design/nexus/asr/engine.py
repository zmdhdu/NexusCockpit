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


class SpeakerVerifier:
    """
    声纹验证引擎
    基于 ModelScope CAM++ 模型
    """

    def __init__(self):
        self.config = get_config().asr
        self._pipeline = None
        self._loaded = False

    def load(self) -> None:
        """加载声纹模型"""
        if self._loaded:
            return

        try:
            from modelscope.pipelines import pipeline

            model_path = self.config.resolved_cam_path()
            self._pipeline = pipeline(
                task="speaker-verification",
                model=model_path,
                model_revision="v1.0.0",
                device="cuda:0" if _has_cuda() else "cpu",
            )
            self._loaded = True
            logger.info(f"Speaker verifier loaded from {model_path}")
        except ImportError:
            logger.warning("modelscope not installed, speaker verification disabled")
        except Exception as e:
            logger.error(f"Speaker verifier load failed: {e}")

    def verify(self, audio_path: str, enrolled_audio_path: str) -> dict:
        """
        验证声纹是否匹配
        返回: {"match": bool, "score": float}
        """
        if not self._loaded or not self._pipeline:
            return {"match": False, "score": 0.0}

        try:
            result = self._pipeline(
                audio_in=[audio_path, enrolled_audio_path],
                output_emb=False,
            )
            # result 格式: {"text": "YES"/"NO", "score": float}
            match = result.get("text", "").upper() == "YES"
            score = float(result.get("score", 0.0))
            return {"match": match, "score": score}
        except Exception as e:
            logger.error(f"Speaker verification failed: {e}")
            return {"match": False, "score": 0.0}

    def extract_embedding(self, audio_path: str) -> list[float] | None:
        """提取声纹 embedding"""
        if not self._loaded or not self._pipeline:
            return None

        try:
            result = self._pipeline(audio_in=audio_path, output_emb=True)
            if isinstance(result, list) and len(result) > 0:
                return result[0].get("spk_embedding", [])
            return None
        except Exception as e:
            logger.error(f"Embedding extraction failed: {e}")
            return None

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
