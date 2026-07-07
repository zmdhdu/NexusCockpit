"""
Non-vehicle skills: web search, food delivery, voice registration
"""

from __future__ import annotations

import os
from typing import Any, Optional

from nexus.skills.base import BaseSkill, SkillResult
from nexus.core.logger import get_logger

logger = get_logger(__name__)


class WebSearchSkill(BaseSkill):
    """联网搜索技能"""

    name = "web_search"
    description = "当用户询问实时信息、天气、新闻、百科等需要联网查询的内容时调用此技能。"
    required_parameters = ["query"]
    optional_parameters: list[str] = []
    examples = [
        {"input": "明天北京天气怎么样", "arguments": {"query": "明天北京天气怎么样"}},
        {"input": "查一下 DeepSeek 最新模型", "arguments": {"query": "DeepSeek 最新模型"}},
    ]
    parameters = {
        "query": {
            "type": "string",
            "description": "需要搜索引擎查询的具体关键词",
        }
    }

    def __init__(self):
        from nexus.config import get_config
        api_key = get_config().tavily.api_key or os.getenv("TAVILY_API_KEY", "")
        self._client = None
        if api_key:
            try:
                from tavily import TavilyClient
                self._client = TavilyClient(api_key)
            except ImportError:
                logger.warning("tavily-python not installed, web search disabled")

    async def execute(self, query: str = "", **kwargs: Any) -> SkillResult:
        logger.info(f"WebSearch executing: {query}")
        if not self._client:
            return SkillResult(
                status="error",
                message="当前未配置联网搜索密钥，无法执行搜索。",
                action="web_search",
                handled=True,
            )
        try:
            response = self._client.search(query=query, search_depth="basic")
            results = response.get("results", [])[:2]
            if not results:
                return SkillResult(
                    status="ok",
                    message="未检索到相关信息。",
                    action="web_search",
                    handled=True,
                )

            compact = []
            for r in results:
                title = r.get("title", "")[:40]
                content = r.get("content", "").replace("\n", " ")[:160]
                compact.append(f"【{title}】{content}")

            return SkillResult(
                status="ok",
                message="搜索完成",
                search_context="\n".join(compact),
                action="web_search",
                handled=True,
                metadata={"query": query},
            )
        except Exception as e:
            return SkillResult(
                status="error",
                message=f"搜索失败: {e}",
                action="web_search",
                handled=True,
            )


class FoodDeliverySkill(BaseSkill):
    """点餐技能"""

    name = "order_food"
    description = "当用户表达想吃什么、点外卖、饿了等意图时调用此技能。"
    required_parameters = ["food_name"]
    optional_parameters: list[str] = []
    examples = [
        {"input": "我想吃汉堡", "arguments": {"food_name": "汉堡"}},
        {"input": "来一份宫保鸡丁", "arguments": {"food_name": "宫保鸡丁"}},
    ]
    parameters = {
        "food_name": {
            "type": "string",
            "description": "用户想吃的具体食物名称",
        }
    }

    def __init__(self, graph_store=None):
        self.graph_store = graph_store

    async def execute(self, food_name: str = "", **kwargs: Any) -> SkillResult:
        logger.info(f"FoodDelivery executing: {food_name}")
        matched = None
        if self.graph_store and hasattr(self.graph_store, "search_food"):
            matched = self.graph_store.search_food(food_name)
        if matched:
            return SkillResult(
                status="ok",
                message=f"系统已为您在菜单中找到【{matched}】，即将为您下单。",
                action="order_food",
                handled=True,
                metadata={"food_name": food_name, "matched": matched},
            )
        return SkillResult(
            status="ok",
            message=f"抱歉，当前的食材库中没有找到【{food_name}】。",
            action="order_food",
            handled=True,
            metadata={"food_name": food_name},
        )


class RegisterVoiceSkill(BaseSkill):
    """声纹注册技能"""

    name = "register_voice"
    description = "当用户要求注册声纹、记录身份、或说'我是谁谁谁'时调用此技能。"
    required_parameters = ["user_name"]
    optional_parameters: list[str] = []
    examples = [
        {"input": "我是张三", "arguments": {"user_name": "张三"}},
        {"input": "帮我注册声纹，叫我小明", "arguments": {"user_name": "小明"}},
    ]
    parameters = {
        "user_name": {
            "type": "string",
            "description": "用户声明的名字",
        }
    }

    async def execute(self, user_name: str = "Unknown_User", **kwargs: Any) -> SkillResult:
        logger.info(f"VoiceRegister triggered: {user_name}")
        return SkillResult(
            status="ok",
            message=f"ACTION_REGISTER:{user_name}",
            action="register_voice",
            handled=True,
            metadata={"user_name": user_name},
        )
