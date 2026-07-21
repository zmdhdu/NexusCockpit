# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Vehicle Expert — 车控专家 Agent

封装车控类技能：空调/车窗/座椅/媒体/状态查询。
从 intent 中提取车控动作字段，分发到对应技能执行。
"""

from __future__ import annotations

from typing import Any

from nexus.agent.experts.base import BaseExpertAgent
from nexus.core.logger import get_logger
from nexus.models.state import SupervisorState
from nexus.skills.base import SkillGroup

logger = get_logger(__name__)

# intent 字段 → 技能名映射
_VEHICLE_ACTION_MAP = {
    "Climate_Action": "vehicle_climate",
    "Window_Action": "vehicle_window",
    "Seat_Action": "vehicle_seat",
    "Media_Action": "vehicle_media",
    "Vehicle_Status_Action": "vehicle_status",
}


class VehicleExpert(BaseExpertAgent):
    """车控专家：处理空调/车窗/座椅/媒体/状态查询。"""

    expert_name = "vehicle"
    group = SkillGroup.VEHICLE

    async def _execute(self, state: SupervisorState) -> dict[str, Any]:
        intent = state.get("intent", {})

        for intent_key, tool_name in _VEHICLE_ACTION_MAP.items():
            action_data = intent.get(intent_key) or {}
            if action_data:
                # 过滤 None 值
                cleaned = {k: v for k, v in action_data.items() if v is not None}
                result = await self.registry.execute(tool_name, cleaned)

                # 车控指令执行后验证结果
                # 确保命令确实改变了车辆状态，而非空返回 success
                verified = self._verify_result(tool_name, result, cleaned)

                expert_result = self._build_expert_result(
                    action=tool_name,
                    reply=verified.message,
                    handled=verified.handled,
                    skill_status=verified.status,
                    skill_data=verified.data,
                    skip_synthesis=True,  # 车控指令直接使用工具返回的自然语言消息，跳过 LLM 合成
                )
                # 标记有副作用（车控指令修改了车辆状态），禁止缓存
                expert_result["has_side_effect"] = True
                return expert_result

        # 无匹配车控动作
        return self._build_expert_result(
            action="",
            reply="",
            handled=False,
        )

    def _verify_result(self, tool_name: str, result: Any, args: dict[str, Any]) -> Any:
        """验证车控命令执行结果。

        检查工具返回的 data 是否反映了预期的状态变更，
        避免返回成功但实际未变动的问题。

        Args:
            tool_name: 技能名称（如 vehicle_climate）
            result: SkillResult 执行结果
            args: 原始命令参数

        Returns:
            验证后的 SkillResult（可能修正 message 和 status）
        """
        from nexus.skills.base import SkillResult

        if not result.handled:
            return result

        data = result.data or {}

        # 空调温度验证
        if tool_name == "vehicle_climate" and "climate" in data:
            climate = data["climate"]
            target_temp = args.get("target_temp")
            if target_temp is not None:
                actual_temp = climate.get("temperature")
                if actual_temp is not None and int(actual_temp) != int(target_temp):
                    logger.warning(
                        f"Climate verification FAILED: target={target_temp}, actual={actual_temp}"
                    )
                    return SkillResult(
                        status="error",
                        message=f"空调温度设置失败，目标 {target_temp} 度，当前 {actual_temp} 度，请重试。",
                        data=data,
                        error="temp_mismatch",
                        action=tool_name,
                        handled=True,
                    )

        # 车窗位置验证
        if tool_name == "vehicle_window" and "windows" in data:
            windows = data["windows"]
            position = args.get("position", "all")
            target_percent = args.get("percent")
            op = args.get("op", "")
            if target_percent is not None:
                actual = windows.get(position, windows.get("all"))
                if actual is not None and int(actual) != int(target_percent):
                    logger.warning(
                        f"Window verification FAILED: pos={position}, target={target_percent}%, actual={actual}%"
                    )
                    return SkillResult(
                        status="error",
                        message=f"车窗设置失败，目标 {target_percent}%，当前 {actual}%，请重试。",
                        data=data,
                        error="position_mismatch",
                        action=tool_name,
                        handled=True,
                    )
            elif op in ("open", "close"):
                expected = 100 if op == "open" else 0
                actual = windows.get(position, windows.get("all"))
                if actual is not None and int(actual) != expected:
                    logger.warning(
                        f"Window verification FAILED: op={op}, pos={position}, expected={expected}%, actual={actual}%"
                    )
                    return SkillResult(
                        status="error",
                        message=f"车窗{op}失败，当前 {actual}%，请重试。",
                        data=data,
                        error="position_mismatch",
                        action=tool_name,
                        handled=True,
                    )

        # 媒体播放验证
        if tool_name == "vehicle_media" and "media" in data:
            media = data["media"]
            op = args.get("op", "")
            if op == "play" and not media.get("playing"):
                logger.warning("Media verification FAILED: play requested but not playing")
                return SkillResult(
                    status="error",
                    message="播放失败，请重试。",
                    data=data,
                    error="play_failed",
                    action=tool_name,
                    handled=True,
                )
            elif op == "pause" and media.get("playing"):
                logger.warning("Media verification FAILED: pause requested but still playing")
                return SkillResult(
                    status="error",
                    message="暂停失败，请重试。",
                    data=data,
                    error="pause_failed",
                    action=tool_name,
                    handled=True,
                )

        logger.info(f"Vehicle command verified OK: {tool_name}")
        return result
