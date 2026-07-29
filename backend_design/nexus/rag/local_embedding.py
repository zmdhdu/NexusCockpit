# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Local Embedding Service — 基于 sentence-transformers 的本地文本向量化服务

使用 BAAI/bge-m3 模型 (1024 维)，完全本地推理，数据不出服务器。
与 LocalReranker (bge-reranker-v2-m3) 同属 BAAI BGE 系列，技术栈统一。

模型路径: ./models/embedding/bge-m3/
依赖: sentence-transformers>=2.7.0 (已在 requirements.txt 中)
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from nexus.core.logger import get_logger

logger = get_logger(__name__)

# 项目根目录: backend_design/nexus/rag/local_embedding.py → 向上四级
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

_DEFAULT_MODEL_PATH = os.path.join(_PROJECT_ROOT, "models", "embedding", "bge-m3")


class LocalEmbeddingService:
    """本地 Embedding 服务 (sentence-transformers + bge-m3)。

    与 EmbeddingService (云端 Ark API) 接口完全一致，可无缝替换。
    支持 CPU/GPU 自动切换，批量向量化。

    Attributes:
        _model: SentenceTransformer 模型实例
        _dim: 输出向量维度
        _loaded: 是否已加载
    """

    def __init__(self, model_path: str = ""):
        self.model_path = model_path or _DEFAULT_MODEL_PATH
        self._model = None
        self._dim = 1024  # bge-m3 默认维度
        self._loaded = False
        self._load_error = ""

    def _ensure_loaded(self) -> bool:
        """延迟加载模型（首次调用时加载）。"""
        if self._loaded:
            return True
        if self._model is not None:
            return True

        if not os.path.exists(self.model_path):
            self._load_error = f"Model not found at {self.model_path}"
            logger.warning(self._load_error)
            return False

        try:
            from sentence_transformers import SentenceTransformer

            # GPU/CPU 自动检测
            device = self._detect_device()

            self._model = SentenceTransformer(
                self.model_path,
                device=device,
            )
            self._dim = self._model.get_sentence_embedding_dimension()
            self._loaded = True
            logger.info(
                f"LocalEmbedding loaded: model=bge-m3, "
                f"dim={self._dim}, device={device}"
            )
            return True

        except ImportError:
            self._load_error = "sentence-transformers not installed"
            logger.warning(self._load_error)
            return False
        except Exception as e:
            self._load_error = str(e)
            logger.error(f"Failed to load embedding model: {e}")
            return False

    @staticmethod
    def _detect_device() -> str:
        """检测可用计算设备。"""
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
            # Apple Silicon
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
        except ImportError:
            pass
        return "cpu"

    async def embed(self, text: str) -> list[float]:
        """获取单条文本的 embedding 向量。

        Args:
            text: 待向量化的文本

        Returns:
            1024 维浮点列表，空文本返回零向量
        """
        if not text or not text.strip():
            return [0.0] * self._dim

        if not self._ensure_loaded():
            logger.error(f"Embedding model not loaded: {self._load_error}")
            return [0.0] * self._dim

        # sentence-transformers 的 encode 是同步方法，
        # 使用 run_in_executor 避免阻塞事件循环
        loop = asyncio.get_event_loop()
        vec = await loop.run_in_executor(
            None,
            lambda: self._model.encode(
                text,
                normalize_embeddings=True,
            )
        )
        return vec.tolist()

    async def embed_batch(
        self, texts: list[str], batch_size: int = 32
    ) -> list[list[float]]:
        """批量获取 embedding。

        Args:
            texts: 文本列表
            batch_size: 每批最大文本数

        Returns:
            向量列表，顺序与输入一致
        """
        if not texts:
            return []

        if not self._ensure_loaded():
            return [[0.0] * self._dim] * len(texts)

        loop = asyncio.get_event_loop()
        vecs = await loop.run_in_executor(
            None,
            lambda: self._model.encode(
                texts,
                batch_size=batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        )
        return [v.tolist() for v in vecs]

    @property
    def dimension(self) -> int:
        """返回当前模型的向量维度。"""
        return self._dim

    @property
    def is_available(self) -> bool:
        """模型是否已加载可用。"""
        return self._loaded

    async def close(self) -> None:
        """释放模型资源。"""
        if self._model is not None:
            # sentence-transformers 内部使用 PyTorch，无需显式释放
            self._model = None
            self._loaded = False
