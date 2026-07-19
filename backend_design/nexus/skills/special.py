# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Non-vehicle skills: web search, food delivery, voice registration
"""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from nexus.skills.base import BaseSkill, SkillResult
from nexus.core.logger import get_logger

# 东八区时区 (UTC+8)，确保无论服务器在什么时区都能获取正确的中国时间
_CN_TZ = timezone(timedelta(hours=8))


def _now_cn() -> datetime:
    """获取当前东八区时间，避免 Docker 容器 UTC 时区导致时间偏差。"""
    return datetime.now(_CN_TZ)

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
            # 在搜索查询中注入当前日期和时间，提高时效性
            # 使用东八区时间，避免 Docker 容器 UTC 时区导致时间偏差
            now = _now_cn()
            today_str = now.strftime("%Y年%m月%d日")
            time_str = now.strftime("%H:%M")
            enhanced_query = f"{query} {today_str} {time_str}"
            logger.info(f"WebSearch enhanced query: {enhanced_query}")
            
            response = self._client.search(query=enhanced_query, search_depth="basic")
            results = response.get("results", [])[:3]
            if not results:
                return SkillResult(
                    status="ok",
                    message="未检索到相关信息。",
                    action="web_search",
                    handled=True,
                )

            compact = []
            for r in results:
                title = r.get("title", "")[:60]
                content = r.get("content", "").replace("\n", " ")[:300]
                url = r.get("url", "")
                compact.append(f"【{title}】{content}\n来源: {url}")

            # 在搜索结果中注入当前时间，供 LLM 和反思节点使用
            # 使用东八区时间
            current_time = _now_cn().strftime("%Y-%m-%d %H:%M")
            time_prefix = f"[当前时间: {current_time}]\n"
            
            return SkillResult(
                status="ok",
                message="搜索完成",
                search_context=time_prefix + "\n".join(compact),
                action="web_search",
                handled=True,
                metadata={"query": query, "search_time": current_time},
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


class AmapPoiSearchSkill(BaseSkill):
    """高德地图 POI 周边搜索技能

    使用高德地图 Web API 搜索当前位置周边的兴趣点（POI），
    包括餐厅、加油站、停车场、景点等。

    特性:
        - 替代原来通过 Tavily 搜索周边美食的方式（结果不准确）
        - 直接使用高德 POI API 获取真实商家信息
        - 支持多种 POI 类型：餐饮、加油站、停车场、景点、超市等
    """

    name = "amap_poi_search"
    description = (
        "当用户询问周边美食、附近餐厅、周边加油站、附近停车场、周边景点等"
        "基于当前位置的地点推荐时调用此技能。"
    )
    required_parameters = ["keyword"]
    optional_parameters = ["poi_type", "radius", "cockpit_id"]
    examples = [
        {"input": "附近有什么好吃的", "arguments": {"keyword": "餐厅", "poi_type": "restaurant"}},
        {"input": "周边加油站", "arguments": {"keyword": "加油站", "poi_type": "gas_station"}},
        {"input": "附近停车场", "arguments": {"keyword": "停车场", "poi_type": "parking"}},
    ]
    parameters = {
        "keyword": {
            "type": "string",
            "description": "搜索关键词，如：餐厅、美食、加油站、停车场、景点、超市",
        },
        "poi_type": {
            "type": "string",
            "description": "POI 类型: restaurant/gas_station/parking/attraction/supermarket",
        },
        "radius": {
            "type": "integer",
            "description": "搜索半径（米），默认 3000",
        },
    }

    # POI 类型 → 高德分类代码映射
    POI_TYPE_MAP = {
        "restaurant": "050000",      # 餐饮服务
        "gas_station": "010000",     # 汽车服务（含加油站）
        "parking": "150900",         # 停车场
        "attraction": "110200",      # 风景名胜
        "supermarket": "060101",     # 超级市场
        "hotel": "100000",           # 住宿服务
        "hospital": "090000",        # 医疗保健
        "bank": "160000",            # 银行
    }

    def __init__(self):
        from nexus.config import get_config
        self._amap_key = get_config().amap.api_key

    async def execute(
        self,
        keyword: str = "",
        poi_type: str = "",
        radius: int = 3000,
        cockpit_id: str = "",
        **kwargs: Any,
    ) -> SkillResult:
        logger.info(f"AmapPoiSearch: keyword={keyword}, type={poi_type}, radius={radius}")

        if not self._amap_key:
            return SkillResult(
                status="error",
                message="当前未配置高德地图 API Key，无法搜索周边信息。请在 .env.local 中设置 AMAP_KEY。",
                action="amap_poi_search",
                handled=True,
            )

        # 从 vehicle adapter 获取缓存的 GPS 坐标
        lat, lon = self._get_gps_coords(cockpit_id)
        if lat is None or lon is None:
            return SkillResult(
                status="error",
                message="无法获取当前位置坐标，请确保浏览器已授权定位。",
                action="amap_poi_search",
                handled=True,
            )

        try:
            import httpx

            # 构建高德 POI 搜索请求
            params: dict[str, Any] = {
                "key": self._amap_key,
                "location": f"{lon},{lat}",
                "keywords": keyword or "餐厅",
                "radius": radius,
                "sortrule": "distance",  # 按距离排序
                "output": "json",
                "offset": 10,  # 返回 10 条
                "extensions": "all",  # 返回详细信息
            }

            # 映射 POI 类型到高德分类代码
            if poi_type and poi_type in self.POI_TYPE_MAP:
                params["types"] = self.POI_TYPE_MAP[poi_type]

            resp = httpx.get(
                "https://restapi.amap.com/v3/place/around",
                params=params,
                timeout=5.0,
            )

            if resp.status_code != 200:
                logger.error(f"Amap POI search HTTP error: {resp.status_code}")
                return SkillResult(
                    status="error",
                    message="周边搜索服务暂时不可用，请稍后重试。",
                    action="amap_poi_search",
                    handled=True,
                )

            data = resp.json()
            if data.get("status") != "1":
                logger.error(f"Amap POI search failed: {data.get('info', 'unknown')}")
                return SkillResult(
                    status="error",
                    message=f"周边搜索失败: {data.get('info', '服务异常')}",
                    action="amap_poi_search",
                    handled=True,
                )

            pois = data.get("pois", [])
            if not pois:
                return SkillResult(
                    status="ok",
                    message=f"在您周边 {radius} 米范围内未找到相关地点，可以尝试扩大搜索范围。",
                    action="amap_poi_search",
                    handled=True,
                )

            # 格式化搜索结果
            type_name = {
                "restaurant": "餐厅",
                "gas_station": "加油站",
                "parking": "停车场",
                "attraction": "景点",
                "supermarket": "超市",
                "hotel": "酒店",
                "hospital": "医院",
                "bank": "银行",
            }.get(poi_type, "地点")

            poi_list = []
            for i, poi in enumerate(pois[:8], 1):
                name = poi.get("name", "")
                address = poi.get("address", "") or "地址不详"
                distance = poi.get("distance", "")
                tel = poi.get("tel", "") or ""

                # 高德返回的 distance 单位为米
                if distance:
                    try:
                        dist_m = int(distance)
                        if dist_m >= 1000:
                            distance_str = f"{dist_m / 1000:.1f}公里"
                        else:
                            distance_str = f"{dist_m}米"
                    except ValueError:
                        distance_str = distance
                else:
                    distance_str = "未知"

                line = f"{i}. {name}\n   地址: {address}\n   距离: {distance_str}"
                if tel:
                    line += f"\n   电话: {tel}"
                poi_list.append(line)

            result_text = f"为您找到以下周边{type_name}（共 {len(pois)} 个）：\n\n" + "\n\n".join(poi_list)

            logger.info(f"AmapPoiSearch done: found {len(pois)} POIs for '{keyword}'")

            return SkillResult(
                status="ok",
                message=result_text,
                action="amap_poi_search",
                handled=True,
                search_context=result_text,
                metadata={
                    "keyword": keyword,
                    "poi_type": poi_type,
                    "count": len(pois),
                    "center": f"{lat},{lon}",
                    "radius": radius,
                },
            )

        except Exception as e:
            logger.error(f"AmapPoiSearch failed: {e}")
            return SkillResult(
                status="error",
                message=f"周边搜索出现错误: {e}",
                action="amap_poi_search",
                handled=True,
            )

    def _get_gps_coords(self, cockpit_id: str = "") -> tuple:
        """从 vehicle adapter 获取缓存的 GPS 坐标。"""
        try:
            from nexus.vehicle.factory import get_cockpit_vehicle_adapter
            if cockpit_id:
                adapter = get_cockpit_vehicle_adapter(cockpit_id)
                if adapter and hasattr(adapter, "navigation"):
                    lat = adapter.navigation.get("latitude")
                    lon = adapter.navigation.get("longitude")
                    if lat is not None and lon is not None:
                        return float(lat), float(lon)
            # 尝试获取全局适配器
            from nexus.vehicle.factory import build_vehicle_adapter
            adapter = build_vehicle_adapter()
            if adapter and hasattr(adapter, "navigation"):
                lat = adapter.navigation.get("latitude")
                lon = adapter.navigation.get("longitude")
                if lat is not None and lon is not None:
                    return float(lat), float(lon)
        except Exception as e:
            logger.warning(f"Failed to get GPS coords: {e}")
        return None, None


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
