# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Intent Router Service — 统一意图路由服务

判断用户输入应该交给哪个技能处理，是 Agent 工作流的关键第一步。

三级路由策略 (按优先级降级):
  Level 1: 启发式路由 — 基于关键词规则匹配 (快速免费)
  Level 2: LLM 路由 — 让大模型理解语义并选择技能 (最准确)
  Level 3: 默认闲聊 — 无匹配技能时走 LLM 闲聊

v2.2 简化: BERT 路由 (Level 3) 已移除（始终为 None，从未实现）
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from openai import AsyncOpenAI

from nexus.config import get_config
from nexus.core.logger import get_logger
from nexus.intent.heuristic import HeuristicRouter
from nexus.intent.llm_router import LLMIntentRouter

logger = get_logger(__name__)


class IntentRouterService:
    """统一意图路由服务。

    路由优先级: 启发式规则 → LLM → 默认闲聊。
    v2.2 简化: BERT 路由分支已移除（始终为 None，从未实现）

    Args:
        llm_client: OpenAI 兼容的 LLM 客户端
        llm_model: LLM 模型名称
        tool_catalog: 技能 Tool Schema 列表 (供 LLM 理解可用技能)
        llm_enabled: 是否启用 LLM 路由
        min_confidence: LLM 路由最低置信度阈值
    """

    REQUIRED_KEYS = (
        "Call_elm", "Food_candidate", "Need_Search", "Register_Action",
        "Climate_Action", "Window_Action", "Seat_Action",
        "Navigation_Action", "Media_Action", "Vehicle_Status_Action",
        "Poi_Search_Action",  # v2.2.3: 高德 POI 周边搜索
    )

    def __init__(
        self,
        llm_client: Optional[AsyncOpenAI] = None,
        llm_model: str = "",
        tool_catalog: Optional[list[dict]] = None,
        llm_enabled: bool = True,
        min_confidence: float = 0.55,
    ):
        self.config = get_config().llm
        self.client = llm_client or AsyncOpenAI(
            api_key=self.config.ark_api_key,
            base_url=self.config.ark_base_url,
        )
        self.llm_model = llm_model or self.config.llm_model
        # v2.2 简化: bert_router 参数已移除（始终为 None，从未实现）
        self.llm_enabled = llm_enabled and self.client is not None and bool(tool_catalog)
        self.min_confidence = min_confidence
        self.heuristic = HeuristicRouter()
        self.llm_router = LLMIntentRouter(
            llm_client=self.client,
            llm_model=self.llm_model,
            tool_catalog=tool_catalog or [],
            min_confidence=min_confidence,
        ) if self.llm_enabled else None

    async def route(self, text: str) -> Dict[str, Any]:
        """路由用户意图，返回标准意图字典。

        优化路由顺序（v2.1 性能优化）:
          Level 1: 启发式规则 — 关键词匹配，<1ms，覆盖常见车控指令
          Level 2: LLM 路由 — 语义理解，1-3s，处理复杂/模糊意图
          Level 3: 默认闲聊

        v2.2 简化: BERT 路由分支已移除（始终为 None，从未实现）

        Args:
            text: 用户输入文本

        Returns:
            包含各技能动作字段的意图字典
        """
        default = self._build_default_intent()

        # Level 1: 启发式规则（快速路径，<1ms）
        # 常见车控指令（空调/车窗/座椅/导航/音乐/车况）直接命中，无需等 LLM
        heuristic_intent = self.heuristic.route(text)
        if heuristic_intent:
            return {**default, **heuristic_intent, "Route_Source": "heuristic"}

        # Level 2: LLM 路由（慢速路径，1-3s）
        # 启发式未命中时，用 LLM 理解复杂/模糊意图
        if self.llm_enabled and self.llm_router:
            try:
                decision = await self.llm_router.route(text)
                if decision:
                    resolved = self._decision_to_intent(decision)
                    if resolved:
                        return resolved
            except Exception as e:
                logger.warning(f"LLM routing failed, falling back: {e}")

        # Level 3: 默认闲聊
        return default

    def _build_default_intent(self) -> Dict[str, Any]:
        return {
            "Call_elm": False,
            "Food_candidate": "",
            "Need_Search": "",
            "Register_Action": "",
            "Climate_Action": {},
            "Window_Action": {},
            "Seat_Action": {},
            "Navigation_Action": {},
            "Media_Action": {},
            "Vehicle_Status_Action": {},
            "Poi_Search_Action": {},  # v2.2.3: 高德 POI 周边搜索
            "Need_Clarification": False,
            "Clarification_Prompt": "",
            "Route_Source": "default",
            "Route_Confidence": 0.0,
        }

    def _decision_to_intent(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """将 LLM 决策转换为标准意图格式"""
        return self._decision_to_intent_static(decision, self.min_confidence)

    @staticmethod
    def _decision_to_intent_static(decision: Dict[str, Any], min_confidence: float = 0.55) -> Dict[str, Any]:
        """静态方法: LLM 决策 → 标准意图"""
        default = IntentRouterService()._build_default_intent()
        tool_name = str(decision.get("selected_tool") or "").strip()
        arguments = decision.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {}

        confidence = 0.0
        try:
            confidence = float(decision.get("confidence", 0))
        except Exception:
            pass

        need_clarification = bool(decision.get("need_clarification"))
        clarification_question = str(decision.get("clarification_question") or "").strip()

        if need_clarification or confidence < min_confidence or not tool_name or tool_name.lower() in {"none", "chat", "default"}:
            if clarification_question:
                default["Need_Clarification"] = True
                default["Clarification_Prompt"] = clarification_question
                default["Route_Source"] = "llm_clarify"
                default["Route_Confidence"] = confidence
            return default if default["Need_Clarification"] else {}

        return IntentRouterService._tool_to_legacy_intent(tool_name, arguments, confidence)

    @staticmethod
    def _tool_to_legacy_intent(tool_name: str, arguments: Dict[str, Any], confidence: float = 0.0) -> Dict[str, Any]:
        """工具名 → 遗留意图格式"""
        default = IntentRouterService()._build_default_intent()
        tool_name = tool_name.strip()

        if tool_name == "web_search":
            query = str(arguments.get("query") or "").strip()
            if not query:
                return {}
            default["Need_Search"] = query
            default["Route_Source"] = "llm"
            default["Route_Confidence"] = confidence
            return default

        if tool_name == "amap_poi_search":
            keyword = str(arguments.get("keyword") or "").strip()
            if not keyword:
                return {}
            default["Poi_Search_Action"] = {
                "keyword": keyword,
                "poi_type": str(arguments.get("poi_type") or ""),
                "radius": arguments.get("radius", 3000),
            }
            default["Route_Source"] = "llm"
            default["Route_Confidence"] = confidence
            return default

        if tool_name == "order_food":
            food = str(arguments.get("food_name") or "").strip()
            if not food:
                return {}
            default["Call_elm"] = True
            default["Food_candidate"] = food
            default["Route_Source"] = "llm"
            default["Route_Confidence"] = confidence
            return default

        if tool_name == "register_voice":
            default["Register_Action"] = str(arguments.get("user_name") or "Unknown_User").strip() or "Unknown_User"
            default["Route_Source"] = "llm"
            default["Route_Confidence"] = confidence
            return default

        if tool_name == "vehicle_climate":
            default["Climate_Action"] = {
                "op": str(arguments.get("op") or "status"),
                "target_temp": arguments.get("target_temp"),
                "delta": arguments.get("delta"),
                "fan_speed": arguments.get("fan_speed"),
                "mode": arguments.get("mode"),
            }
            default["Route_Source"] = "llm"
            default["Route_Confidence"] = confidence
            return default

        if tool_name == "vehicle_window":
            default["Window_Action"] = {
                "op": str(arguments.get("op") or "status"),
                "position": str(arguments.get("position") or "all"),
                "percent": arguments.get("percent"),
            }
            default["Route_Source"] = "llm"
            default["Route_Confidence"] = confidence
            return default

        if tool_name == "vehicle_seat":
            default["Seat_Action"] = {
                "op": str(arguments.get("op") or "status"),
                "position": str(arguments.get("position") or "driver"),
                "level": arguments.get("level"),
                "direction": arguments.get("direction"),
            }
            default["Route_Source"] = "llm"
            default["Route_Confidence"] = confidence
            return default

        if tool_name == "vehicle_navigation":
            op = str(arguments.get("op") or "").strip()
            dest = str(arguments.get("destination") or "").strip()

            # 位置查询（op=location 或类似值）不需要目的地
            if op in ("location", "current_location", "where", "位置", "我在哪"):
                default["Navigation_Action"] = {
                    "op": "location",
                    "destination": "",
                    "waypoint": "",
                    "mode": "drive",
                }
                default["Route_Source"] = "llm"
                default["Route_Confidence"] = confidence
                return default

            # 导航到目的地需要 destination
            if not dest:
                return {}
            default["Navigation_Action"] = {
                "destination": dest,
                "waypoint": str(arguments.get("waypoint") or ""),
                "mode": str(arguments.get("mode") or "drive"),
            }
            default["Route_Source"] = "llm"
            default["Route_Confidence"] = confidence
            return default

        if tool_name == "vehicle_media":
            default["Media_Action"] = {
                "op": str(arguments.get("op") or "play"),
                "source": arguments.get("source"),
                "track": arguments.get("track"),
                "volume": arguments.get("volume"),
            }
            default["Route_Source"] = "llm"
            default["Route_Confidence"] = confidence
            return default

        if tool_name == "vehicle_status":
            op = str(arguments.get("op") or "status")
            default["Vehicle_Status_Action"] = {"op": op}
            default["Route_Source"] = "llm"
            default["Route_Confidence"] = confidence
            return default

        return {}
