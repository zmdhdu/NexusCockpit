# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
LLM Output Schema — Pydantic 模型验证 LLM 结构化输出

为 LLMIntentRouter 和 ReflectionNode 的 LLM 输出提供 Pydantic schema 验证，
防止 LLM 输出格式漂移导致路由失效或反思静默失败。

使用方式:
    from nexus.intent.schema import IntentDecision, ReflectionResult

    # 意图路由 LLM 输出验证
    try:
        decision = IntentDecision.model_validate_json(content)
    except ValidationError:
        # 格式异常，降级处理
        pass

    # 反思 LLM 输出验证
    try:
        reflection = ReflectionResult.model_validate_json(content)
    except ValidationError:
        pass
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, ValidationError


class IntentDecision(BaseModel):
    """LLM 意图路由决策的 schema 验证模型。"""

    selected_tool: str = Field(description="技能名称或 none")
    arguments: dict[str, Any] = Field(default_factory=dict, description="技能参数")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="置信度 0-1")
    need_clarification: bool = Field(default=False, description="是否需要澄清")
    clarification_question: str = Field(default="", description="澄清问题")
    reason: str = Field(default="", description="简短原因")


class MultiIntentDecision(BaseModel):
    """LLM 多意图路由决策的 schema 验证模型。

    支持复合查询场景：用户单条输入包含多个不同类型的需求时，
    LLM 需要识别所有适用的技能并返回列表。
    """

    tools: list[IntentDecision] = Field(
        default_factory=list,
        description="识别到的所有技能列表，每个元素是一个 IntentDecision",
    )
    need_clarification: bool = Field(default=False, description="是否需要澄清")
    clarification_question: str = Field(default="", description="澄清问题")
    reason: str = Field(default="", description="简短原因")


class ReflectionResult(BaseModel):
    """反思 LLM 输出的 schema 验证模型。"""

    valid: bool = Field(description="是否合格")
    reason: str = Field(default="", description="简短原因")
    suggested_response: str = Field(default="", description="修正后的回复（不合格时）")


def parse_intent_decision(content: str) -> IntentDecision | None:
    """安全解析 LLM 意图路由输出。

    Args:
        content: LLM 返回的原始文本

    Returns:
        IntentDecision 实例，或 None（解析失败）
    """
    import json
    import re

    cleaned = content.replace("```json", "").replace("```", "").strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)

    try:
        data = json.loads(cleaned)
        return IntentDecision.model_validate(data)
    except (json.JSONDecodeError, ValidationError, Exception):
        return None


def parse_multi_intent_decision(content: str) -> MultiIntentDecision | None:
    """安全解析 LLM 多意图路由输出。

    支持两种 LLM 响应格式:
        1. 标准 multi 格式: {"tools": [{...}, {...}], ...}
        2. 兼容单工具格式: {"selected_tool": "...", ...} → 自动包装为单元素列表

    Args:
        content: LLM 返回的原始文本

    Returns:
        MultiIntentDecision 实例，或 None（解析失败）
    """
    import json
    import re

    cleaned = content.replace("```json", "").replace("```", "").strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)

    try:
        data = json.loads(cleaned)
        # 兼容: 如果 LLM 返回单工具格式（无 tools 字段但有 selected_tool），
        # 自动包装为 multi 格式
        if "tools" not in data and "selected_tool" in data:
            data = {
                "tools": [{
                    "selected_tool": data.get("selected_tool", ""),
                    "arguments": data.get("arguments", {}),
                    "confidence": data.get("confidence", 0.0),
                    "need_clarification": data.get("need_clarification", False),
                    "clarification_question": data.get("clarification_question", ""),
                    "reason": data.get("reason", ""),
                }],
                "need_clarification": data.get("need_clarification", False),
                "clarification_question": data.get("clarification_question", ""),
                "reason": data.get("reason", ""),
            }
        return MultiIntentDecision.model_validate(data)
    except (json.JSONDecodeError, ValidationError, Exception):
        return None


def parse_reflection_result(content: str) -> ReflectionResult | None:
    """安全解析反思 LLM 输出。

    Args:
        content: LLM 返回的原始文本

    Returns:
        ReflectionResult 实例，或 None（解析失败）
    """
    import json
    import re

    cleaned = content.replace("```json", "").replace("```", "").strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)

    try:
        data = json.loads(cleaned)
        return ReflectionResult.model_validate(data)
    except (json.JSONDecodeError, ValidationError, Exception):
        return None
