# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
LLM Intent Router — 基于 LLM 的意图路由
使用 Function Calling 从技能列表中选择最合适的技能
"""

from __future__ import annotations

import json
import re
from typing import Any

from nexus.agent.llm_client_factory import get_chat_model
from nexus.config import get_config
from nexus.core.logger import get_logger

logger = get_logger(__name__)


class LLMIntentRouter:
    """LLM 意图路由器"""

    def __init__(
        self,
        llm_client: Any = None,
        llm_model: str = "",
        tool_catalog: list[dict] | None = None,
        min_confidence: float = 0.55,
    ):
        self.config = get_config().llm
        self._chat_model = get_chat_model()
        self.llm_model = llm_model or self.config.llm_model
        self.tool_catalog = tool_catalog or []
        self.min_confidence = min_confidence

    async def route(self, text: str) -> dict[str, Any] | None:
        """使用 LLM 路由意图（带重试机制）。

        改进: JSON 解析失败时自动重试一次，使用更明确的提示词要求 LLM 输出纯 JSON。
        原实现解析失败时静默返回 None，无重试，导致误降级到默认闲聊。

        Returns:
            {"selected_tool": "...", "arguments": {...}, "confidence": 0.x, ...} 或 None
        """
        if not text.strip() or not self.tool_catalog:
            return None

        prompt = self._build_prompt(text)
        try:
            response = await self._chat_model.ainvoke(prompt)
            content = (response.content or "").strip()
            if not content:
                return None

            parsed = self._parse_json(content)
            if parsed is not None:
                return parsed

            # 首次解析失败 — 重试一次，使用更明确的提示词
            logger.warning(
                f"LLM router JSON parse failed on first attempt, retrying. "
                f"Raw content (first 200 chars): {content[:200]}"
            )
            return await self._retry_parse(text)

        except Exception as e:
            logger.error(f"LLM routing failed: {e}")
            return None

    async def _retry_parse(self, text: str) -> dict[str, Any] | None:
        """重试: 使用更强的约束提示词要求 LLM 输出纯 JSON。"""
        retry_prompt = [
            {"role": "system", "content": (
                "你是车载语音技能路由器。上一次输出无法解析为 JSON，请重新输出。\n"
                "严格要求: 只输出一个 JSON 对象，不要输出任何其他文字、Markdown 或解释。\n"
                "JSON 格式: {\"selected_tool\": \"...\", \"arguments\": {...}, "
                "\"confidence\": 0.0, \"need_clarification\": false, "
                "\"clarification_question\": \"\", \"reason\": \"...\"}"
            )},
            {"role": "user", "content": f"用户输入: {text}\n\n请只输出 JSON:"},
        ]
        try:
            response = await self._chat_model.ainvoke(retry_prompt)
            content = (response.content or "").strip()
            if not content:
                return None
            parsed = self._parse_json(content)
            if parsed is not None:
                logger.info("LLM router JSON parse succeeded on retry")
                return parsed
            logger.error(
                f"LLM router JSON parse failed on retry too. "
                f"Raw content (first 300 chars): {content[:300]}"
            )
            return None
        except Exception as e:
            logger.error(f"LLM router retry failed: {e}")
            return None

    def _build_prompt(self, text: str) -> list[dict[str, str]]:
        tool_catalog_text = json.dumps(self.tool_catalog, ensure_ascii=False, indent=2)
        system_prompt = (
            "你是一个车载语音技能路由器。你的任务不是回答用户，而是从技能列表中选择最合适的一个技能，并提取参数。"
            "如果信息不足、用户意图不明确、或需要补充参数，"
            "就返回 need_clarification=true，并给出 clarification_question。"
            "如果是普通闲聊或不需要任何技能，selected_tool 设为 none。"
            "必须只输出 JSON，不要输出解释、Markdown 或多余文本。"
        )
        user_prompt = f"""
技能列表:
{tool_catalog_text}

请根据用户输入选择技能，并严格输出以下 JSON 结构:
{{
  "selected_tool": "skill_name 或 none",
  "arguments": {{"key": "value"}},
  "confidence": 0.0,
  "need_clarification": false,
  "clarification_question": "",
  "reason": "简短原因"
}}

约束:
1. 只能选择技能列表中的 name。
2. 车控类请求优先选择对应 vehicle_* 技能。
3. 搜索、点餐、注册声纹也必须走对应技能。
4. 当用户询问“附近”、“周边”的美食、餐厅、加油站、
   停车场等基于当前位置的信息时，优先选择 amap_poi_search，而非 web_search。
5. 不要编造参数；缺参数时请明确请求澄清。
6. confidence 取 0 到 1 之间的小数。
7. 车辆健康诊断（故障灯、异响、故障码、保养）选择 diagnose_vehicle/decode_dtc/maintenance_advice。
8. 用户习惯画像（记录偏好、习惯推荐、习惯调整）选择 habit_record/habit_recommend/habit_adjust。
9. 日程提醒（设置提醒、查询提醒、取消提醒）选择 set_reminder/query_reminder/cancel_reminder。

用户输入:
{text}
""".strip()
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _parse_json(self, content: str) -> dict[str, Any] | None:
        """解析 LLM 输出为 JSON 字典。

        改进: 使用 Pydantic schema 验证 (intent/schema.py)，
        防止 LLM 输出格式漂移导致路由失效。
        """
        from nexus.intent.schema import parse_intent_decision

        decision = parse_intent_decision(content)
        if decision is None:
            return None
        # 转换为字典格式供 _decision_to_intent_static 使用
        return {
            "selected_tool": decision.selected_tool,
            "arguments": decision.arguments,
            "confidence": decision.confidence,
            "need_clarification": decision.need_clarification,
            "clarification_question": decision.clarification_question,
            "reason": decision.reason,
        }


