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
        if any(k in text for k in ("调高", "升高", "加一", "暖一点", "热一点", "提高")):
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
        if not any(k in text for k in ("车况", "胎压", "续航", "油量", "电量", "保养", "车辆状态")):
            return {}
        return {"Vehicle_Status_Action": {"op": "status"}}
