# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""Media Control Skill"""

from __future__ import annotations

from typing import Any

from nexus.skills.base import SkillResult
from nexus.skills.vehicle import VehicleBaseSkill


class MediaControlSkill(VehicleBaseSkill):
    name = "vehicle_media"
    tool_name = "vehicle_media"
    description = "控制车机媒体播放、暂停、切歌和音量。"
    required_parameters: list[str] = []
    optional_parameters = ["op", "source", "track", "volume"]
    examples = [
        {"input": "播放音乐", "arguments": {"op": "play", "source": "local"}},
        {"input": "下一首", "arguments": {"op": "next"}},
        {"input": "音量调到16", "arguments": {"op": "set_volume", "volume": 16}},
        {"input": "切换到蓝牙", "arguments": {"op": "set_source", "source": "bluetooth"}},
    ]
    parameters = {
        "op": {"type": "string", "description": "操作类型，例如 play、pause、next、prev"},
        "source": {"type": "string", "description": "媒体来源，例如 local、bluetooth、radio"},
        "track": {"type": "string", "description": "指定曲目或内容"},
        "volume": {"type": "integer", "description": "音量大小，0 到 30"},
    }

    async def execute(self, **kwargs: Any) -> SkillResult:
        return self._invoke(kwargs)
