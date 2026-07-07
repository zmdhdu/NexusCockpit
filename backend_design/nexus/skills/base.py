"""
Skill Base — 技能基类定义

所有车载/搜索/点餐等技能均继承 BaseSkill，实现 execute() 方法。
技能系统采用统一接口设计，便于编排器 (Orchestrator) 统一调度。

技能分类:
    车载技能: 空调/车窗/座椅/导航/媒体/状态查询
    非车载技能: 联网搜索/外卖点餐/声纹注册
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


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
    data: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    action: str = ""  # 技能动作标识，如 "vehicle_climate", "web_search"
    search_context: str = ""  # 搜索类技能返回的检索上下文
    handled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseSkill(ABC):
    """技能基类。

    子类需要实现 execute() 方法定义具体逻辑。
    类属性 (name, description, parameters 等) 描述了技能的元信息，
    用于 LLM 意图路由和 Tool Schema 生成。

    Attributes:
        name: 技能名称 (唯一标识)
        description: 技能描述 (供 LLM 理解技能用途)
        parameters: 参数定义 (JSON Schema 格式)
        required_parameters: 必填参数列表
        risk_level: 风险等级 (low/medium/high)，影响执行前是否需确认
        timeout_ms: 执行超时时间 (毫秒)
        idempotent: 是否幂等 (重复执行结果相同)
    """

    name: str = ""
    description: str = ""
    parameters: Dict[str, Any] = {}
    required_parameters: list[str] = []
    optional_parameters: list[str] = []
    examples: list[Dict[str, Any]] = []
    risk_level: str = "low"  # low / medium / high
    timeout_ms: int = 3000
    requires_auth: bool = False
    idempotent: bool = True

    async def execute(self, **kwargs: Any) -> SkillResult:
        """执行技能，子类必须实现"""
        raise NotImplementedError

    def get_tool_schema(self) -> dict:
        """返回供大模型识别的 Tool Schema (OpenAI Function Calling 格式)。

        LLM 通过此 schema 理解每个技能的参数和用途，
        从而正确地将用户意图路由到对应技能。
        """
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

    def __repr__(self) -> str:
        return f"<Skill name={self.name} risk={self.risk_level}>"
