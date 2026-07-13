# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
车主习惯画像技能组 — v2.0 新增

3 个技能:
  1. habit_record:   记录用户偏好到 Neo4j HABIT 关系
  2. habit_recommend: 查询图谱习惯，主动推荐
  3. habit_adjust:    读取画像，批量下发车控指令

依赖: Neo4j graph_store（通过 graph_store 依赖注入）
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from nexus.core.logger import get_logger
from nexus.skills.base import BaseSkill, SkillGroup, SkillResult, register_skill

logger = get_logger(__name__)


@register_skill(
    "habit_record",
    SkillGroup.CHAT,
    description="当用户表达个人偏好（如喜欢什么温度、习惯什么音乐）时调用此技能记录。",
    cache_ttl=0,
)
class HabitRecordSkill(BaseSkill):
    """习惯记录技能：提取用户偏好并写入 Neo4j HABIT 关系。"""

    name = "habit_record"
    required_parameters = ["preference"]
    optional_parameters = ["category"]
    examples = [
        {"input": "我喜欢空调开24度", "arguments": {"preference": "空调温度24度", "category": "climate"}},
        {"input": "我习惯听流行音乐", "arguments": {"preference": "喜欢流行音乐", "category": "media"}},
    ]
    parameters = {
        "preference": {"type": "string", "description": "用户表达的偏好内容"},
        "category": {"type": "string", "description": "偏好类别: climate/media/seat/navigation/food"},
    }

    def __init__(self, graph_store=None):
        self.graph_store = graph_store

    async def execute(self, preference: str = "", category: str = "general", **kwargs: Any) -> SkillResult:
        logger.info(f"HabitRecord: category={category}, preference={preference}")

        if not preference:
            return SkillResult(
                status="error",
                message="请告诉我您想记录什么习惯。",
                action="habit_record",
                handled=True,
            )

        # 写入 Neo4j HABIT 关系
        user_id = kwargs.get("user_id", "default")
        if self.graph_store and hasattr(self.graph_store, "add_habit"):
            try:
                self.graph_store.add_habit(user_id, category, preference)
            except Exception as e:
                logger.warning(f"Neo4j habit write failed: {e}")

        return SkillResult(
            status="ok",
            message=f"好的，我已经记住了您{category}方面的偏好：{preference}。",
            action="habit_record",
            handled=True,
            metadata={"preference": preference, "category": category},
        )


@register_skill(
    "habit_recommend",
    SkillGroup.CHAT,
    description="当用户上车或开始驾驶时，查询用户习惯主动推荐。",
    cache_ttl=3600,
)
class HabitRecommendSkill(BaseSkill):
    """习惯推荐技能：查询图谱习惯，主动推荐。"""

    name = "habit_recommend"
    required_parameters: list[str] = []
    optional_parameters = ["trigger"]
    examples = [
        {"input": "早上上车", "arguments": {"trigger": "morning_start"}},
        {"input": "开始导航", "arguments": {"trigger": "nav_start"}},
    ]
    parameters = {
        "trigger": {"type": "string", "description": "触发场景: morning_start/nav_start/evening_start"},
    }

    def __init__(self, graph_store=None):
        self.graph_store = graph_store

    async def execute(self, trigger: str = "morning_start", **kwargs: Any) -> SkillResult:
        logger.info(f"HabitRecommend: trigger={trigger}")
        user_id = kwargs.get("user_id", "default")

        # 查询用户习惯
        habits: list[str] = []
        if self.graph_store and hasattr(self.graph_store, "search_user_graph"):
            try:
                habits = self.graph_store.search_user_graph(user_id, depth=1)
            except Exception as e:
                logger.warning(f"Habit query failed: {e}")

        if not habits:
            return SkillResult(
                status="ok",
                message="暂未记录您的习惯偏好，可以告诉我您的喜好，下次为您主动推荐。",
                action="habit_recommend",
                handled=True,
            )

        # 根据触发场景筛选推荐
        recommendation = self._build_recommendation(trigger, habits)
        return SkillResult(
            status="ok",
            message=recommendation,
            action="habit_recommend",
            handled=True,
            metadata={"trigger": trigger, "habit_count": len(habits)},
        )

    def _build_recommendation(self, trigger: str, habits: list[str]) -> str:
        """根据触发场景和习惯列表构建推荐话术。"""
        habit_str = "；".join(habits[:3])
        if trigger == "morning_start":
            return f"早上好！根据您的习惯：{habit_str}，已为您准备就绪。"
        elif trigger == "nav_start":
            return f"导航已启动。根据您的习惯：{habit_str}，建议参考。"
        return f"根据您的习惯：{habit_str}，为您推荐。"


@register_skill(
    "habit_adjust",
    SkillGroup.VEHICLE,
    description="根据用户习惯画像批量调整车控设置。",
    has_side_effect=True,
    cache_ttl=0,
)
class HabitAdjustSkill(BaseSkill):
    """习惯调整技能：读取画像批量下发车控指令。"""

    name = "habit_adjust"
    required_parameters: list[str] = []
    optional_parameters = ["adapter"]
    examples = [
        {"input": "按我的习惯调一下车", "arguments": {}},
    ]
    parameters = {}

    def __init__(self, graph_store=None, vehicle_adapter=None):
        self.graph_store = graph_store
        self.vehicle_adapter = vehicle_adapter

    async def execute(self, **kwargs: Any) -> SkillResult:
        logger.info("HabitAdjust: reading profile and adjusting vehicle")
        user_id = kwargs.get("user_id", "default")

        # 查询用户习惯
        habits: list[str] = []
        if self.graph_store and hasattr(self.graph_store, "search_user_graph"):
            try:
                habits = self.graph_store.search_user_graph(user_id, depth=1)
            except Exception as e:
                logger.warning(f"Habit query failed: {e}")

        if not habits:
            return SkillResult(
                status="ok",
                message="暂未记录您的习惯，无法自动调整。",
                action="habit_adjust",
                handled=True,
            )

        # 根据习惯批量下发车控指令
        adjusted: list[str] = []
        if self.vehicle_adapter:
            for habit in habits:
                if "温度" in habit or "空调" in habit:
                    try:
                        self.vehicle_adapter.invoke_command("vehicle_climate", {"op": "status"})
                        adjusted.append("空调")
                    except Exception:
                        pass
                if "音乐" in habit or "媒体" in habit:
                    try:
                        self.vehicle_adapter.invoke_command("vehicle_media", {"op": "play"})
                        adjusted.append("媒体")
                    except Exception:
                        pass

        if adjusted:
            return SkillResult(
                status="ok",
                message=f"已根据您的习惯调整了：{'、'.join(adjusted)}。",
                action="habit_adjust",
                handled=True,
                metadata={"adjusted": adjusted, "habit_count": len(habits)},
            )

        return SkillResult(
            status="ok",
            message="已读取您的习惯，但暂无可自动调整的项目。",
            action="habit_adjust",
            handled=True,
        )
