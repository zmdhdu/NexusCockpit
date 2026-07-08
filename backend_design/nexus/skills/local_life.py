"""
本地生活推荐技能组 — v2.0 新增

3 个技能:
  1. recommend_poi:      周边餐饮/景点检索+距离排序
  2. multi_turn_refine:  多轮填充推荐槽位，保留上下文
  3. preference_filter:  基于用户偏好筛选候选推荐结果

依赖: Neo4j graph_store（POI 检索）
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from nexus.core.logger import get_logger
from nexus.skills.base import BaseSkill, SkillGroup, SkillResult, register_skill

logger = get_logger(__name__)


@register_skill(
    "recommend_poi",
    SkillGroup.LIFESTYLE,
    description="当用户询问周边餐饮、景点、加油站、停车场等地点推荐时调用此技能。",
    cache_ttl=3600,
)
class RecommendPoiSkill(BaseSkill):
    """POI 推荐技能：周边兴趣点检索+距离排序。"""

    name = "recommend_poi"
    required_parameters = ["poi_type"]
    optional_parameters = ["radius", "user_id"]
    examples = [
        {"input": "附近有什么好吃的", "arguments": {"poi_type": "restaurant"}},
        {"input": "周边加油站", "arguments": {"poi_type": "gas_station"}},
    ]
    parameters = {
        "poi_type": {"type": "string", "description": "地点类型: restaurant/gas_station/parking/attraction"},
        "radius": {"type": "integer", "description": "搜索半径（米），默认3000"},
    }

    def __init__(self, graph_store=None):
        self.graph_store = graph_store

    async def execute(self, poi_type: str = "", radius: int = 3000, **kwargs: Any) -> SkillResult:
        logger.info(f"RecommendPoi: type={poi_type}, radius={radius}")

        if not poi_type:
            return SkillResult(
                status="error",
                message="请告诉我您想找什么类型的地点。",
                action="recommend_poi",
                handled=True,
            )

        # 查询图谱 POI
        pois: List[str] = []
        if self.graph_store and hasattr(self.graph_store, "search_poi"):
            try:
                pois = self.graph_store.search_poi(poi_type, radius)
            except Exception as e:
                logger.warning(f"POI search failed: {e}")

        type_map = {
            "restaurant": "餐饮",
            "gas_station": "加油站",
            "parking": "停车场",
            "attraction": "景点",
        }
        type_name = type_map.get(poi_type, poi_type)

        if not pois:
            return SkillResult(
                status="ok",
                message=f"暂未找到附近的{type_name}推荐，请扩大搜索范围试试。",
                action="recommend_poi",
                handled=True,
            )

        # 格式化推荐列表
        poi_list = "\n".join(f"• {p}" for p in pois[:5])
        message = f"为您推荐以下{type_name}：\n{poi_list}"
        return SkillResult(
            status="ok",
            message=message,
            action="recommend_poi",
            handled=True,
            metadata={"poi_type": poi_type, "count": len(pois)},
        )


@register_skill(
    "multi_turn_refine",
    SkillGroup.LIFESTYLE,
    description="当用户在推荐过程中补充偏好（如价格、距离、口味）进行多轮细化时调用此技能。",
    cache_ttl=0,
)
class MultiTurnRefineSkill(BaseSkill):
    """多轮细化推荐技能：填充槽位，保留上下文。"""

    name = "multi_turn_refine"
    required_parameters = ["refinement"]
    optional_parameters = ["slot", "user_id"]
    examples = [
        {"input": "便宜一点的", "arguments": {"refinement": "便宜", "slot": "price"}},
        {"input": "近一点的", "arguments": {"refinement": "距离近", "slot": "distance"}},
    ]
    parameters = {
        "refinement": {"type": "string", "description": "用户补充的偏好描述"},
        "slot": {"type": "string", "description": "槽位名称: price/distance/cuisine/rating"},
    }

    def __init__(self, graph_store=None):
        self.graph_store = graph_store

    async def execute(self, refinement: str = "", slot: str = "", **kwargs: Any) -> SkillResult:
        logger.info(f"MultiTurnRefine: slot={slot}, refinement={refinement}")

        if not refinement:
            return SkillResult(
                status="error",
                message="请告诉我您想怎么调整推荐。",
                action="multi_turn_refine",
                handled=True,
            )

        # 存储用户偏好到图谱（多轮上下文）
        user_id = kwargs.get("user_id", "default")
        if self.graph_store and hasattr(self.graph_store, "add_habit"):
            try:
                self.graph_store.add_habit(user_id, f"preference_{slot}", refinement)
            except Exception:
                pass

        # 重新查询并筛选
        pois: List[str] = []
        if self.graph_store and hasattr(self.graph_store, "search_poi"):
            try:
                pois = self.graph_store.search_poi("restaurant", 5000)
            except Exception:
                pass

        if pois:
            filtered = [p for p in pois if refinement in p]
            if filtered:
                poi_list = "\n".join(f"• {p}" for p in filtered[:3])
                return SkillResult(
                    status="ok",
                    message=f"根据您「{refinement}」的偏好，为您筛选：\n{poi_list}",
                    action="multi_turn_refine",
                    handled=True,
                    metadata={"slot": slot, "filtered_count": len(filtered)},
                )

        return SkillResult(
            status="ok",
            message=f"已记录您的偏好「{refinement}」，但暂未找到更匹配的结果。",
            action="multi_turn_refine",
            handled=True,
        )


@register_skill(
    "preference_filter",
    SkillGroup.LIFESTYLE,
    description="当需要根据用户历史偏好自动筛选推荐结果时调用此技能。",
    cache_ttl=3600,
)
class PreferenceFilterSkill(BaseSkill):
    """偏好筛选技能：基于用户画像筛选候选。"""

    name = "preference_filter"
    required_parameters = ["candidates"]
    optional_parameters = ["user_id"]
    examples = [
        {"input": "帮我从这些里选一个", "arguments": {"candidates": "餐厅A,餐厅B,餐厅C"}},
    ]
    parameters = {
        "candidates": {"type": "string", "description": "候选项列表（逗号分隔）"},
    }

    def __init__(self, graph_store=None):
        self.graph_store = graph_store

    async def execute(self, candidates: str = "", **kwargs: Any) -> SkillResult:
        logger.info(f"PreferenceFilter: candidates={candidates}")

        if not candidates:
            return SkillResult(
                status="error",
                message="请提供候选项。",
                action="preference_filter",
                handled=True,
            )

        user_id = kwargs.get("user_id", "default")

        # 查询用户偏好
        preferences: List[str] = []
        if self.graph_store and hasattr(self.graph_store, "search_user_graph"):
            try:
                preferences = self.graph_store.search_user_graph(user_id, depth=1)
            except Exception:
                pass

        candidate_list = [c.strip() for c in candidates.split(",") if c.strip()]

        # 简单偏好匹配
        if preferences:
            scored = []
            for cand in candidate_list:
                score = sum(1 for pref in preferences if any(kw in cand for kw in pref.split()))
                scored.append((cand, score))
            scored.sort(key=lambda x: x[1], reverse=True)
            best = scored[0][0] if scored else candidate_list[0]
        else:
            best = candidate_list[0]

        return SkillResult(
            status="ok",
            message=f"根据您的偏好，推荐选择：{best}",
            action="preference_filter",
            handled=True,
            metadata={"best": best, "candidate_count": len(candidate_list)},
        )
