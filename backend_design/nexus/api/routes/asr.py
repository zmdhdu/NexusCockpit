# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
ASR 语音识别 API 路由 — 提供本地语音转文字服务

使用 FunASR (SenseVoice) 模型将音频文件识别为文字。
支持前端录音上传（webm/wav 格式），返回识别文本。
"""

from __future__ import annotations

import os
import tempfile
from typing import Optional

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel

from nexus.asr.engine import ASREngine
from nexus.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/asr", tags=["asr"])

# 全局 ASR 引擎实例（懒加载）
_asr_engine: Optional[ASREngine] = None


def _get_asr_engine() -> ASREngine:
    """获取或初始化 ASR 引擎单例。"""
    global _asr_engine
    if _asr_engine is None:
        _asr_engine = ASREngine()
        _asr_engine.load()
    return _asr_engine


class TranscribeResponse(BaseModel):
    """语音识别响应"""
    text: str
    success: bool
    engine: str = "sensevoice"
    message: str = ""


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(file: UploadFile = File(...)):
    """将上传的音频文件识别为文字。

    支持的音频格式:
        - WAV (16kHz, 16-bit, mono)
        - WebM (Chrome/Firefox 录音默认格式)
        - MP3
        - M4A

    Args:
        file: 音频文件（multipart/form-data 上传）

    Returns:
        识别结果，包含 text 字段
    """
    try:
        # 读取上传的音频数据
        audio_bytes = await file.read()
        if not audio_bytes:
            return TranscribeResponse(
                text="", success=False, message="音频文件为空"
            )

        # 获取文件扩展名（用于临时文件）
        suffix = os.path.splitext(file.filename or "audio.webm")[1] or ".webm"

        # 写入临时文件
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(audio_bytes)
            temp_path = f.name

        try:
            # 获取 ASR 引擎并识别
            engine = _get_asr_engine()
            if not engine.is_loaded:
                return TranscribeResponse(
                    text="",
                    success=False,
                    message="ASR 模型未加载，请检查模型路径配置",
                )

            # 如果是 webm/m4a 格式，需要先转换为 wav
            if suffix.lower() in (".webm", ".m4a", ".mp3", ".ogg"):
                wav_path = _convert_to_wav(temp_path)
                if wav_path:
                    text = engine.transcribe(wav_path)
                    if wav_path != temp_path:
                        try:
                            os.unlink(wav_path)
                        except Exception:
                            pass
                else:
                    # 转换失败，尝试直接识别
                    text = engine.transcribe(temp_path)
            else:
                text = engine.transcribe(temp_path)

            return TranscribeResponse(
                text=text.strip(),
                success=bool(text.strip()),
                message="识别成功" if text.strip() else "未识别到语音内容",
            )
        finally:
            try:
                os.unlink(temp_path)
            except Exception:
                pass

    except Exception as e:
        logger.error(f"ASR transcription failed: {e}")
        return TranscribeResponse(
            text="", success=False, message=f"识别失败: {str(e)}"
        )


@router.get("/status")
async def get_asr_status():
    """获取 ASR 引擎状态。"""
    try:
        engine = _get_asr_engine()
        return {
            "loaded": engine.is_loaded,
            "engine": "sensevoice",
            "model_path": engine.config.resolved_funasr_path(),
        }
    except Exception as e:
        return {
            "loaded": False,
            "engine": "sensevoice",
            "error": str(e),
        }


def _convert_to_wav(input_path: str) -> Optional[str]:
    """将音频文件转换为 16kHz 单声道 WAV 格式。

    转换策略（按优先级）:
        1. 系统 ffmpeg (功能最全，支持所有格式)
        2. imageio_ffmpeg 包 (pip 安装的 ffmpeg 二进制)
        3. torchaudio (支持 WAV/FLAC，不支持 WebM)
        4. soundfile / librosa (通过 libsndfile 支持 OGG/FLAC)

    Args:
        input_path: 输入音频文件路径

    Returns:
        转换后的 WAV 文件路径，失败返回 None
    """
    import subprocess

    output_path = input_path.rsplit(".", 1)[0] + "_converted.wav"

    # --- 策略 1: 系统 ffmpeg ---
    ffmpeg_cmd = None
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True, timeout=5,
        )
        ffmpeg_cmd = "ffmpeg"
    except FileNotFoundError:
        pass
    except Exception:
        pass

    # --- 策略 2: imageio_ffmpeg (pip 包内置 ffmpeg) ---
    if not ffmpeg_cmd:
        try:
            import imageio_ffmpeg
            ffmpeg_cmd = imageio_ffmpeg.get_ffmpeg_exe()
            logger.info(f"Using imageio_ffmpeg binary: {ffmpeg_cmd}")
        except ImportError:
            pass
        except Exception:
            pass

    if ffmpeg_cmd:
        try:
            subprocess.run(
                [
                    ffmpeg_cmd, "-y",
                    "-i", input_path,
                    "-ar", "16000",
                    "-ac", "1",
                    "-acodec", "pcm_s16le",
                    output_path,
                ],
                capture_output=True,
                timeout=30,
            )
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return output_path
        except Exception as e:
            logger.warning(f"ffmpeg conversion failed: {e}")

    # --- 策略 3: torchaudio (不支持 webm, 但支持 wav/flac) ---
    try:
        import torchaudio
        import torch
        waveform, sample_rate = torchaudio.load(input_path)
        # 重采样到 16kHz
        if sample_rate != 16000:
            resampler = torchaudio.transforms.Resample(sample_rate, 16000)
            waveform = resampler(waveform)
        # 转为单声道
        if waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)
        torchaudio.save(output_path, waveform, 16000)
        if os.path.exists(output_path):
            logger.info(f"Audio converted via torchaudio: {output_path}")
            return output_path
    except Exception as e:
        logger.debug(f"torchaudio conversion failed: {e}")

    # --- 策略 4: soundfile (通过 libsndfile 支持 ogg/flac/wav) ---
    try:
        import soundfile as sf
        import numpy as np
        data, sr = sf.read(input_path, dtype="float32")
        # 转为单声道
        if len(data.shape) > 1:
            data = data.mean(axis=1)
        # 重采样（简单线性插值）
        if sr != 16000:
            num_samples = int(len(data) * 16000 / sr)
            indices = np.linspace(0, len(data) - 1, num_samples)
            data = np.interp(indices, np.arange(len(data)), data).astype(np.float32)
        # 归一化到 int16
        data_int16 = (data * 32767).astype(np.int16)
        sf.write(output_path, data_int16, 16000, subtype="PCM_16")
        if os.path.exists(output_path):
            logger.info(f"Audio converted via soundfile: {output_path}")
            return output_path
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"soundfile conversion failed: {e}")

    logger.warning("All audio conversion strategies failed (ffmpeg/torchaudio/soundfile)")
    return None
