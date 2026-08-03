# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Non-vehicle skills: web search, weather query, food delivery, voice registration
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from nexus.core.logger import get_logger
from nexus.skills.base import BaseSkill, SkillResult

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

            # 从 kwargs 中获取位置上下文（由 LifestyleExpert 从 state["key_context"] 注入）
            # 场景: 用户说"我在杭州"后问"明天天气怎么样"，搜索需带上"杭州"
            location = kwargs.get("location", "")
            # 如果没有显式传入位置，尝试从 key_context 中提取
            if not location:
                key_context = kwargs.get("key_context", {})
                if isinstance(key_context, dict):
                    location = key_context.get("location", "")

            # 构建增强查询：原始查询 + 位置 + 日期时间
            # 位置注入条件：查询包含天气/温度等位置敏感词，且用户未在查询中显式指定地点
            location_keywords = ("天气", "温度", "附近", "周边", "美食", "餐厅", "新闻")
            needs_location = any(kw in query for kw in location_keywords)
            has_location_in_query = any(
                loc in query for loc in ["北京", "上海", "广州", "深圳", "杭州", "南京",
                                          "成都", "武汉", "西安", "重庆", "天津", "苏州",
                                          "长沙", "郑州", "青岛", "大连", "宁波", "厦门"]
            )
            if location and needs_location and not has_location_in_query:
                enhanced_query = f"{query} {location} {today_str} {time_str}"
            else:
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


class WeatherSkill(BaseSkill):
    """和风天气查询技能

    使用和风天气 (QWeather) API 获取精准天气数据，替代 Tavily 通用搜索。

    功能:
        - 识别天气查询日期意图（今天/明天/后天）
        - 从查询中提取城市名称，或从 GPS 坐标获取位置
        - 调用和风天气 API 获取实况天气或天气预报
        - 返回结构化天气信息供 LLM 合成自然语言回复

    认证方式: API KEY (X-QW-Api-Key 请求头)
    API 文档: https://dev.qweather.com/docs/api/weather/
    """

    name = "weather_query"
    timeout_ms = 8000
    description = (
        "当用户询问天气情况、温度、下雨、下雪等天气相关信息时调用此技能。"
        "支持查询今天、明天、后天等不同日期的天气。"
    )
    required_parameters = ["query"]
    optional_parameters = ["cockpit_id"]
    examples = [
        {"input": "今天天气怎么样", "arguments": {"query": "今天天气怎么样"}},
        {"input": "明天北京天气", "arguments": {"query": "明天北京天气"}},
        {"input": "后天会下雨吗", "arguments": {"query": "后天会下雨吗"}},
    ]
    parameters = {
        "query": {
            "type": "string",
            "description": "用户的天气查询原文",
        },
        "cockpit_id": {
            "type": "string",
            "description": "座舱 ID（用于获取 GPS 坐标）",
        },
    }

    def __init__(self):
        from nexus.config import get_config
        config = get_config().qweather
        self._api_key = config.effective_key
        self._api_host = config.api_host or "devapi.qweather.com"
        # 新版和风天气 API 统一使用同一个 host，GeoAPI 路径为 /geo/v2/city/lookup
        # 旧版使用独立的 geoapi.qweather.com，路径为 /v2/city/lookup
        # 这里保留两个 host 用于回退尝试
        self._geo_hosts = [
            (self._api_host, "/geo/v2/city/lookup"),   # 新版: 统一 host + /geo 前缀
            ("geoapi.qweather.com", "/v2/city/lookup"),  # 旧版: 独立 host
        ]

    async def execute(self, query: str = "", cockpit_id: str = "", **kwargs: Any) -> SkillResult:
        """执行天气查询：作用：解析日期+城市→调用和风API→格式化返回；场景：用户询问天气。"""
        logger.info(f"WeatherSkill executing: query={query}")

        if not self._api_key:
            logger.warning("QWeather API key not configured, falling back to web_search")
            return SkillResult(
                status="error",
                message="天气服务未配置，请设置 QWEATHER_APIKEY。",
                action="weather_query",
                handled=True,
            )

        try:
            import httpx

            # 1. 解析日期意图
            date_intent = self._parse_date_intent(query)

            # 2. 提取城市名
            city_name = self._extract_city(query)

            # 2b. 如果 query 中没有城市名，尝试从 key_context 中获取
            # 场景: 用户说"我在杭州"后问"明天天气怎么样"
            if not city_name:
                key_context = kwargs.get("key_context", {})
                if isinstance(key_context, dict):
                    ctx_loc = key_context.get("location", "")
                    if ctx_loc:
                        city_name = self._extract_city_from_context(ctx_loc)
                        if city_name:
                            logger.info(f"WeatherSkill: city '{city_name}' extracted from key_context: '{ctx_loc}'")

            # 3. 获取位置参数（LocationID 或经纬度）
            location_id = ""
            lat, lon = None, None
            city_resolved = False  # 标记是否已成功获取到有效位置

            if city_name:
                # 通过 GeoAPI 查询城市
                location_id, lat, lon = await self._geo_lookup(httpx.AsyncClient, city_name)
                if location_id or (lat is not None and lon is not None):
                    city_resolved = True
                else:
                    # GeoAPI 失败 — 回退到 GPS 坐标
                    logger.warning(
                        f"QWeather GeoAPI failed for city '{city_name}', "
                        f"falling back to GPS coordinates"
                    )

            # 如果城市名未提取到或 GeoAPI 失败，尝试 GPS 坐标
            if not city_resolved:
                gps_lat, gps_lon = self._get_gps_coords(cockpit_id)
                if gps_lat is not None and gps_lon is not None:
                    lat, lon = gps_lat, gps_lon
                    city_resolved = True
                    logger.info(f"WeatherSkill: using GPS coordinates ({lat}, {lon}) for weather query")
                elif not city_name:
                    return SkillResult(
                        status="ok",
                        message="请告诉我您想查询哪个城市的天气，或确保定位已开启。",
                        action="weather_query",
                        handled=True,
                    )
                else:
                    # 有城市名但 GeoAPI 失败且 GPS 也不可用
                    return SkillResult(
                        status="ok",
                        message=f"未能获取「{city_name}」的天气信息，请稍后重试或确认城市名称。",
                        action="weather_query",
                        handled=True,
                    )

            # 构建位置参数：优先使用 LocationID，其次使用经纬度
            location_param = location_id if location_id else f"{lon:.2f},{lat:.2f}"

            # 4. 调用天气 API（API Key 同时通过 query 参数和 header 传递，兼容新旧版）
            headers = {"X-QW-Api-Key": self._api_key}
            query_params = {"key": self._api_key}

            async with httpx.AsyncClient() as client:
                if date_intent == "now":
                    # 查询实况天气
                    weather_data = await self._fetch_weather_now(client, headers, query_params, location_param)
                else:
                    # 查询天气预报（7天）
                    weather_data = await self._fetch_weather_forecast(
                        client, headers, query_params, location_param, date_intent
                    )

            if not weather_data:
                return SkillResult(
                    status="ok",
                    message="暂时无法获取天气信息，请稍后重试。",
                    action="weather_query",
                    handled=True,
                )

            # 5. 格式化天气信息
            result_text = self._format_weather(weather_data, date_intent, city_name)
            logger.info(f"WeatherSkill done: {date_intent}, city={city_name or 'GPS'}")

            return SkillResult(
                status="ok",
                message=result_text,
                search_context=result_text,
                action="weather_query",
                handled=True,
                metadata={
                    "date_intent": date_intent,
                    "city": city_name,
                    "location": location_param,
                },
            )

        except Exception as e:
            logger.error(f"WeatherSkill failed: {e}")
            return SkillResult(
                status="error",
                message=f"天气查询失败: {e}",
                action="weather_query",
                handled=True,
            )

    def _parse_date_intent(self, query: str) -> str:
        """解析日期意图。

        返回值:
            "now" — 今天/当前天气
            "tomorrow" — 明天
            "day_after" — 后天
            "three_days" — 未来三天
        """
        if "三天" in query or "未来三天" in query or "未来3天" in query or "3天" in query:
            return "three_days"
        if "后天" in query or "大后天" in query:
            return "day_after"
        if "明天" in query or "明日" in query:
            return "tomorrow"
        # 默认查询今天的天气（含"今天"、"现在"、"天气怎么样"等）
        return "now"

    def _extract_city(self, query: str) -> str:
        """从查询中提取城市名称。

        通过正则匹配常见城市名和"XX天气"模式。
        """
        import re

        # 日期/时间相关词，不应被误识别为城市名
        date_words = {
            "今天", "明天", "后天", "大后天", "今日", "明日", "昨日", "昨天",
            "这周", "下周", "上周", "现在", "当前", "这几天",
        }

        # 常见城市列表
        cities = [
            "北京", "上海", "广州", "深圳", "杭州", "南京", "成都", "武汉",
            "西安", "重庆", "天津", "苏州", "长沙", "郑州", "青岛", "大连",
            "宁波", "厦门", "福州", "合肥", "济南", "沈阳", "长春", "哈尔滨",
            "昆明", "贵阳", "南昌", "太原", "兰州", "乌鲁木齐", "拉萨",
            "银川", "西宁", "呼和浩特", "海口", "三亚", "桂林", "丽江",
        ]

        for city in cities:
            if city in query:
                return city

        # 尝试匹配"XX天气"模式（XX 为 2-4 个中文字符）
        match = re.search(r"([\u4e00-\u9fa5]{2,4})天气", query)
        if match:
            candidate = match.group(1)
            # 过滤日期词（如"明天的天气"中的"明天的"不应被识别为城市）
            # 去除尾部的"的"字后检查
            candidate_clean = candidate.rstrip("的")
            if candidate_clean and candidate_clean not in date_words and len(candidate_clean) >= 2:
                return candidate_clean

        # 尝试匹配"XX市"模式
        match = re.search(r"([\u4e00-\u9fa5]{2,4})市", query)
        if match:
            candidate = match.group(1)
            if candidate not in date_words:
                return candidate

        return ""

    def _extract_city_from_context(self, ctx_location: str) -> str:
        """从 key_context 的 location 字段中提取城市名。

        key_context 中的位置可能是:
            - "杭州" （直接城市名）
            - "浙江省 杭州市" （IP 定位格式）
            - "浙江省杭州市余杭区XXX街道" （逆地理编码格式）

        提取策略: 优先匹配已知城市列表，其次匹配"XX市"模式，
        最后回退到第一个 2-4 字中文片段。
        """
        if not ctx_location:
            return ""

        # 非城市名停用词 — 从 key_context 中误提取的位置（如"处于什么位置"）
        _city_stopwords = {
            "什么", "哪里", "哪个", "哪儿", "啥", "位置", "地方",
            "处于什么", "处于什么位置", "处于哪", "处于哪里",
            "什么位置", "什么地方", "现在", "目前", "当前",
            "今天", "明天", "昨天",
        }

        # 优先匹配已知城市列表
        cities = [
            "北京", "上海", "广州", "深圳", "杭州", "南京", "成都", "武汉",
            "西安", "重庆", "天津", "苏州", "长沙", "郑州", "青岛", "大连",
            "宁波", "厦门", "福州", "合肥", "济南", "沈阳", "长春", "哈尔滨",
            "昆明", "贵阳", "南昌", "太原", "兰州", "乌鲁木齐", "拉萨",
            "银川", "西宁", "呼和浩特", "海口", "三亚", "桂林", "丽江",
        ]
        for city in cities:
            if city in ctx_location:
                return city

        # 匹配"XX市"模式
        import re
        match = re.search(r"([\u4e00-\u9fa5]{2,4})市", ctx_location)
        if match:
            candidate = match.group(1)
            if candidate not in _city_stopwords:
                return candidate

        # 回退: 取第一个 2-4 字中文片段
        match = re.search(r"([\u4e00-\u9fa5]{2,4})", ctx_location)
        if match:
            candidate = match.group(1)
            # 停用词过滤 — 防止"处于什么"等非城市名被误识别
            if candidate not in _city_stopwords:
                return candidate

        return ""

    async def _geo_lookup(self, client_cls, city_name: str) -> tuple[str, float | None, float | None]:
        """通过和风 GeoAPI 查询城市 LocationID 和坐标。

        兼容新旧版 API:
            - 新版: https://{api_host}/geo/v2/city/lookup (统一 host + /geo 前缀)
            - 旧版: https://geoapi.qweather.com/v2/city/lookup (独立 host)
        API Key 同时通过 query 参数 key 和 header X-QW-Api-Key 传递。

        Returns:
            (location_id, lat, lon) — 如果查询失败返回 ("", None, None)
        """
        params = {"location": city_name, "lang": "zh", "key": self._api_key}
        headers = {"X-QW-Api-Key": self._api_key}

        for host, path in self._geo_hosts:
            try:
                url = f"https://{host}{path}"
                logger.info(f"QWeather GeoAPI trying: {url}")

                async with client_cls() as client:
                    resp = await client.get(url, params=params, headers=headers, timeout=5.0)

                if resp.status_code == 404:
                    logger.info(f"QWeather GeoAPI 404 on {host}{path}, trying next host")
                    continue

                if resp.status_code != 200:
                    logger.warning(f"QWeather GeoAPI HTTP error: {resp.status_code} on {host}{path}")
                    continue

                data = resp.json()
                if data.get("code") != "200":
                    logger.warning(f"QWeather GeoAPI error: code={data.get('code')} on {host}{path}")
                    continue

                locations = data.get("location", [])
                if not locations:
                    return "", None, None

                loc = locations[0]
                location_id = loc.get("id", "")
                lat = float(loc.get("lat", 0)) if loc.get("lat") else None
                lon = float(loc.get("lon", 0)) if loc.get("lon") else None
                logger.info(f"QWeather GeoAPI: city={city_name}, id={location_id}, lat={lat}, lon={lon} (via {host})")
                return location_id, lat, lon

            except Exception as e:
                logger.warning(f"QWeather GeoAPI failed on {host}{path}: {e}")
                continue

        logger.warning(f"QWeather GeoAPI exhausted all hosts for city '{city_name}'")
        return "", None, None

    async def _fetch_weather_now(
        self, client, headers: dict, query_params: dict, location: str
    ) -> dict[str, Any]:
        """获取实况天气。"""
        url = f"https://{self._api_host}/v7/weather/now"
        params = {"location": location, "lang": "zh", "unit": "m", **query_params}

        resp = await client.get(url, params=params, headers=headers, timeout=8.0)
        if resp.status_code != 200:
            logger.error(f"QWeather now HTTP error: {resp.status_code}")
            return {}

        data = resp.json()
        if data.get("code") != "200":
            logger.error(f"QWeather now API error: code={data.get('code')}")
            return {}

        return {"type": "now", "now": data.get("now", {})}

    async def _fetch_weather_forecast(
        self, client, headers: dict, query_params: dict, location: str, date_intent: str
    ) -> dict[str, Any]:
        """获取天气预报（7天）。"""
        url = f"https://{self._api_host}/v7/weather/7d"
        params = {"location": location, "lang": "zh", "unit": "m", **query_params}

        resp = await client.get(url, params=params, headers=headers, timeout=8.0)
        if resp.status_code != 200:
            logger.error(f"QWeather 7d HTTP error: {resp.status_code}")
            return {}

        data = resp.json()
        if data.get("code") != "200":
            logger.error(f"QWeather 7d API error: code={data.get('code')}")
            return {}

        daily_list = data.get("daily", [])

        # 根据日期意图选择对应天的预报
        index = 0 if date_intent == "now" else 1 if date_intent == "tomorrow" else 2
        # 支持"未来三天"等场景: 返回前3天的预报
        if "三天" in (date_intent or "") or "future" in (date_intent or ""):
            if len(daily_list) >= 3:
                return {"type": "forecast", "daily": daily_list[:3], "all_daily": daily_list}
        if index < len(daily_list):
            return {"type": "forecast", "daily": daily_list[index], "all_daily": daily_list}

        return {}

    def _format_weather(
        self, weather_data: dict[str, Any], date_intent: str, city_name: str
    ) -> str:
        """将天气 API 返回数据格式化为结构化文本。"""
        now = _now_cn()
        date_str = now.strftime("%Y年%m月%d日")
        time_str = now.strftime("%H:%M")

        # 日期描述
        if date_intent == "tomorrow":
            tomorrow = now + timedelta(days=1)
            date_desc = f"明天（{tomorrow.strftime('%m月%d日')}）"
        elif date_intent == "day_after":
            day_after = now + timedelta(days=2)
            date_desc = f"后天（{day_after.strftime('%m月%d日')}）"
        else:
            date_desc = f"今天（{now.strftime('%m月%d日')}）"

        location_desc = city_name if city_name else "当前位置"

        if weather_data.get("type") == "now":
            now_data = weather_data.get("now", {})
            temp = now_data.get("temp", "未知")
            text = now_data.get("text", "未知")
            wind_dir = now_data.get("windDir", "")
            wind_scale = now_data.get("windScale", "")
            humidity = now_data.get("humidity", "")
            feels_like = now_data.get("feelsLike", "")

            parts = [
                f"[当前时间: {date_str} {time_str}]",
                f"{location_desc}{date_desc}天气：{text}，",
                f"气温{temp}°C",
            ]
            if feels_like:
                parts.append(f"，体感{feels_like}°C")
            if humidity:
                parts.append(f"，湿度{humidity}%")
            if wind_dir and wind_scale:
                parts.append(f"，{wind_dir}风{wind_scale}级")
            parts.append("。")

            return "".join(parts)

        elif weather_data.get("type") == "forecast":
            daily = weather_data.get("daily", {})
            # 支持"未来三天"场景: daily 为列表
            if isinstance(daily, list):
                if not daily:
                    return f"{location_desc}未来天气预报暂无数据。"
                parts = [f"[当前时间: {date_str} {time_str}]"]
                for i, d in enumerate(daily):
                    date_label = ["今天", "明天", "后天"][i] if i < 3 else f"第{i+1}天"
                    d_max = d.get("tempMax", "未知")
                    d_min = d.get("tempMin", "未知")
                    d_text = d.get("textDay", "未知")
                    d_night = d.get("textNight", "")
                    parts.append(f"\n{date_label}：{d_text}")
                    if d_night and d_night != d_text:
                        parts.append(f"，夜间{d_night}")
                    parts.append(f"，{d_min}~{d_max}°C。")
                return "".join(parts)

            if not daily:
                return f"{location_desc}{date_desc}的天气预报暂无数据。"

            temp_max = daily.get("tempMax", "未知")
            temp_min = daily.get("tempMin", "未知")
            text_day = daily.get("textDay", "未知")
            text_night = daily.get("textNight", "")
            wind_dir_day = daily.get("windDirDay", "")
            wind_scale_day = daily.get("windScaleDay", "")
            humidity = daily.get("humidity", "")
            uv_index = daily.get("uvIndex", "")
            precip = daily.get("precip", "")

            parts = [
                f"[当前时间: {date_str} {time_str}]",
                f"{location_desc}{date_desc}天气：白天{text_day}",
            ]
            if text_night and text_night != text_day:
                parts.append(f"，夜间{text_night}")
            parts.append(f"，{temp_min}~{temp_max}°C")
            if humidity:
                parts.append(f"，湿度{humidity}%")
            if wind_dir_day and wind_scale_day:
                parts.append(f"，{wind_dir_day}风{wind_scale_day}级")
            if uv_index:
                parts.append(f"，紫外线指数{uv_index}")
            if precip and precip != "0.0":
                parts.append(f"，降水量{precip}mm")
            parts.append("。")

            return "".join(parts)

        return f"{location_desc}天气信息获取失败。"

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

    超时配置:
        - 通过 BaseSkill.timeout_ms (默认 5000ms) 统一管理
        - SkillRegistry.execute() 会基于此值设置 asyncio.wait_for 超时
        - 不再硬编码 timeout=5.0
    """

    name = "amap_poi_search"
    # 统一超时配置：5 秒（与原硬编码 timeout=5.0 对齐）
    timeout_ms = 5000
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

            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://restapi.amap.com/v3/place/around",
                    params=params,
                    timeout=self.timeout_ms / 1000.0,
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
