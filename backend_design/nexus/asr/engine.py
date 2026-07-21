# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
ASR Engine — 语音识别引擎封装
基于 FunASR (SenseVoice) 实现端侧语音识别
"""

from __future__ import annotations

import io
import logging
import os
import re
import warnings
from collections.abc import Iterator
from contextlib import contextmanager, redirect_stdout

from nexus.config import get_config
from nexus.core.logger import get_logger

logger = get_logger(__name__)

# 匹配纯标点/空白文本（如 "。"、"... "、"，"），用于过滤无意义的 ASR 结果
_PURE_PUNCT_RE = re.compile(r"^[\s\W_]+$", re.UNICODE)


def _suppress_funasr_noise() -> None:
    """持久抑制 FunASR / PyTorch 的噪音日志（在 import funasr 前调用一次）。

    解决以下噪音（均不影响功能）:
      1. ``FutureWarning: torch.load weights_only=False``
         → PyTorch 2.5 安全警告，来自 funasr 内部 torch.load。
      2. ``Loading remote code failed: model, No module named 'model'``
         → trust_remote_code=True 时尝试加载远程代码，本地模型不需要。
      3. ``new registry table has been added`` / ``funasr version``
         → FunASR 内部 ``logging.info()`` 直接走 root logger（见下方上下文管理器）。
    """
    # 抑制 PyTorch 的 FutureWarning（torch.load weights_only）
    warnings.filterwarnings("ignore", category=FutureWarning, module="funasr")
    warnings.filterwarnings("ignore", message=".*torch.load.*weights_only.*")

    # 降低 funasr / torchaudio 库自身 logger 级别
    for noisy_logger in ("funasr", "torchaudio", "markdown_it"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)


@contextmanager
def _silence_during_load() -> Iterator[None]:
    """在 FunASR 模型加载期间临时抑制噪音输出。

    FunASR 内部有两类噪音，需要分别处理:

    1. ``logging.info(...)`` 直接走 root logger 的消息（如
       ``new registry table has been added``、``funasr version``）
       → 用 ``logging.disable(INFO)`` 抑制。
       structlog 使用 ``make_filtering_bound_logger`` 自带过滤，
       不受标准 logging.disable 影响，应用自身日志正常输出。

    2. ``print(...)`` 直接输出到 stdout 的消息（如
       ``Loading remote code failed: model, No module named 'model'``）
       → 用 ``redirect_stdout`` 临时重定向到内存缓冲丢弃。
       SenseVoice 本地模型不需要远程代码，此 print 可安全抑制。

    两项操作均只在 ASR 懒加载（首次语音请求）时触发一次，
    加载完成后立即恢复，对应用正常运行无持续影响。
    """
    logging.disable(logging.INFO)
    with redirect_stdout(io.StringIO()):
        try:
            yield
        finally:
            logging.disable(logging.NOTSET)  # 恢复默认（不禁用任何级别）


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
        """加载 ASR 模型

        在加载期间临时抑制 FunASR 的 INFO 级别噪音日志
        （``new registry table``、``funasr version`` 等），
        加载完成后恢复应用正常日志级别。
        """
        if self._loaded:
            return

        # 持久抑制：warnings 过滤 + funasr logger 级别
        _suppress_funasr_noise()

        # 临时抑制：funasr 内部 logging.info() + print() 噪音
        # 注意: structlog 不受 logging.disable 影响，但 logger.warning/error
        # 需在 with 块外调用以确保不受 redirect_stdout 影响
        load_error: str | None = None
        model_path = ""
        with _silence_during_load():
            try:
                from funasr import AutoModel

                model_path = self.config.resolved_funasr_path()
                if not os.path.exists(model_path):
                    load_error = f"ASR model path not found: {model_path}"
                else:
                    self._model = AutoModel(
                        model=model_path,
                        trust_remote_code=True,
                        # 关闭启动时的版本检查（消除 "Check update of funasr" 和
                        # "New version is available" 提示，同时加快启动几秒）
                        disable_update=True,
                        device="cuda:0" if _has_cuda() else "cpu",
                    )
                    self._loaded = True
            except ImportError:
                load_error = "funasr not installed, ASR disabled"
            except Exception as e:
                load_error = f"ASR model load failed: {e}"

        # 在重定向块外输出结果日志
        if load_error:
            if "not found" in load_error or "not installed" in load_error:
                logger.warning(load_error)
            else:
                logger.error(load_error)
        elif self._loaded:
            logger.info(f"ASR model loaded from {model_path}")

    def transcribe(self, audio_path: str) -> str:
        """
        识别音频文件为文本
        返回识别出的文本

        对纯标点结果（如 "。"）会被过滤为空字符串，
        避免静音/极短录音经 rich_transcription_postprocess 补标点后
        产生无意义的识别结果。
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
                # 过滤纯标点/空白结果（如 "。"、"，"）
                text = text.strip()
                if text and _PURE_PUNCT_RE.match(text):
                    logger.info("ASR result: <empty (pure punctuation filtered)>")
                    return ""
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
