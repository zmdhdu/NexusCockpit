"""
LLM Intent Router — 基于 LLM 的意图路由
使用 Function Calling 从技能列表中选择最合适的技能
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from nexus.config import get_config
from nexus.core.logger import get_logger

logger = get_logger(__name__)


class LLMIntentRouter:
    """LLM 意图路由器"""

    def __init__(
        self,
        llm_client: Optional[AsyncOpenAI] = None,
        llm_model: str = "",
        tool_catalog: Optional[List[dict]] = None,
        min_confidence: float = 0.55,
    ):
        self.config = get_config().llm
        self.client = llm_client or AsyncOpenAI(
            api_key=self.config.ark_api_key,
            base_url=self.config.ark_base_url,
        )
        self.llm_model = llm_model or self.config.llm_model
        self.tool_catalog = tool_catalog or []
        self.min_confidence = min_confidence

    async def route(self, text: str) -> Optional[Dict[str, Any]]:
        """
        使用 LLM 路由意图
        返回: {"selected_tool": "...", "arguments": {...}, "confidence": 0.x, ...}
        """
        if not text.strip() or not self.tool_catalog:
            return None

        prompt = self._build_prompt(text)
        try:
            response = await self.client.chat.completions.create(
                model=self.llm_model,
                messages=prompt,
                temperature=0.0,
            )
            content = (response.choices[0].message.content or "").strip()
            if not content:
                return None
            return self._parse_json(content)
        except Exception as e:
            logger.error(f"LLM routing failed: {e}")
            return None

    def _build_prompt(self, text: str) -> List[Dict[str, str]]:
        tool_catalog_text = json.dumps(self.tool_catalog, ensure_ascii=False, indent=2)
        system_prompt = (
            "你是一个车载语音技能路由器。你的任务不是回答用户，而是从技能列表中选择最合适的一个技能，并提取参数。"
            "如果信息不足、用户意图不明确、或需要补充参数，就返回 need_clarification=true，并给出 clarification_question。"
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
4. 不要编造参数；缺参数时请明确请求澄清。
5. confidence 取 0 到 1 之间的小数。

用户输入:
{text}
""".strip()
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _parse_json(self, content: str) -> Optional[Dict[str, Any]]:
        cleaned = content.replace("```json", "").replace("```", "").strip()
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(0)
        try:
            parsed = json.loads(cleaned)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None

    def decision_to_intent(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """将 LLM 决策转换为标准意图格式"""
        from nexus.intent.router import IntentRouterService
        return IntentRouterService._decision_to_intent_static(decision, self.min_confidence)
