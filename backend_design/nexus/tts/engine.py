"""
TTS Engine — 语音合成引擎封装
基于 CosyVoice 实现端侧语音合成
"""

from __future__ import annotations

import os
from typing import Optional

from nexus.config import get_config
from nexus.core.logger import get_logger

logger = get_logger(__name__)


class TTSEngine:
    """
    语音合成引擎
    封装 CosyVoice 模型
    """

    def __init__(self):
        self.config = get_config().asr
        self._model = None
        self._loaded = False
        self._available_speakers: list[str] = []

    def load(self) -> None:
        """加载 TTS 模型"""
        if self._loaded:
            return

        try:
            from cosyvoice.cli.cosyvoice import CosyVoice

            model_path = self.config.resolved_cosyvoice_path()
            if not os.path.exists(model_path):
                logger.warning(f"TTS model path not found: {model_path}")
                return

            self._model = CosyVoice(
                model_path,
                load_jit=True,
                load_onnx=False,
                fp16=_has_cuda(),
            )
            self._available_speakers = self._model.list_avaliable_spks() or []
            self._loaded = True
            logger.info(
                f"TTS model loaded from {model_path}, "
                f"speakers={self._available_speakers}"
            )
        except ImportError:
            logger.warning("cosyvoice not installed, TTS disabled")
        except Exception as e:
            logger.error(f"TTS model load failed: {e}")

    def synthesize(
        self,
        text: str,
        speaker: str = "",
        output_path: str = "",
    ) -> Optional[str]:
        """
        合成语音
        返回生成的音频文件路径，失败返回 None
        """
        if not self._loaded or not self._model:
            logger.error("TTS model not loaded")
            return None

        if not output_path:
            import tempfile
            output_path = tempfile.mktemp(suffix=".wav")

        try:
            # 如果未指定说话人且模型有可用说话人，使用第一个
            if not speaker and self._available_speakers:
                speaker = self._available_speakers[0]

            # 生成语音
            if speaker:
                outputs = self._model.inference_sft(
                    text, speaker, stream=False
                )
            else:
                outputs = self._model.inference_zero_shot(
                    text, "", "", stream=False
                )

            # 保存音频
            import torchaudio

            for i, chunk in enumerate(outputs):
                audio_data = chunk["tts_speech"]
                torchaudio.save(
                    output_path if i == 0 else f"{output_path}_{i}.wav",
                    audio_data,
                    22050,
                )

            logger.info(f"TTS synthesized: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"TTS synthesis failed: {e}")
            return None

    def synthesize_stream(self, text: str, speaker: str = ""):
        """
        流式合成语音
        返回生成器，每次 yield 一个音频块
        """
        if not self._loaded or not self._model:
            logger.error("TTS model not loaded")
            return

        try:
            if not speaker and self._available_speakers:
                speaker = self._available_speakers[0]

            if speaker:
                outputs = self._model.inference_sft(text, speaker, stream=True)
            else:
                outputs = self._model.inference_zero_shot(text, "", "", stream=True)

            for chunk in outputs:
                yield chunk["tts_speech"]
        except Exception as e:
            logger.error(f"TTS stream synthesis failed: {e}")

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def available_speakers(self) -> list[str]:
        return self._available_speakers


def _has_cuda() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False
