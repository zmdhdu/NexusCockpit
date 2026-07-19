# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Skill Registry — 技能注册中心

核心特性:
  - 装饰器自动发现 + 手动注册兼容
  - 按 SkillGroup 分组查询接口（供专家 Agent 使用）
  - has_side_effect / cache_ttl 查询接口（供缓存层使用）

技能注册方式:
  1. 装饰器自动注册: @register_skill("name", SkillGroup.XXX) 标记技能类
  2. 手动注册: registry.register("name", skill_instance)
  注册中心初始化时自动扫描全局 _SKILL_REGISTRY 表完成实例化
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from nexus.core.logger import get_logger
from nexus.skills.base import (
    BaseSkill,
    SkillGroup,
    SkillResult,
    _SKILL_REGISTRY,
    register_skill,  # 导出供技能模块使用
)

logger = get_logger(__name__)


class SkillRegistry:
    """技能注册中心。

    初始化流程:
      1. 扫描 _SKILL_REGISTRY 全局表，获取所有用 @register_skill 标记的技能类
      2. 实例化每个技能类（通过 factory 回调注入 graph_store / vehicle_adapter 等依赖）
      3. 同时支持手动 register() 注册

    Args:
        graph_store: Neo4j 图谱存储（供点餐/习惯技能查询）
        vehicle_adapter: 车控适配器（供车载技能发送指令）
    """

    def __init__(self, graph_store=None, vehicle_adapter=None):
        self._skills: Dict[str, BaseSkill] = {}
        self._deps = {
            "graph_store": graph_store,
            "vehicle_adapter": vehicle_adapter,
        }

        # 1. 自动扫描装饰器注册的技能
        self._auto_discover()

        # 2. 注册未被装饰器标记的技能
        self._register_legacy_skills()

        logger.info(f"SkillRegistry initialized with {len(self._skills)} skills: {list(self._skills.keys())}")

    def _auto_discover(self) -> None:
        """扫描全局 _SKILL_REGISTRY 表，实例化所有装饰器注册的技能。"""
        for skill_name, info in _SKILL_REGISTRY.items():
            if skill_name in self._skills:
                continue  # 已注册（可能是手动注册的），跳过

            cls = info["class"]
            try:
                instance = self._instantiate(cls)
                self._skills[skill_name] = instance
                logger.debug(f"Auto-registered skill: {skill_name} ({info['group'].value})")
            except Exception as e:
                logger.error(f"Failed to instantiate skill '{skill_name}': {e}")

    def _instantiate(self, cls: type[BaseSkill]) -> BaseSkill:
        """根据技能类的 __init__ 签名智能注入依赖。"""
        import inspect

        sig = inspect.signature(cls.__init__)
        kwargs: Dict[str, Any] = {}

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue
            # 按参数名匹配依赖
            if param_name in self._deps:
                kwargs[param_name] = self._deps[param_name]
            elif param.default is not inspect.Parameter.empty:
                # 有默认值的参数跳过
                pass
            # 无默认值且无法注入的参数，让 Python 抛出 TypeError

        return cls(**kwargs)

    def _register_legacy_skills(self) -> None:
        """注册未被 @register_skill 标记的旧技能。"""
        # 如果已经用 @register_skill 标记，_auto_discover 已处理
        # 这里只处理未标记的旧技能（通过检查 _SKILL_REGISTRY 是否覆盖了它们）
        from nexus.skills.special import AmapPoiSearchSkill, FoodDeliverySkill, RegisterVoiceSkill, WebSearchSkill
        from nexus.skills.vehicle.climate import ClimateControlSkill
        from nexus.skills.vehicle.media import MediaControlSkill
        from nexus.skills.vehicle.navigation import NavigationSkill
        from nexus.skills.vehicle.seat import SeatControlSkill
        from nexus.skills.vehicle.status import VehicleStatusSkill
        from nexus.skills.vehicle.window import WindowControlSkill

        legacy_map = {
            "web_search": (WebSearchSkill, {}),
            "order_food": (FoodDeliverySkill, {"graph_store": self._deps["graph_store"]}),
            "amap_poi_search": (AmapPoiSearchSkill, {}),
            "register_voice": (RegisterVoiceSkill, {}),
            "vehicle_climate": (ClimateControlSkill, {"adapter": self._deps["vehicle_adapter"]} if self._deps["vehicle_adapter"] else {}),
            "vehicle_window": (WindowControlSkill, {"adapter": self._deps["vehicle_adapter"]} if self._deps["vehicle_adapter"] else {}),
            "vehicle_seat": (SeatControlSkill, {"adapter": self._deps["vehicle_adapter"]} if self._deps["vehicle_adapter"] else {}),
            "vehicle_navigation": (NavigationSkill, {"adapter": self._deps["vehicle_adapter"]} if self._deps["vehicle_adapter"] else {}),
            "vehicle_media": (MediaControlSkill, {"adapter": self._deps["vehicle_adapter"]} if self._deps["vehicle_adapter"] else {}),
            "vehicle_status": (VehicleStatusSkill, {"adapter": self._deps["vehicle_adapter"]} if self._deps["vehicle_adapter"] else {}),
        }

        for name, (cls, kwargs) in legacy_map.items():
            if name not in self._skills:
                try:
                    # 过滤 None 值
                    clean_kwargs = {k: v for k, v in kwargs.items() if v is not None}
                    self._skills[name] = cls(**clean_kwargs) if clean_kwargs else cls()
                    # 设置分组（旧技能未标记装饰器的，手动设置）
                    if not hasattr(self._skills[name], "_skill_group") or self._skills[name]._skill_group == SkillGroup.CHAT:
                        if name.startswith("vehicle_"):
                            self._skills[name]._skill_group = SkillGroup.VEHICLE
                            self._skills[name]._skill_has_side_effect = True
                            self._skills[name]._skill_cache_ttl = 0
                        elif name == "order_food" or name == "web_search" or name == "amap_poi_search":
                            self._skills[name]._skill_group = SkillGroup.LIFESTYLE
                        elif name == "register_voice":
                            self._skills[name]._skill_group = SkillGroup.CHAT
                except Exception as e:
                    logger.error(f"Failed to register legacy skill '{name}': {e}")

    def register(self, name: str, skill: BaseSkill) -> None:
        """手动注册技能。"""
        self._skills[name] = skill

    def get_skill(self, name: str) -> Optional[BaseSkill]:
        """获取技能实例。"""
        return self._skills.get(name)

    def list_skills(self) -> List[str]:
        """列出所有技能名称。"""
        return list(self._skills.keys())

    def get_all_tools(self) -> List[dict]:
        """获取所有技能的 Tool Schema。"""
        return [skill.get_tool_schema() for skill in self._skills.values()]

    def get_skills_by_group(self, group: SkillGroup) -> Dict[str, BaseSkill]:
        """按专家分组获取技能（供专家 Agent 使用）。"""
        return {
            name: skill for name, skill in self._skills.items()
            if getattr(skill, "_skill_group", SkillGroup.CHAT) == group
        }

    def get_side_effect_skills(self) -> List[str]:
        """获取所有有副作用的技能名称（供缓存层使用）。"""
        return [
            name for name, skill in self._skills.items()
            if getattr(skill, "_skill_has_side_effect", False)
        ]

    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> SkillResult:
        """执行指定技能。"""
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
