# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Skill Base — 技能基类定义 + 装饰器自动注册 (LangChain StructuredTool 接入)

核心特性:
  - @register_skill 装饰器，技能类标记后自动注册到全局表
  - SkillGroup 枚举，标识技能归属的专家
  - BaseSkill 提供 has_side_effect / cache_ttl 属性，用于缓存安全控制
  - SkillRegistry 初始化时自动扫描已注册技能，无需硬编码
  - to_structured_tool() 方法将技能转换为 LangChain StructuredTool

LangChain 接入:
  - 使用 langchain_core.tools.StructuredTool 包装技能
  - 动态创建 Pydantic args_schema 从 self.parameters 字典
  - StructuredTool.coroutine 包装 BaseSkill.execute() 异步调用
  - 保留 get_tool_schema() 返回 OpenAI Function Calling 格式 (向后兼容)

技能分类:
    车载技能: 空调/车窗/座椅/导航/媒体/状态查询
    非车载技能: 联网搜索/外卖点餐/声纹注册
    扩展技能: 习惯画像/日程提醒/车辆健康/本地生活推荐
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SkillGroup(str, Enum):
    """技能分组枚举，对应 5 个专家 Agent。"""
    VEHICLE = "vehicle"        # 车控专家
    NAVIGATION = "navigation"  # 导航专家
    LIFESTYLE = "lifestyle"    # 生活推荐专家
    HEALTH = "health"          # 车辆健康专家
    CHAT = "chat"              # 闲聊专家


# ---- 全局技能注册表 ----
# 装饰器 @register_skill 会将技能类信息写入此表
# SkillRegistry 初始化时自动遍历此表完成注册
_SKILL_REGISTRY: dict[str, dict] = {}


def register_skill(
    name: str,
    group: SkillGroup,
    description: str = "",
    has_side_effect: bool = False,
    cache_ttl: int = 3600,
):
    """技能装饰器：标记技能类并自动注册到全局表。

    用法:
        @register_skill("vehicle_climate", SkillGroup.VEHICLE, has_side_effect=True)
        class ClimateControlSkill(BaseSkill):
            ...

    Args:
        name: 技能唯一标识名
        group: 归属的专家分组
        description: 技能描述（可选，会覆盖类属性）
        has_side_effect: 是否有副作用（车控类=True，禁止缓存）
        cache_ttl: 缓存 TTL 秒数（0=不缓存）
    """
    def decorator(cls):
        # 在类上打标记，SkillRegistry 扫描时识别
        cls._skill_name = name
        cls._skill_group = group
        cls._skill_has_side_effect = has_side_effect
        cls._skill_cache_ttl = cache_ttl
        if description:
            cls.description = description

        # 写入全局注册表
        _SKILL_REGISTRY[name] = {
            "class": cls,
            "group": group,
            "has_side_effect": has_side_effect,
            "cache_ttl": cache_ttl,
        }
        return cls

    return decorator


@dataclass
class SkillResult:
    """技能执行统一结果。

    所有技能的 execute() 方法都返回此对象，便于编排器统一处理。

    Attributes:
        status: 执行状态 (ok/error)
        message: 人类可读的结果描述
        data: 结构化结果数据
        action: 技能动作标识 (如 vehicle_climate)
        search_context: 搜索类技能返回的检索上下文
        handled: 是否被技能处理 (False 表示无匹配技能)
    """
    status: str = "ok"  # ok / error
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    action: str = ""
    search_context: str = ""
    handled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseSkill(ABC):
    """技能基类。

    子类需要实现 execute() 方法定义具体逻辑。
    类属性 (name, description, parameters 等) 描述了技能的元信息，
    用于 LLM 意图路由和 Tool Schema 生成。

    装饰器注入的类属性:
        _skill_name: 由 @register_skill 设置
        _skill_group: 归属专家分组
        _skill_has_side_effect: 是否有副作用（控制缓存）
        _skill_cache_ttl: 缓存 TTL
    """

    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {}
    required_parameters: list[str] = []
    optional_parameters: list[str] = []
    examples: list[dict[str, Any]] = []
    risk_level: str = "low"  # low / medium / high
    timeout_ms: int = 3000
    requires_auth: bool = False
    idempotent: bool = True

    # 装饰器注入的属性
    _skill_name: str = ""
    _skill_group: SkillGroup = SkillGroup.CHAT
    _skill_has_side_effect: bool = False
    _skill_cache_ttl: int = 3600

    async def execute(self, **kwargs: Any) -> SkillResult:
        """执行技能，子类必须实现"""
        raise NotImplementedError

    def get_tool_schema(self) -> dict:
        """返回供大模型识别的 Tool Schema (OpenAI Function Calling 格式)。"""
        required = list(self.required_parameters)
        optional = list(self.optional_parameters) if self.optional_parameters else [
            key for key in self.parameters.keys() if key not in required
        ]
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": required,
                    "additionalProperties": False,
                    "x-llm-hints": {
                        "required": required,
                        "optional": optional,
                        "examples": self.examples,
                    },
                },
            },
        }

    @property
    def has_side_effect(self) -> bool:
        """是否有副作用（车控类=True，禁止缓存）。"""
        return self._skill_has_side_effect

    @property
    def cache_ttl(self) -> int:
        """缓存 TTL 秒数（0=不缓存）。"""
        return self._skill_cache_ttl

    @property
    def group(self) -> SkillGroup:
        """归属的专家分组。"""
        return self._skill_group

    def to_structured_tool(self):
        """将技能转换为 LangChain StructuredTool。

        动态创建 Pydantic args_schema 从 self.parameters 字典，
        包装 BaseSkill.execute() 为 StructuredTool 的异步调用接口。

        Returns:
            langchain_core.tools.StructuredTool 实例
        """
        from langchain_core.tools import StructuredTool
        from pydantic import Field, create_model

        # OpenAPI type -> Python type 映射
        _type_map = {
            "string": str,
            "number": float,
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
        }

        # 动态创建 Pydantic 模型作为 args_schema
        fields: dict[str, Any] = {}
        for param_name, param_info in self.parameters.items():
            if not isinstance(param_info, dict):
                fields[param_name] = (str | None, Field(default=None))
                continue
            type_str = param_info.get("type", "string")
            param_type = _type_map.get(type_str, str)
            description = param_info.get("description", "")
            if param_name in self.required_parameters:
                default = ...  # 必填参数
            else:
                default = None  # 可选参数
            fields[param_name] = (param_type | None, Field(default=default, description=description))

        args_model = create_model(f"{self.name}_args", **fields) if fields else None

        # 异步包装: StructuredTool 调用 execute() 并返回 SkillResult.message
        async def _arun(**kwargs) -> str:
            result = await self.execute(**kwargs)
            return result.message or result.error or ""

        # 同步包装: 创建新事件循环执行 async 调用 (仅用于非 async 上下文)
        def _run(**kwargs) -> str:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 在 async 上下文中，StructuredTool 会自动调用 coroutine
                    raise RuntimeError("Use arun() in async context")
            except RuntimeError:
                raise
            new_loop = asyncio.new_event_loop()
            try:
                result = new_loop.run_until_complete(self.execute(**kwargs))
                return result.message or result.error or ""
            finally:
                new_loop.close()

        return StructuredTool.from_function(
            func=_run,
            coroutine=_arun,
            name=self.name,
            description=self.description,
            args_schema=args_model,
        )

    def __repr__(self) -> str:
        return f"<Skill name={self.name} group={self._skill_group.value} risk={self.risk_level}>"


