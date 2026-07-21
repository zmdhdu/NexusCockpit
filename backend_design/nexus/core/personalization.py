# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
个性化服务 — 根据声纹识别的用户ID匹配偏好内容。

功能:
1. 读取用户偏好 JSON 文件（data/preferences/{user_id}.json）
2. 读取 MySQL user_habits 表（频次加权）
3. 构建用户画像文本，注入到 Prompt 的 {user_profile} 占位符
4. 根据用户偏好匹配本地音乐曲库

依赖:
- VoiceprintService: 声纹识别返回 user_id
- DataConfig.preferences_dir: 用户偏好 JSON 存储目录
- MySQL user_habits 表: 用户习惯频次记录
"""

from __future__ import annotations

import json
import os
from typing import Any

from nexus.config import get_config
from nexus.core.logger import get_logger

logger = get_logger(__name__)


class PersonalizationService:
    """个性化服务 — 根据声纹识别的用户ID匹配偏好内容。

    核心流程:
        声纹识别 → user_id → 读取 JSON 偏好 + MySQL 习惯 → 构建画像文本 → 注入 Prompt

    Attributes:
        config: 应用配置实例
        _prefs_dir: 用户偏好 JSON 文件目录
    """

    def __init__(self) -> None:
        self.config = get_config()
        self._prefs_dir = self.config.data.resolved_preferences_dir()
        # 确保偏好目录存在
        os.makedirs(self._prefs_dir, exist_ok=True)

    async def get_user_profile(self, user_id: str) -> dict[str, Any]:
        """获取用户画像，用于注入 Prompt。

        合并 JSON 偏好文件和 MySQL 习惯记录，生成用户画像文本。

        Args:
            user_id: 用户 ID（由声纹识别返回）

        Returns:
            包含 user_id、profile_text、preferences 的字典
        """
        # 1. 读取 JSON 偏好文件
        prefs = self._load_json_prefs(user_id)

        # 2. 读取 MySQL 习惯记录（频次加权，可选）
        habits = await self._load_mysql_habits(user_id)

        # 3. 构建用户画像文本
        profile_text = self._build_profile_text(prefs, habits)

        return {
            "user_id": user_id,
            "profile_text": profile_text,  # 注入到 Prompt 的 {user_profile}
            "preferences": prefs,
        }

    def _load_json_prefs(self, user_id: str) -> dict[str, Any]:
        """读取用户偏好 JSON 文件。

        文件路径: data/preferences/{user_id}.json

        Args:
            user_id: 用户 ID

        Returns:
            用户偏好字典，文件不存在时返回默认偏好
        """
        prefs_path = os.path.join(self._prefs_dir, f"{user_id}.json")
        if not os.path.exists(prefs_path):
            # 尝试加载默认用户偏好
            default_path = os.path.join(self._prefs_dir, "default_user.json")
            if os.path.exists(default_path):
                try:
                    with open(default_path, encoding="utf-8") as f:
                        return json.load(f)
                except Exception as e:
                    logger.warning(f"Failed to load default preferences: {e}")
            logger.debug(f"No preferences found for user={user_id}")
            return {}

        try:
            with open(prefs_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load preferences for user={user_id}: {e}")
            return {}

    async def _load_mysql_habits(self, user_id: str) -> list[dict[str, Any]]:
        """读取 MySQL user_habits 表的频次记录。

        Args:
            user_id: 用户 ID

        Returns:
            习惯记录列表，MySQL 不可用时返回空列表
        """
        try:
            from nexus.core.db_manager import get_db_manager
            db = get_db_manager()
            if not getattr(db, "_connected", False):
                return []

            # 查询用户习惯记录，按频次降序
            pool = getattr(db, "_pool", None)
            if pool is None:
                return []

            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT habit_key, habit_value, hit_count "
                        "FROM user_habits WHERE user_id = %s "
                        "ORDER BY hit_count DESC LIMIT 10",
                        (user_id,),
                    )
                    rows = await cur.fetchall()
                    return [
                        {
                            "habit_key": row[0],
                            "habit_value": row[1],
                            "hit_count": row[2],
                        }
                        for row in rows
                    ] if rows else []
        except Exception as e:
            logger.debug(f"MySQL habits load failed (non-fatal): {e}")
            return []

    def _build_profile_text(
        self, prefs: dict[str, Any], habits: list[dict[str, Any]]
    ) -> str:
        """构建用户画像文本，注入到 Prompt。

        Args:
            prefs: JSON 偏好字典
            habits: MySQL 习惯记录列表

        Returns:
            用户画像文本字符串
        """
        lines: list[str] = []

        # 音乐偏好
        music = prefs.get("music", {})
        if music.get("favorite_songs"):
            songs = "、".join(music["favorite_songs"][:5])
            lines.append(f"喜欢的歌曲：{songs}")
        if music.get("favorite_artists"):
            artists = "、".join(music["favorite_artists"][:3])
            lines.append(f"喜欢的歌手：{artists}")

        # 美食偏好
        food = prefs.get("food", {})
        if food.get("favorite_cuisines"):
            cuisines = "、".join(food["favorite_cuisines"])
            lines.append(f"偏好菜系：{cuisines}")
        if food.get("spicy_tolerance"):
            lines.append(f"辣度偏好：{food['spicy_tolerance']}")
        if food.get("allergies"):
            allergies = "、".join(food["allergies"])
            lines.append(f"过敏食物：{allergies}")

        # 位置偏好
        location = prefs.get("location", {})
        if location.get("frequent_destinations"):
            dests = "、".join(location["frequent_destinations"])
            lines.append(f"常去地点：{dests}")

        # 空调偏好
        climate = prefs.get("climate", {})
        if climate.get("preferred_temp"):
            lines.append(f"偏好空调温度：{climate['preferred_temp']}度")
        if climate.get("preferred_mode"):
            lines.append(f"偏好空调模式：{climate['preferred_mode']}")

        # MySQL 习惯记录（频次加权）
        if habits:
            top_habits = [h["habit_value"] for h in habits[:5] if h.get("habit_value")]
            if top_habits:
                lines.append(f"高频习惯：{'、'.join(top_habits)}")

        return "；".join(lines) if lines else ""

    async def match_music(self, user_id: str) -> list[dict[str, Any]]:
        """根据用户偏好匹配本地音乐播放列表。

        扫描 assets/audio/music/ 目录，与用户偏好的歌曲列表匹配。

        Args:
            user_id: 用户 ID

        Returns:
            匹配的歌曲列表，每项包含 title、filename、url
        """
        prefs = self._load_json_prefs(user_id)
        favorite_songs = prefs.get("music", {}).get("favorite_songs", [])

        # 扫描本地音乐库
        local_songs = self._scan_local_music()

        if not local_songs:
            return []

        if not favorite_songs:
            return local_songs  # 无偏好则返回全部

        # 模糊匹配：用户偏好的歌曲名是否出现在本地文件名中
        matched = []
        for song in local_songs:
            for fav in favorite_songs:
                # 提取歌曲名关键词（去掉歌手部分）
                fav_name = fav.split(" - ")[0] if " - " in fav else fav
                if (
                    fav_name in song["title"]
                    or fav in song["title"]
                    or fav_name in song["filename"]
                ):
                    matched.append(song)
                    break

        return matched if matched else local_songs  # 无匹配则返回全部

    def _scan_local_music(self) -> list[dict[str, Any]]:
        """扫描 assets/audio/music/ 目录，构建本地音乐列表。

        支持的格式: .mp3, .wav

        Returns:
            歌曲列表，每项包含 title、filename、url、format
        """
        music_dir = os.path.join(
            self.config.project_root, "assets", "audio", "music"
        )
        supported_formats = {".mp3", ".wav"}
        playlist: list[dict[str, Any]] = []

        if not os.path.isdir(music_dir):
            logger.warning(f"Music directory not found: {music_dir}")
            return []

        import glob
        for filepath in sorted(glob.glob(os.path.join(music_dir, "*"))):
            ext = os.path.splitext(filepath)[1].lower()
            if ext not in supported_formats:
                continue
            filename = os.path.basename(filepath)
            title = self._parse_title(filename)
            playlist.append({
                "title": title,
                "filename": filename,
                "url": f"/audio/music/{filename}",
                "format": ext.lstrip("."),
            })

        if playlist:
            logger.info(f"Loaded {len(playlist)} songs from {music_dir}")

        return playlist

    @staticmethod
    def _parse_title(filename: str) -> str:
        """从文件名解析歌曲标题。

        "王力宏-爱错.mp3" → "爱错 - 王力宏"
        "周杰伦 - 晴天.wav" → "晴天 - 周杰伦"（已规范则不变）

        Args:
            filename: 音频文件名

        Returns:
            解析后的歌曲标题
        """
        name = os.path.splitext(filename)[0]
        if " - " in name:
            parts = [p.strip() for p in name.split(" - ", 1)]
            return f"{parts[1]} - {parts[0]}" if len(parts) == 2 else name
        elif "-" in name:
            parts = [p.strip() for p in name.split("-", 1)]
            return f"{parts[1]} - {parts[0]}" if len(parts) == 2 else name
        return name

    def save_preferences(
        self, user_id: str, preferences: dict[str, Any]
    ) -> bool:
        """保存用户偏好到 JSON 文件。

        Args:
            user_id: 用户 ID
            preferences: 偏好字典

        Returns:
            是否保存成功
        """
        from datetime import datetime, timezone

        prefs_path = os.path.join(self._prefs_dir, f"{user_id}.json")
        now = datetime.now(timezone.utc).isoformat()

        # 如果文件已存在，更新 updated_at；否则创建新文件
        existing = {}
        if os.path.exists(prefs_path):
            try:
                with open(prefs_path, encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                pass

        existing.update(preferences)
        existing["user_id"] = user_id
        existing["updated_at"] = now
        if "created_at" not in existing:
            existing["created_at"] = now

        try:
            with open(prefs_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
            logger.info(f"Preferences saved for user={user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save preferences for user={user_id}: {e}")
            return False


# 全局单例
_personalization: PersonalizationService | None = None


def get_personalization_service() -> PersonalizationService:
    """获取个性化服务全局单例。"""
    global _personalization
    if _personalization is None:
        _personalization = PersonalizationService()
    return _personalization
