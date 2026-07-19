# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Heuristic Intent Router — 基于规则的关键词意图路由
作为 LLM 路由的快速兜底层
"""

from __future__ import annotations

import re
from typing import Any, Dict


class HeuristicRouter:
    """关键词规则路由器"""

    def route(self, text: str) -> Dict[str, Any]:
        """返回意图字典，未匹配返回空字典"""
        text = text or ""
        compact = text.replace(" ", "")

        for extractor in [
            self._extract_climate,
            self._extract_window,
            self._extract_seat,
            self._extract_navigation,
            self._extract_media,
            self._extract_vehicle_status,
            self._extract_time,  # v2.2.4: 时间查询优先于搜索，避免"几点"触发 web_search
            self._extract_nearby_poi,  # v2.2.3: 周边搜索优先于普通搜索
            self._extract_food,  # v2.2.1: 点餐优先于搜索，避免"想吃外卖+附近"被搜索拦截
            self._extract_search,
        ]:
            result = extractor(compact)
            if result:
                return result

        return {}

    def _extract_climate(self, text: str) -> Dict[str, Any]:
        if not any(k in text for k in ("空调", "车内温度", "风量", "冷一点", "热一点", "制冷", "制热", "除雾")):
            return {}
        if "温度" in text and not any(k in text for k in ("空调", "车内", "车里", "调高", "调低", "设置", "设为")):
            return {}

        target_temp = None
        temp_match = re.search(r"(\d{1,2})\s*度", text)
        if temp_match:
            target_temp = int(temp_match.group(1))

        op = "status"
        if any(k in text for k in ("打开", "开启", "开开", "制冷", "制热")):
            op = "power_on"
        elif any(k in text for k in ("关闭", "关掉", "关上", "关了")):
            op = "power_off"
        elif any(k in text for k in ("调高", "升高", "加一", "暖一点", "热一点", "提高")):
            op = "temp_up"
        elif any(k in text for k in ("调低", "降低", "小一点", "冷一点")):
            op = "temp_down"
        elif target_temp is not None:
            op = "set_temp"

        fan_speed = None
        fan_match = re.search(r"风量(\d+)", text)
        if fan_match:
            fan_speed = int(fan_match.group(1))

        return {
            "Climate_Action": {
                "op": op,
                "target_temp": target_temp,
                "delta": 1 if op == "temp_up" else -1 if op == "temp_down" else None,
                "fan_speed": fan_speed,
                "mode": "auto" if "自动" in text else None,
            }
        }

    def _extract_window(self, text: str) -> Dict[str, Any]:
        if not any(k in text for k in ("车窗", "窗", "天窗")):
            return {}

        if any(k in text for k in ("打开", "升起", "上升", "开窗")):
            op, percent = "open", 100
        elif any(k in text for k in ("关闭", "关上", "落下", "升窗")):
            op, percent = "close", 0
        else:
            op, percent = "status", None

        position = "sunroof" if "天窗" in text else "all"
        return {"Window_Action": {"op": op, "position": position, "percent": percent}}

    def _extract_seat(self, text: str) -> Dict[str, Any]:
        if not any(k in text for k in ("座椅", "按摩", "加热", "通风", "靠背")):
            return {}

        if any(k in text for k in ("加热", "暖座")):
            op = "heat_on"
        elif any(k in text for k in ("通风", "降温")):
            op = "cool_on"
        elif "按摩" in text:
            op = "massage_on"
        elif any(k in text for k in ("前移", "往前")):
            op = "forward"
        elif any(k in text for k in ("后移", "往后")):
            op = "backward"
        else:
            op = "status"

        position = "passenger" if "副驾" in text else "driver"
        return {"Seat_Action": {"op": op, "position": position, "level": 1, "direction": op if op in ("forward", "backward") else None}}

    def _extract_navigation(self, text: str) -> Dict[str, Any]:
        # 位置查询优先 — 覆盖多种自然语言表达方式
        location_keywords = (
            # 基础位置查询
            "我在哪", "当前位置", "我在什么位置", "现在在哪", "我的位置",
            "我们在哪", "这是哪", "我在哪儿", "我们在哪儿", "这是哪里",
            # 带"当前"前缀
            "当前在什么位置", "当前在哪", "当前位于", "当前位置在哪",
            # 带"我现在"前缀
            "我现在在", "我现在在哪", "我现在什么位置", "我现在在哪儿",
            # 带"目前"/"现在"前缀
            "目前在哪", "目前位置", "现在位置", "目前位于",
            # 带"我们"变体
            "我们在什么位置", "我们在哪了", "我们在哪个位置",
            # 带"哪个"变体
            "我在哪个位置", "现在在哪个位置", "目前在哪个位置",
            # 定位相关
            "定位", "查看定位", "我的定位", "GPS位置", "GPS定位",
            # 其他常见表达
            "这是什么地方", "这里是哪", "当前位置信息",
        )
        if any(k in text for k in location_keywords):
            return {"Navigation_Action": {"op": "location", "destination": "", "waypoint": "", "mode": "drive"}}

        if not any(k in text for k in ("导航", "带我", "前往", "回家", "充电站", "去公司", "去学校", "去机场", "开到", "开去", "去往")):
            if not re.search(r"去[^，。！？?]{1,12}(家|公司|学校|机场|医院|商场|车站|充电站)", text):
                return {}

        destination = ""
        for keyword in ("回家", "去公司", "去学校", "充电站"):
            if keyword in text:
                destination = keyword.replace("去", "")
                break

        if not destination:
            match = re.search(r"(导航到|前往|去往|带我去|开到|开去|去|到)([^，。！？?]+)", text)
            if match:
                destination = match.group(2)

        return {"Navigation_Action": {"destination": destination or "目的地", "waypoint": "", "mode": "drive"}}

    def _extract_media(self, text: str) -> Dict[str, Any]:
        if not any(k in text for k in ("音乐", "播放", "暂停", "下一首", "上一首", "音量", "切歌", "听歌")):
            return {}

        if any(k in text for k in ("暂停", "停止")):
            op = "pause"
        elif any(k in text for k in ("下一首", "下一曲")):
            op = "next"
        elif any(k in text for k in ("上一首", "上一曲")):
            op = "prev"
        else:
            op = "play"

        volume = None
        vol_match = re.search(r"音量(\d{1,2})", text)
        if vol_match:
            volume = int(vol_match.group(1))

        return {"Media_Action": {"op": op, "source": "local", "track": "", "volume": volume}}

    def _extract_vehicle_status(self, text: str) -> Dict[str, Any]:
        # 位置查询
        if any(k in text for k in ("我在哪", "当前位置", "我在什么位置", "现在在哪", "我的位置", "我们在哪", "这是哪")):
            return {"Vehicle_Status_Action": {"op": "location"}}

        if not any(k in text for k in ("车况", "胎压", "续航", "油量", "电量", "保养", "车辆状态")):
            return {}
        return {"Vehicle_Status_Action": {"op": "status"}}

    def _extract_time(self, text: str) -> Dict[str, Any]:
        """v2.2.4: 检测时间查询意图。

        当用户询问当前时间、日期、星期时，直接走闲聊分支。
        系统提示词中已注入当前时间，LLM 可以直接回答，
        无需调用 LLM 路由（节省 3-14 秒）也无需联网搜索。
        """
        # 纯时间查询关键词（不包含"营业"等需搜索的词）
        time_keywords = (
            "几点了", "现在几点", "现在是几点", "什么时间",
            "现在时间", "现在什么时间", "今天几号", "今天日期",
            "星期几", "今天星期", "现在日期", "今天是几号",
            "几月几号", "今天是几月", "现在是什么时间",
        )
        if any(k in text for k in time_keywords):
            # 返回一个不匹配任何技能的意图，_determine_experts 会走 chat 兜底
            return {"Time_Query": True}
        return {}

    def _extract_nearby_poi(self, text: str) -> Dict[str, Any]:
        """v2.2.3: 检测周边 POI 搜索意图（附近美食、周边加油站等）。

        当用户询问基于当前位置的周边信息时，路由到高德 POI 搜索技能，
        而非 Tavily 通用搜索（后者返回的结果不准确）。
        """
        # 周边关键词
        nearby_keywords = ("附近", "周边", "周围", "就近", "旁边", "边上")
        if not any(k in text for k in nearby_keywords):
            return {}

        # POI 类型关键词映射
        poi_patterns = [
            # 餐饮类
            (("好吃的", "美食", "餐厅", "吃饭", "吃饭的地方", "外卖店", "餐馆", "小吃", "火锅", "烧烤", "面馆", "快餐"), "餐厅", "restaurant"),
            # 加油站
            (("加油站", "加油", "加气站"), "加油站", "gas_station"),
            # 停车场
            (("停车场", "停车", "停车位", "停车区"), "停车场", "parking"),
            # 景点
            (("景点", "景区", "公园", "游玩", "旅游", "名胜", "遗迹"), "景点", "attraction"),
            # 超市
            (("超市", "便利店", "商场", "购物", "商店", "mall"), "超市", "supermarket"),
            # 酒店
            (("酒店", "宾馆", "住宿", "旅馆", "民宿"), "酒店", "hotel"),
            # 医院
            (("医院", "诊所", "药店", "药房", "急诊", "卫生服务中心"), "医院", "hospital"),
            # 银行
            (("银行", "atm", "取款", "存款"), "银行", "bank"),
            # 洗车
            (("洗车", "汽车美容", "汽车保养"), "洗车", ""),
        ]

        for keywords, display_name, poi_type in poi_patterns:
            if any(k in text for k in keywords):
                return {
                    "Poi_Search_Action": {
                        "keyword": display_name,
                        "poi_type": poi_type,
                        "radius": 3000,
                    }
                }

        # 有"附近"但没有明确类型 — 使用通用搜索
        # 检查是否有其他意图关键词，避免误拦截
        if any(k in text for k in ("附近", "周边")):
            # 提取"附近"后面的关键词作为搜索词
            match = re.search(r"(?:附近|周边|周围)(?:有|的)?(.+?)(?:[，。！？?]|$)", text)
            if match:
                kw = match.group(1).strip()
                if kw and len(kw) <= 10:
                    return {
                        "Poi_Search_Action": {
                            "keyword": kw,
                            "poi_type": "",
                            "radius": 3000,
                        }
                    }

        return {}

    def _extract_search(self, text: str) -> Dict[str, Any]:
        """检测联网搜索意图"""
        # v2.2.3: 如果包含周边搜索关键词，不拦截为通用搜索（已由 _extract_nearby_poi 处理）
        nearby_keywords = ("附近", "周边", "周围", "就近")
        nearby_poi_keywords = (
            "好吃的", "美食", "餐厅", "吃饭", "加油站", "停车场",
            "景点", "超市", "酒店", "医院", "银行", "洗车",
        )
        if any(k in text for k in nearby_keywords) and any(k in text for k in nearby_poi_keywords):
            return {}

        # v2.2.1: 如果包含点餐关键词，不拦截为搜索
        food_keywords = ("点外卖", "饿了", "想吃", "点餐", "叫外卖", "吃什么", "帮我点")
        if any(k in text for k in food_keywords):
            return {}

        # 搜索关键词
        search_keywords = (
            "搜索", "查一下", "查询", "查查", "帮我查", "请问",
            "附近", "周边", "附近有", "哪里有", "在哪",
            "天气", "新闻", "百科", "什么是", "是怎么回事",
            "怎么样", "好不好", "评分", "评价", "几点", "营业",
            "多少钱", "价格", "最新",
        )
        if not any(k in text for k in search_keywords):
            return {}

        # 如果是导航意图（包含“导航”“去”等），不拦截
        if any(k in text for k in ("导航", "带我", "前往", "开到", "去往")):
            return {}

        # 提取搜索 query：原文本即作为搜索关键词
        return {"Need_Search": text}

    def _extract_food(self, text: str) -> Dict[str, Any]:
        """检测点餐意图"""
        food_keywords = ("点外卖", "饿了", "想吃", "点餐", "叫外卖", "吃什么", "帮我点")
        if not any(k in text for k in food_keywords):
            return {}
        # 提取食物名称
        match = re.search(r"(?:想吃|点|叫|来)([^，。！？?]+)", text)
        food = match.group(1) if match else "随便"
        return {"Call_elm": True, "Food_candidate": food}
