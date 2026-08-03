# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Lifestyle Expert — 生活推荐专家 Agent

封装生活类技能：联网搜索、外卖点餐、本地生活推荐。
"""

from __future__ import annotations

import asyncio
from typing import Any

from nexus.agent.experts.base import BaseExpertAgent
from nexus.core.logger import get_logger
from nexus.models.state import SupervisorState
from nexus.skills.base import SkillGroup

logger = get_logger(__name__)


class LifestyleExpert(BaseExpertAgent):
    """生活推荐专家：处理搜索、点餐、本地推荐。"""

    expert_name = "lifestyle"
    group = SkillGroup.LIFESTYLE

    def _verify_result(self, result: Any, action: str = "") -> str:
        """验证生活推荐技能执行结果。

        检查项:
            - 执行状态是否为 error
            - 结果消息是否为空
        """
        if result.status == "error":
            logger.warning(f"LifestyleExpert verify: skill '{action}' returned error: {result.message}")
            return result.message or "生活服务暂时不可用，请稍后重试。"
        if not result.message or len(result.message.strip()) < 2:
            logger.warning(f"LifestyleExpert verify: skill '{action}' returned empty message")
            return "服务已处理，但未返回详细信息。"
        return result.message

    async def _execute(self, state: SupervisorState) -> dict[str, Any]:
        """执行生活类技能 — 支持多动作并行执行。

        底层修复: 原实现使用 if/elif 优先级链，只执行第一个匹配的动作，
        导致用户复合指令（如"查天气+搜索新闻"）只执行天气查询，搜索被丢弃。

        现改为: 遍历所有匹配的技能动作，用 asyncio.gather 并行执行，
        将所有结果聚合为 expert_results 列表返回，由 DispatchNode 统一合并。

        互斥检测: 天气查询与联网搜索存在语义重叠（天气也可通过搜索获取），
        当 Weather_Action 命中时，跳过 Need_Search，避免重复查询。
        """
        intent = state.get("intent", {})
        cockpit_id = state.get("cockpit_id", "")
        key_context = state.get("key_context", {})

        # ---- 收集所有匹配的原子任务 ----
        # 每个原子任务是一个 async 函数，返回 (action, reply, search_context, handled, status, extra)
        atomic_tasks: list = []
        matched_actions: list[str] = []

        # 原子任务 0: 高德 POI 周边搜索
        poi_action = intent.get("Poi_Search_Action") or {}
        if poi_action and isinstance(poi_action, dict) and poi_action.get("keyword"):
            async def _do_poi():
                poi_kwargs = {
                    "keyword": poi_action.get("keyword", ""),
                    "poi_type": poi_action.get("poi_type", ""),
                    "radius": poi_action.get("radius", 3000),
                    "cockpit_id": cockpit_id,
                }
                result = await self.registry.execute("amap_poi_search", poi_kwargs)
                return (
                    "amap_poi_search",
                    result.message if result.status == "ok" else "",
                    result.search_context if result.status == "ok" else "",
                    result.handled,
                    result.status,
                    {},
                )
            atomic_tasks.append(_do_poi())
            matched_actions.append("amap_poi_search")

        # 原子任务 1: 天气查询
        weather_action = intent.get("Weather_Action") or {}
        weather_matched = False
        if weather_action and isinstance(weather_action, dict) and weather_action.get("query"):
            async def _do_weather():
                weather_kwargs: dict[str, Any] = {
                    "query": weather_action.get("query", ""),
                    "cockpit_id": cockpit_id,
                }
                if key_context:
                    weather_kwargs["key_context"] = key_context
                result = await self.registry.execute("weather_query", weather_kwargs)
                return (
                    "weather_query",
                    result.message if result.status == "ok" else "",
                    result.search_context if result.status == "ok" else "",
                    result.handled,
                    result.status,
                    {},
                )
            atomic_tasks.append(_do_weather())
            matched_actions.append("weather_query")
            weather_matched = True

        # 原子任务 2: 联网搜索 — 与天气查询互斥（避免重复查询天气信息）
        search_query = intent.get("Need_Search") or ""
        if (
            search_query
            and isinstance(search_query, str)
            and search_query.strip()
            and not weather_matched  # 天气查询已命中时跳过搜索，避免重复
        ):
            async def _do_search():
                search_kwargs: dict[str, Any] = {"query": search_query.strip()}
                if key_context:
                    search_kwargs["key_context"] = key_context
                result = await self.registry.execute("web_search", search_kwargs)
                return (
                    "web_search",
                    result.message if result.status == "error" else "",
                    result.search_context,
                    result.handled,
                    result.status,
                    {},
                )
            atomic_tasks.append(_do_search())
            matched_actions.append("web_search")

        # 原子任务 3: 点餐
        if intent.get("Call_elm"):
            food_name = (intent.get("Food_candidate") or "").strip() or "随便来点"
            async def _do_food():
                result = await self.registry.execute("order_food", {"food_name": food_name})
                return (
                    "order_food",
                    result.message,
                    "",
                    result.handled,
                    result.status,
                    {},
                )
            atomic_tasks.append(_do_food())
            matched_actions.append("order_food")

        # 原子任务 4: 日程提醒
        reminder_action = intent.get("Reminder_Action") or {}
        if reminder_action and isinstance(reminder_action, dict) and reminder_action.get("skill"):
            skill_name = reminder_action.get("skill")
            reminder_kwargs = {k: v for k, v in reminder_action.items() if k != "skill" and v is not None}
            async def _do_reminder():
                result = await self.registry.execute(skill_name, reminder_kwargs)
                return (
                    skill_name,
                    result.message,
                    "",
                    result.handled,
                    result.status,
                    {},
                )
            atomic_tasks.append(_do_reminder())
            matched_actions.append(skill_name)

        # ---- 无匹配时返回空结果 ----
        if not atomic_tasks:
            return self._build_expert_result(action="", reply="", handled=False)

        # ---- 并行执行所有原子任务 ----
        if len(atomic_tasks) == 1:
            # 单任务直接 await，避免 gather 开销
            results = [await atomic_tasks[0]]
        else:
            # 多任务并行执行
            logger.info(
                f"LifestyleExpert multi-action parallel: actions={matched_actions}, "
                f"count={len(atomic_tasks)}"
            )
            results = await asyncio.gather(*atomic_tasks, return_exceptions=True)

        # ---- 聚合所有结果 ----
        expert_results: list[dict[str, Any]] = []
        merged_search_context = ""
        primary_action = ""
        primary_handled = False
        primary_tool_result: dict[str, Any] = {}
        all_metadata: dict[str, Any] = {}

        for i, res in enumerate(results):
            action_name = matched_actions[i]
            if isinstance(res, Exception):
                logger.error(f"LifestyleExpert action '{action_name}' failed: {res}")
                expert_results.append({
                    "expert": self.expert_name,
                    "action": action_name,
                    "reply": "",
                    "search_context": "",
                    "handled": False,
                    "error": str(res),
                })
                all_metadata[f"{action_name}_error"] = str(res)
                continue

            action, reply, search_ctx, handled, status, extra = res
            expert_results.append({
                "expert": self.expert_name,
                "action": action,
                "reply": reply,
                "search_context": search_ctx,
                "handled": handled,
                "skill_status": status,
                **extra,
            })
            # 合并 search_context（多个搜索结果拼接）
            if search_ctx:
                if merged_search_context:
                    merged_search_context = f"{merged_search_context}\n{search_ctx}"
                else:
                    merged_search_context = search_ctx
            # 第一个 handled=True 的结果作为主结果（用于 skill_action / tool_result）
            if handled and not primary_handled:
                primary_action = action
                primary_handled = True
                if reply or extra.get("skill_data"):
                    primary_tool_result = {
                        "tool_name": action,
                        "message": reply,
                        "data": extra.get("skill_data", {}),
                        "handled": handled,
                        "expert": self.expert_name,
                    }
            all_metadata[f"{action}_status"] = status

        # ---- 构建合并后的 partial state update ----
        update: dict[str, Any] = {
            "expert_results": expert_results,
            "skill_action": primary_action,
            "skill_handled": primary_handled,
            "search_context": merged_search_context,
            "metadata": all_metadata,
        }
        # 如果有工具结果，提升到顶层 state
        if primary_tool_result and primary_handled:
            update["tool_result"] = primary_tool_result

        logger.info(
            f"LifestyleExpert done: actions={matched_actions}, "
            f"results={len(expert_results)}, handled={primary_handled}"
        )
        return update
