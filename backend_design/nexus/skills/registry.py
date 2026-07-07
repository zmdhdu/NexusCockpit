"""
Skill Registry — 技能注册中心

本模块是所有技能的统一管理入口，负责:
  1. 注册所有车载和非车载技能
  2. 提供技能查询接口
  3. 生成 LLM 可识别的 Tool Schema 列表
  4. 执行指定技能并返回结果
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from nexus.core.logger import get_logger
from nexus.skills.base import BaseSkill, SkillResult
from nexus.skills.special import FoodDeliverySkill, RegisterVoiceSkill, WebSearchSkill
from nexus.skills.vehicle.climate import ClimateControlSkill
from nexus.skills.vehicle.media import MediaControlSkill
from nexus.skills.vehicle.navigation import NavigationSkill
from nexus.skills.vehicle.seat import SeatControlSkill
from nexus.skills.vehicle.status import VehicleStatusSkill
from nexus.skills.vehicle.window import WindowControlSkill

logger = get_logger(__name__)


class SkillRegistry:
    """技能注册中心。

    初始化时自动注册所有 9 个技能 (3 非车载 + 6 车载)。

    Args:
        graph_store: Neo4j 图谱存储 (供点餐技能查询食物知识)
        vehicle_adapter: 车控适配器 (供车载技能发送指令)
    """

    def __init__(self, graph_store=None, vehicle_adapter=None):
        self._skills: Dict[str, BaseSkill] = {}

        # 注册非车载技能
        self.register("web_search", WebSearchSkill())
        self.register("order_food", FoodDeliverySkill(graph_store))
        self.register("register_voice", RegisterVoiceSkill())

        # 注册车载技能
        vehicle_kwargs = {"adapter": vehicle_adapter} if vehicle_adapter else {}
        self.register("vehicle_climate", ClimateControlSkill(**vehicle_kwargs))
        self.register("vehicle_window", WindowControlSkill(**vehicle_kwargs))
        self.register("vehicle_seat", SeatControlSkill(**vehicle_kwargs))
        self.register("vehicle_navigation", NavigationSkill(**vehicle_kwargs))
        self.register("vehicle_media", MediaControlSkill(**vehicle_kwargs))
        self.register("vehicle_status", VehicleStatusSkill(**vehicle_kwargs))

        logger.info(f"SkillRegistry initialized with {len(self._skills)} skills")

    def register(self, name: str, skill: BaseSkill) -> None:
        """注册技能"""
        self._skills[name] = skill

    def get_skill(self, name: str) -> Optional[BaseSkill]:
        """获取技能实例"""
        return self._skills.get(name)

    def list_skills(self) -> List[str]:
        """列出所有技能名称"""
        return list(self._skills.keys())

    def get_all_tools(self) -> List[dict]:
        """获取所有技能的 Tool Schema"""
        return [skill.get_tool_schema() for skill in self._skills.values()]

    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> SkillResult:
        """执行指定技能"""
        skill = self._skills.get(tool_name)
        if not skill:
            return SkillResult(
                status="error",
                message="未知技能",
                error=f"skill_not_found:{tool_name}",
                action=tool_name,
                handled=False,
            )

        try:
            # 清理 None 值参数
            cleaned = {k: v for k, v in arguments.items() if v is not None}
            result = await skill.execute(**cleaned)
            return result
        except Exception as e:
            logger.error(f"Skill execution failed: {tool_name} -> {e}")
            return SkillResult(
                status="error",
                message=f"技能执行失败: {e}",
                error=str(e),
                action=tool_name,
                handled=False,
            )
