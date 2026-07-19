# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
声纹注册与验证 — 语音声纹识别

使用 CAM++ (3D-Speaker) 模型提取声纹特征，
按座舱 ID 隔离特征库存储。

功能:
1. 声纹注册: 录制音频 → CAM++ 提取特征 → 存储 embedding
2. 声纹验证: 音频 → 提取特征 → 与已注册特征比对 → 返回相似度
3. 声纹管理: 查询注册状态、删除声纹
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, List, Optional

import numpy as np

try:
    import torch
except ImportError:
    torch = None

from nexus.config import get_config
from nexus.core.logger import get_logger

logger = get_logger(__name__)

# 声纹存储根目录
_SPEAKER_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)
    )))),
    "assets", "speaker", "users"
)


class VoiceprintService:
    """声纹注册与验证服务。

    使用 CAM++ 模型提取声纹特征（embedding），
    按座舱 ID 和用户 ID 隔离存储。

    Attributes:
        model: CAM++ 声纹模型
        threshold: 验证阈值
        enroll_count: 注册所需音频条数
    """

    def __init__(self) -> None:
        config = get_config()
        self.threshold = config.cockpit.voiceprint_threshold
        self.enroll_count = config.cockpit.voiceprint_enroll_count
        self._model = None
        self._model_loaded = False

    def _ensure_model(self) -> None:
        """延迟加载 CAM++ 模型。

        使用 modelscope pipeline API 加载模型（兼容性更好）。
        """
        if self._model_loaded:
            return

        try:
            from modelscope.pipelines import pipeline
            from modelscope.utils.constant import Tasks

            model_path = os.path.join(
                get_config().project_root,
                "models", "sv", "cam_plus"
            )
            if os.path.exists(model_path):
                # 使用 modelscope pipeline 加载 CAM++ 模型
                self._model = pipeline(
                    task=Tasks.speaker_verification,
                    model=model_path,
                )
                logger.info(f"CAM++ voiceprint model loaded from {model_path} (modelscope pipeline)")
            else:
                logger.warning(f"CAM++ model not found at {model_path}, voiceprint will use mock mode")
        except ImportError:
            logger.warning("modelscope not installed, voiceprint will use mock mode")
        except Exception as e:
            logger.warning(f"Failed to load CAM++ model: {e}, using mock mode")

        self._model_loaded = True

    def _get_user_dir(self, cockpit_id: str, user_id: str) -> str:
        """获取用户声纹存储目录。

        Args:
            cockpit_id: 座舱 ID
            user_id: 用户 ID

        Returns:
            声纹存储目录路径
        """
        path = os.path.join(_SPEAKER_ROOT, cockpit_id, user_id)
        os.makedirs(path, exist_ok=True)
        return path

    async def enroll(
        self,
        cockpit_id: str,
        user_id: str,
        audio_data: bytes,
        audio_format: str = "wav",
    ) -> Dict[str, Any]:
        """注册声纹。

        提取音频的声纹特征并存储。需要多次注册（默认 3 次）。

        Args:
            cockpit_id: 座舱 ID
            user_id: 用户 ID
            audio_data: 音频二进制数据
            audio_format: 音频格式

        Returns:
            包含注册状态和已注册条数的信息
        """
        self._ensure_model()

        # 模型不可用时直接返回失败，不创建用户目录（避免空目录残留）
        if self._model is None:
            return {
                "success": False,
                "cockpit_id": cockpit_id,
                "user_id": user_id,
                "enroll_count": 0,
                "required_count": self.enroll_count,
                "completed": False,
                "message": "声纹识别服务不可用（模型未加载），请安装 3D-Speaker 后重试",
            }

        user_dir = self._get_user_dir(cockpit_id, user_id)

        embedding = await self._extract_embedding(audio_data, audio_format)
        if embedding is None:
            return {
                "success": False,
                "cockpit_id": cockpit_id,
                "user_id": user_id,
                "enroll_count": len([
                    f for f in os.listdir(user_dir)
                    if f.startswith("enroll_") and f.endswith(".npy")
                ]),
                "required_count": self.enroll_count,
                "completed": False,
                "message": "声纹特征提取失败，请确保音频清晰且时长不少于3秒",
            }

        # 统计已注册的音频数
        existing = [
            f for f in os.listdir(user_dir)
            if f.startswith("enroll_") and f.endswith(".npy")
        ]
        enroll_num = len(existing) + 1

        # 存储 embedding
        embed_path = os.path.join(user_dir, f"enroll_{enroll_num:02d}.npy")
        np.save(embed_path, embedding)

        # 同时保存原始音频
        audio_path = os.path.join(user_dir, f"enroll_{enroll_num:02d}.{audio_format}")
        with open(audio_path, "wb") as f:
            f.write(audio_data)

        completed = enroll_num >= self.enroll_count
        logger.info(
            f"Voiceprint enroll: cockpit={cockpit_id}, user={user_id}, "
            f"sample={enroll_num}/{self.enroll_count}, completed={completed}"
        )

        return {
            "success": True,
            "cockpit_id": cockpit_id,
            "user_id": user_id,
            "enroll_count": enroll_num,
            "required_count": self.enroll_count,
            "completed": completed,
            "message": f"已注册 {enroll_num}/{self.enroll_count} 条音频"
            + ("，注册完成！" if completed else ""),
        }

    async def verify(
        self,
        cockpit_id: str,
        audio_data: bytes,
        audio_format: str = "wav",
    ) -> Dict[str, Any]:
        """验证声纹。

        提取音频特征，与该座舱下所有已注册用户的声纹比对。

        Args:
            cockpit_id: 座舱 ID
            audio_data: 待验证的音频数据
            audio_format: 音频格式

        Returns:
            验证结果，包含匹配的用户 ID 和相似度
        """
        self._ensure_model()

        # 模型不可用时返回未验证状态
        verify_embedding = await self._extract_embedding(audio_data, audio_format)
        if verify_embedding is None:
            return {
                "verified": False,
                "user_id": None,
                "similarity": 0.0,
                "message": "声纹识别服务不可用（模型未加载）",
            }

        # 遍历该座舱下所有已注册用户
        cockpit_dir = os.path.join(_SPEAKER_ROOT, cockpit_id)
        if not os.path.exists(cockpit_dir):
            return {
                "verified": False,
                "user_id": None,
                "similarity": 0.0,
                "message": "该座舱无已注册用户",
            }

        best_match: Optional[str] = None
        best_score: float = 0.0

        for user_id in os.listdir(cockpit_dir):
            user_dir = os.path.join(cockpit_dir, user_id)
            if not os.path.isdir(user_dir):
                continue

            # 获取该用户所有已注册的 embedding
            enroll_files = [
                f for f in os.listdir(user_dir)
                if f.startswith("enroll_") and f.endswith(".npy")
            ]
            if not enroll_files:
                continue

            # 计算与每个已注册 embedding 的最大相似度
            for ef in enroll_files:
                embed_path = os.path.join(user_dir, ef)
                try:
                    enrolled = np.load(embed_path)
                    score = self._compute_similarity(verify_embedding, enrolled)
                    if score > best_score:
                        best_score = score
                        best_match = user_id
                except Exception as e:
                    logger.error(f"Error loading embedding {embed_path}: {e}")

        verified = best_score >= self.threshold and best_match is not None

        return {
            "verified": verified,
            "user_id": best_match,
            "similarity": round(best_score, 4),
            "threshold": self.threshold,
            "message": f"匹配用户: {best_match}, 相似度: {best_score:.4f}"
            if verified else "未匹配到已注册用户",
        }

    def get_status(self, cockpit_id: str) -> Dict[str, Any]:
        """获取座舱的声纹注册状态。

        Args:
            cockpit_id: 座舱 ID

        Returns:
            各用户的注册状态
        """
        cockpit_dir = os.path.join(_SPEAKER_ROOT, cockpit_id)
        if not os.path.exists(cockpit_dir):
            return {"cockpit_id": cockpit_id, "users": []}

        users: List[Dict[str, Any]] = []
        for user_id in os.listdir(cockpit_dir):
            user_dir = os.path.join(cockpit_dir, user_id)
            if not os.path.isdir(user_dir):
                continue
            enroll_count = len([
                f for f in os.listdir(user_dir)
                if f.startswith("enroll_") and f.endswith(".npy")
            ])
            # 跳过空目录（注册失败时不应显示）
            if enroll_count == 0:
                continue
            users.append({
                "user_id": user_id,
                "enroll_count": enroll_count,
                "completed": enroll_count >= self.enroll_count,
            })

        return {"cockpit_id": cockpit_id, "users": users}

    def delete_voiceprint(self, cockpit_id: str, user_id: str) -> bool:
        """删除用户的声纹数据。

        Args:
            cockpit_id: 座舱 ID
            user_id: 用户 ID

        Returns:
            是否成功删除
        """
        import shutil
        user_dir = os.path.join(_SPEAKER_ROOT, cockpit_id, user_id)
        if os.path.exists(user_dir):
            shutil.rmtree(user_dir)
            logger.info(f"Deleted voiceprint for cockpit={cockpit_id}, user={user_id}")
            return True
        return False

    async def _extract_embedding(self, audio_data: bytes, audio_format: str) -> Optional[np.ndarray]:
        """提取音频的声纹特征向量。

        使用 modelscope pipeline 提取 embedding，兼容性更好。
        模型不可用时返回 None 并记 warn，不再返回假数据。
        调用方需处理 None 返回值，跳过声纹验证步骤。

        Args:
            audio_data: 音频二进制数据
            audio_format: 音频格式

        Returns:
            声纹特征向量 (numpy array)，模型不可用时返回 None
        """
        if self._model is not None:
            # 使用 modelscope pipeline 的底层模型提取特征
            try:
                import torchaudio
                import tempfile

                # 保存临时文件
                with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as f:
                    f.write(audio_data)
                    temp_path = f.name

                try:
                    # 加载音频
                    waveform, sample_rate = torchaudio.load(temp_path)

                    # 直接调用 pipeline 的底层模型提取 embedding
                    # modelscope pipeline 的 __call__ 不支持 output_embedding 参数
                    # 所以直接访问 pipeline.model 提取特征
                    if torch is not None:
                        with torch.no_grad():
                            emb = self._model.model(waveform)
                    else:
                        emb = self._model.model(waveform)

                    return emb.detach().cpu().numpy().flatten()
                finally:
                    os.unlink(temp_path)
            except Exception as e:
                logger.error(f"Model extraction failed: {e}")
                return None

        # 模型不可用时返回 None，不再返回假随机向量
        logger.warning("CAM++ model not loaded, voiceprint verification skipped")
        return None

    @staticmethod
    def _compute_similarity(embed1: np.ndarray, embed2: np.ndarray) -> float:
        """计算两个声纹特征向量的余弦相似度。

        Args:
            embed1: 特征向量 1
            embed2: 特征向量 2

        Returns:
            余弦相似度 (0-1)
        """
        # 归一化后点积 = 余弦相似度
        norm1 = np.linalg.norm(embed1)
        norm2 = np.linalg.norm(embed2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(np.dot(embed1, embed2) / (norm1 * norm2))


# 全局单例
_voiceprint: Optional[VoiceprintService] = None


def get_voiceprint_service() -> VoiceprintService:
    """获取声纹服务全局单例。"""
    global _voiceprint
    if _voiceprint is None:
        _voiceprint = VoiceprintService()
    return _voiceprint
