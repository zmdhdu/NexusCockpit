# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""设备检测工具 — ASR/TTS 共享"""

from __future__ import annotations


def has_cuda() -> bool:
    """检测是否有可用的 CUDA GPU 或 Apple MPS 后端。"""
    try:
        import torch
        if torch.cuda.is_available():
            return True
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return True
    except ImportError:
        pass
    return False
