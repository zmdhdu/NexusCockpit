# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""媒体状态模型 + 媒体控制方法 + 音频播放列表扫描。"""

from __future__ import annotations

import glob
import os
import random
from typing import Any

from nexus.core.logger import get_logger
from nexus.vehicle.base import VehicleCommandResult

logger = get_logger(__name__)

# 项目根目录: backend_design/nexus/vehicle/mock/media_state.py → 向上五级
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)


class MediaState:
    """媒体状态管理 + 音频播放列表扫描。"""

    def __init__(self):
        # 动态扫描音频目录，构建播放列表
        self._playlist: list[dict[str, Any]] = self._scan_music_dir()
        self._track_index = 0
        self.media: dict[str, Any] = {
            "playing": False,
            "volume": 18,
            "source": "local",
            "track": self._playlist[0] if self._playlist else None,
            "track_index": 0,
            "play_mode": "sequential",  # sequential / single / shuffle
            "playlist": list(self._playlist),
        }

    def _scan_music_dir(self) -> list[dict[str, Any]]:
        """扫描 assets/audio/music/ 目录，构建播放列表。"""
        music_dir = os.path.join(_PROJECT_ROOT, "assets", "audio", "music")
        supported_formats = {".mp3", ".wav"}
        playlist: list[dict[str, Any]] = []

        if os.path.isdir(music_dir):
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

        if not playlist:
            logger.warning(f"No audio files found in {music_dir}")
        else:
            logger.info(f"Loaded {len(playlist)} songs from {music_dir}")

        return playlist

    @staticmethod
    def _parse_title(filename: str) -> str:
        """从文件名解析歌曲标题。

        "王力宏-爱错.mp3" → "爱错 - 王力宏"
        """
        name = os.path.splitext(filename)[0]
        if " - " in name:
            parts = [p.strip() for p in name.split(" - ", 1)]
            return f"{parts[1]} - {parts[0]}" if len(parts) == 2 else name
        elif "-" in name:
            parts = [p.strip() for p in name.split("-", 1)]
            return f"{parts[1]} - {parts[0]}" if len(parts) == 2 else name
        return name

    # 合法操作符枚举
    _VALID_OPS = frozenset({
        "play", "pause", "stop", "next", "next_track", "prev", "previous_track",
        "resume", "set_volume", "volume", "set_source", "set_play_mode", "play_mode",
        "play_track", "select_track", "status", "query", "query_status",
    })

    def handle(
        self,
        op: str = "play",
        source: str | None = None,
        track: str | None = None,
        volume: int | None = None,
        play_mode: str | None = None,
    ) -> VehicleCommandResult:
        # 操作符校验 — 非法 op 直接返回错误
        if op not in self._VALID_OPS:
            return VehicleCommandResult(
                success=False,
                message=f"不支持的媒体操作: {op}",
                error="invalid_op",
                data={"media": dict(self.media)},
            )

        # 设置播放模式
        if op in ("set_play_mode", "play_mode"):
            valid_modes = ("sequential", "single", "shuffle")
            if play_mode and play_mode in valid_modes:
                self.media["play_mode"] = play_mode
                mode_names = {"sequential": "列表循环", "single": "单曲循环", "shuffle": "随机播放"}
                return VehicleCommandResult(
                    success=True,
                    message=f"播放模式已切换为{mode_names.get(play_mode, play_mode)}。",
                    data={"media": dict(self.media)},
                )
            return VehicleCommandResult(
                success=False,
                message=f"不支持的播放模式: {play_mode}",
                error="invalid_play_mode",
                data={"media": dict(self.media)},
            )

        if op in ("set_volume", "volume"):
            if volume is not None:
                self.media["volume"] = max(0, min(30, int(volume)))
            return VehicleCommandResult(
                success=True,
                message=f"已将音量调整到 {self.media['volume']}。",
                data={"media": dict(self.media)},
            )

        if op in ("set_source",):
            if source:
                self.media["source"] = source
            return VehicleCommandResult(
                success=True,
                message=f"已将媒体来源切换为 {self.media['source']}。",
                data={"media": dict(self.media)},
            )

        if op in ("status", "query", "query_status"):
            return VehicleCommandResult(
                success=True,
                message=f"媒体状态：{self.media}",
                data={"media": dict(self.media)},
            )

        if source:
            self.media["source"] = source
        if track:
            self.media["track"] = track
        if volume is not None:
            self.media["volume"] = max(0, min(30, int(volume)))

        if op in ("play", "resume"):
            self.media["playing"] = True
            if not self.media.get("track") and self._playlist:
                self.media["track"] = self._playlist[self._track_index]
        elif op == "pause":
            # 暂停: 记住当前播放进度，可恢复
            self.media["playing"] = False
        elif op == "stop":
            # 停止: 停止播放并重置到第一首
            self.media["playing"] = False
            self._track_index = 0
            if self._playlist:
                self.media["track"] = self._playlist[0]
                self.media["track_index"] = 0
        elif op in ("next", "next_track"):
            if self._playlist:
                mode = self.media.get("play_mode", "sequential")
                if mode == "shuffle":
                    if len(self._playlist) > 1:
                        new_idx = random.randint(0, len(self._playlist) - 1)
                        while new_idx == self._track_index:
                            new_idx = random.randint(0, len(self._playlist) - 1)
                        self._track_index = new_idx
                    else:
                        self._track_index = 0
                else:
                    self._track_index = (self._track_index + 1) % len(self._playlist)
                self.media["track"] = self._playlist[self._track_index]
                self.media["track_index"] = self._track_index
                self.media["playing"] = True
        elif op in ("prev", "previous_track"):
            if self._playlist:
                mode = self.media.get("play_mode", "sequential")
                if mode == "shuffle":
                    if len(self._playlist) > 1:
                        new_idx = random.randint(0, len(self._playlist) - 1)
                        while new_idx == self._track_index:
                            new_idx = random.randint(0, len(self._playlist) - 1)
                        self._track_index = new_idx
                    else:
                        self._track_index = 0
                else:
                    self._track_index = (self._track_index - 1) % len(self._playlist)
                self.media["track"] = self._playlist[self._track_index]
                self.media["track_index"] = self._track_index
                self.media["playing"] = True
        elif op in ("play_track", "select_track"):
            if track is not None and self._playlist:
                if isinstance(track, int) or (isinstance(track, str) and track.isdigit()):
                    idx = int(track)
                    if 0 <= idx < len(self._playlist):
                        self._track_index = idx
                else:
                    for i, t in enumerate(self._playlist):
                        if track in t["title"] or track in t["filename"]:
                            self._track_index = i
                            break
                self.media["track"] = self._playlist[self._track_index]
                self.media["track_index"] = self._track_index
                self.media["playing"] = True

        self.media["playlist"] = list(self._playlist)

        return VehicleCommandResult(
            success=True,
            message=f"已执行媒体操作 {op}。当前音量 {self.media['volume']}。",
            data={"media": dict(self.media)},
        )
