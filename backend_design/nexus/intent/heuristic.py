# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Heuristic Intent Router — 基于规则的关键词意图路由
作为 LLM 路由的快速兜底层

修复记录:
    - 新增 _split_segments 文本分段方法，将复合指令按标点拆解为独立子句，
      各 extractor 仅在包含领域关键词的子句内解析操作动词，
      彻底解决"打开音乐，关闭车窗"中"打开"被车窗提取器误匹配为 open 的问题。
    - _extract_window / _extract_seat / _extract_media / _extract_climate
      全部改为分段解析模式，确保跨域关键词不产生干扰。
"""

from __future__ import annotations

import re
from typing import Any

from nexus.core.logger import get_logger

_logger = get_logger(__name__)


class HeuristicRouter:
    """关键词规则路由器"""

    # 子句分隔标点 — 用于将复合指令拆解为独立子句
    _SEGMENT_SPLIT_RE = re.compile(r"[，。！？；;,\n]")

    def _split_segments(self, text: str) -> list[str]:
        """将复合指令按标点拆解为独立子句列表。

        示例:
            "打开音乐，关闭全部车窗，打开座椅按摩"
            → ["打开音乐", "关闭全部车窗", "打开座椅按摩"]

        每个子句是一个独立的需求单元，后续 extractor 仅在
        包含自身领域关键词的子句内解析操作动词，避免跨域误匹配。
        """
        parts = self._SEGMENT_SPLIT_RE.split(text)
        return [p.strip() for p in parts if p.strip()]

    def route(self, text: str) -> dict[str, Any]:
        """返回意图字典，未匹配返回空字典。

        多需求并行支持：遍历所有 extractor，收集全部匹配的意图后合并返回。
        这样复合指令（如"打开车窗+查天气+播放音乐"）能同时触发多个专家并行执行。

        对话历史查询检测优先于车控指令:
            当用户输入同时包含对话历史查询（如"我问了什么"）和车控指令（如"打开天窗"）时，
            必须同时识别两种意图，确保车控指令走 vehicle 专家执行，
            对话历史查询走 chat 专家 + 记忆召回回答，两者并行不遗漏。
        """
        text = text or ""
        compact = text.replace(" ", "")

        merged: dict[str, Any] = {}
        matched_extractors: list[str] = []

        for extractor in [
            self._extract_conversation_history,  # 对话历史查询优先检测，支持与车控并行
            self._extract_climate,
            self._extract_window,
            self._extract_seat,
            self._extract_navigation,
            self._extract_media,
            self._extract_vehicle_status,
            self._extract_time,  # 时间查询优先于搜索，避免"几点"触发 web_search
            self._extract_nearby_poi,  # 周边搜索优先于普通搜索
            self._extract_weather,  # 天气查询优先于普通搜索，路由到和风天气 API
            self._extract_food,  # 点餐优先于搜索，避免"想吃外卖+附近"被搜索拦截
            self._extract_search,
        ]:
            result = extractor(compact)
            if result:
                merged.update(result)
                matched_extractors.append(extractor.__name__)

        # 多意图日志打点 — 打印拆解后的原子需求清单，直观验证并行能力是否生效
        if len(matched_extractors) > 1:
            _logger.info(
                f"Multi-intent detected: extractors={matched_extractors}, "
                f"intents={list(merged.keys())}, text='{text[:80]}'"
            )

        return merged

    # 中文数字 → 阿拉伯数字映射（用于风量/音量等参数解析）
    _CN_NUM_MAP = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

    # 对话历史查询关键词模式 — 用户询问之前对话内容时命中
    # 这些模式覆盖了"我问了什么""你是怎么回答的""之前聊了啥"等自然表达
    _HISTORY_QUERY_KEYWORDS = (
        # 询问用户自己问了什么
        "我问了", "我问了什么", "我问了哪些", "我问了你",
        "我问了什么问题", "我之前问了", "我刚才问了",
        "我的问题", "我说了什么", "我说了哪些",
        # 询问助手如何回答
        "你是如何回答", "你是怎么回答", "你怎么回答",
        "你是怎么说的", "你是如何说的",
        # 询问对话历史/记录
        "对话历史", "聊天记录", "聊天历史", "对话记录",
        "我们聊了什么", "我们聊了哪些", "我们聊了啥",
        "之前聊了什么", "刚才聊了什么", "之前说了什么",
        # 询问记忆
        "还记得我", "你还记得", "你还记得吗",
        # 询问第一句话/最后一个问题等
        "第一个问题", "第一句话", "第一次问",
        "上一个问题", "刚才问", "之前问",
        "上次问", "刚才聊", "之前聊",
    )

    def _extract_conversation_history(self, text: str) -> dict[str, Any]:
        """检测对话历史查询意图。

        当用户询问之前对话的内容（如"我问了什么""你是如何回答的"）时，
        返回 History_Query_Action 意图，路由到 chat 专家处理。

        关键场景: 复合指令"我问了你哪些问题，你是如何回答的，同时打开音乐和天窗"
        - 对话历史查询部分（"我问了你哪些问题，你是如何回答的"）→ History_Query_Action
        - 车控指令部分（"打开音乐""天窗"）→ Media_Action + Window_Action
        两种意图并行检测，分别路由到 chat 和 vehicle 专家，
        确保"执行车控 + 回答历史查询"同时完成。

        注意: 此 extractor 不拦截后续的车控/天气/搜索等 extractor，
        仅在 merged dict 中追加 History_Query_Action 字段，
        与其他意图共存而非互斥。
        """
        for kw in self._HISTORY_QUERY_KEYWORDS:
            if kw in text:
                return {"History_Query_Action": {"query": text}}
        return {}

    def _extract_climate(self, text: str) -> dict[str, Any]:
        """解析空调控制意图。

        分段解析：在包含空调领域关键词的子句内解析操作动词和参数，
        避免复合指令中其他子句的动词（如"打开音乐"中的"打开"）干扰空调操作判断。
        """
        # 领域关键词
        climate_keywords = ("空调", "车内温度", "风量", "风速", "冷一点", "热一点", "制冷", "制热", "除雾", "除霜")
        if not any(k in text for k in climate_keywords):
            return {}
        if "温度" in text and not any(k in text for k in ("空调", "车内", "车里", "调高", "调低", "设置", "设为", "开到", "调到")):
            return {}

        # 分段解析 — 仅在包含空调关键词的子句内查找操作动词
        segments = self._split_segments(text)
        climate_segments = [s for s in segments if any(k in s for k in climate_keywords)]
        # 如果分段后没有找到空调子句（可能整句就是空调指令），用原文
        if not climate_segments:
            climate_segments = [text]

        # 在空调子句中解析温度参数
        target_temp = None
        for seg in climate_segments:
            temp_match = re.search(r"(\d{1,2})\s*度", seg)
            if temp_match:
                target_temp = int(temp_match.group(1))
                break

        # 风量解析 — 支持多种表达:
        #   "风量2" / "2级风量" / "风速2" / "两级风速" / "2档风速"
        #   "风量调到两级" / "风量设为3档" / "把风速调到2级"
        # 注意: 风量解析必须在 op 回退之前完成，因为回退逻辑需要检查 fan_speed 是否已解析到值
        fan_speed = None
        for seg in climate_segments:
            fan_match = (
                re.search(r"风量(\d+)", seg)
                or re.search(r"(\d+)\s*级\s*风[速量]", seg)
                or re.search(r"风[速量](\d+)", seg)
                or re.search(r"(\d+)\s*档\s*风", seg)
                or re.search(r"(\d+)\s*档\s*风速", seg)
                or re.search(r"风[速量].*?(\d+)\s*[级档]", seg)
            )
            if fan_match:
                fan_speed = int(fan_match.group(1))
                break
            # 中文数字: "两级风速" / "两档风量" / "风量调到两级" 等
            cn_match = (
                re.search(r"([一两二三四五六七八十])\s*[级档]\s*风[速量]", seg)
                or re.search(r"风[速量].*?([一两二三四五六七八十])\s*[级档]", seg)
            )
            if cn_match:
                fan_speed = self._CN_NUM_MAP.get(cn_match.group(1))
                break
        # 如果子句中未找到风量，回退到整句匹配
        if fan_speed is None:
            fan_match = (
                re.search(r"风量(\d+)", text)
                or re.search(r"(\d+)\s*级\s*风[速量]", text)
                or re.search(r"风[速量](\d+)", text)
                or re.search(r"(\d+)\s*档\s*风", text)
                or re.search(r"(\d+)\s*档\s*风速", text)
                or re.search(r"风[速量].*?(\d+)\s*[级档]", text)
            )
            if fan_match:
                fan_speed = int(fan_match.group(1))
            else:
                cn_match = (
                    re.search(r"([一两二三四五六七八十])\s*[级档]\s*风[速量]", text)
                    or re.search(r"风[速量].*?([一两二三四五六七八十])\s*[级档]", text)
                )
                if cn_match:
                    fan_speed = self._CN_NUM_MAP.get(cn_match.group(1))

        # 操作动词解析 — 在空调子句内匹配
        # 优先级: 关闭 > 打开 > 调高 > 调低 > 设温度 > 制冷/制热
        # 注意: 必须在空调子句内匹配，不能用整句匹配
        op = "status"
        for seg in climate_segments:
            if any(k in seg for k in ("关闭", "关掉", "关上", "关了")):
                op = "power_off"
                break
            if any(k in seg for k in ("打开", "开启", "开开")):
                op = "power_on"
                break
            if any(k in seg for k in ("调高", "升高", "加一", "暖一点", "热一点", "提高")):
                op = "temp_up"
                break
            if any(k in seg for k in ("调低", "降低", "小一点", "冷一点")):
                op = "temp_down"
                break
        # 如果操作动词未在子句中匹配到，回退到整句匹配
        # 注意: 当 target_temp/fan_speed 已解析到值时，优先设为 set_temp，
        # 避免复合指令中其他子句的"关闭"（如"关闭音乐，关闭车窗"）被误匹配为空调 power_off。
        # 因为分段解析已在空调子句内查找过"关闭"，如果没找到，说明"关闭"不属于空调操作。
        if op == "status":
            if target_temp is not None or fan_speed is not None:
                op = "set_temp"
            elif any(k in text for k in ("关闭", "关掉", "关上", "关了")):
                op = "power_off"
            elif any(k in text for k in ("打开", "开启", "开开")):
                op = "power_on"
            elif any(k in text for k in ("调高", "升高", "加一", "暖一点", "热一点", "提高")):
                op = "temp_up"
            elif any(k in text for k in ("调低", "降低", "小一点", "冷一点")):
                op = "temp_down"
            elif any(k in text for k in ("制冷", "冷风")):
                op = "power_on"
            elif any(k in text for k in ("制热", "暖风", "热风")):
                op = "power_on"

        # 模式解析 — 支持 制冷/制热/除雾/自动
        mode = None
        if "自动" in text:
            mode = "auto"
        elif any(k in text for k in ("制冷", "冷风")):
            mode = "cool"
        elif any(k in text for k in ("制热", "暖风", "热风")):
            mode = "heat"
        elif "除雾" in text or "除霜" in text:
            mode = "defog"

        return {
            "Climate_Action": {
                "op": op,
                "target_temp": target_temp,
                "delta": 1 if op == "temp_up" else -1 if op == "temp_down" else None,
                "fan_speed": fan_speed,
                "mode": mode,
            }
        }

    def _extract_window(self, text: str) -> dict[str, Any]:
        """解析车窗控制意图。

        分段解析：在包含车窗领域关键词的子句内解析操作动词，
        避免"打开音乐，关闭车窗"中"打开"被误匹配为车窗 open 操作。
        """
        if not any(k in text for k in ("车窗", "窗", "天窗")):
            return {}

        # 分段解析 — 仅在包含车窗关键词的子句内查找操作动词
        segments = self._split_segments(text)
        window_segments = [s for s in segments if any(k in s for k in ("车窗", "窗", "天窗"))]
        # 如果分段后没有找到车窗子句（可能整句就是车窗指令），用原文
        if not window_segments:
            window_segments = [text]

        # 操作动词解析 — 仅在车窗子句内匹配
        op = "status"
        percent = None
        for seg in window_segments:
            if any(k in seg for k in ("打开", "升起", "上升", "开窗")):
                op, percent = "open", 100
                break
            if any(k in seg for k in ("关闭", "关上", "落下", "升窗")):
                op, percent = "close", 0
                break
            if any(k in seg for k in ("半开", "开一半", "开一点")):
                op, percent = "set", 50
                break
        # 如果操作动词未在子句中匹配到，回退到整句匹配
        if op == "status":
            if any(k in text for k in ("打开", "升起", "上升", "开窗")):
                op, percent = "open", 100
            elif any(k in text for k in ("关闭", "关上", "落下", "升窗")):
                op, percent = "close", 0
            elif any(k in text for k in ("半开", "开一半", "开一点")):
                op, percent = "set", 50

        # 百分比解析: "开到30%" / "开到30%" 等 — 在车窗子句内匹配
        for seg in window_segments:
            percent_match = re.search(r"(?:开到|调到|设为)(\d{1,3})\s*%", seg)
            if percent_match and op != "status":
                percent = max(0, min(100, int(percent_match.group(1))))
                op = "set"
                break
        # 回退到整句匹配
        if op != "status" and percent in (100, 0, 50):
            percent_match = re.search(r"(?:开到|调到|设为)(\d{1,3})\s*%", text)
            if percent_match:
                percent = max(0, min(100, int(percent_match.group(1))))
                op = "set"

        # 位置解析 — 支持单独车窗控制
        if "天窗" in text:
            position = "sunroof"
        elif any(k in text for k in ("左前", "主驾", "驾驶位", "驾驶员")):
            position = "front_left"
        elif any(k in text for k in ("右前", "副驾", "乘客", "副驾驶")):
            position = "front_right"
        elif any(k in text for k in ("左后", "后排左", "后座左")):
            position = "rear_left"
        elif any(k in text for k in ("右后", "后排右", "后座右")):
            position = "rear_right"
        else:
            position = "all"
        return {"Window_Action": {"op": op, "position": position, "percent": percent}}

    def _extract_seat(self, text: str) -> dict[str, Any]:
        """解析座椅控制意图。

        分段解析：在包含座椅领域关键词的子句内解析操作动词，
        避免"打开音乐，打开座椅按摩"中音乐子句的"打开"干扰座椅操作判断。
        """
        if not any(k in text for k in ("座椅", "按摩", "加热", "通风", "靠背")):
            return {}

        # 分段解析 — 仅在包含座椅关键词的子句内查找操作动词
        segments = self._split_segments(text)
        seat_segments = [s for s in segments if any(k in s for k in ("座椅", "按摩", "加热", "通风", "靠背"))]
        if not seat_segments:
            seat_segments = [text]

        # 操作动词解析 — 仅在座椅子句内匹配
        op = "status"
        for seg in seat_segments:
            if any(k in seg for k in ("加热", "暖座")):
                op = "heat_on"
                break
            if any(k in seg for k in ("通风", "降温")):
                op = "cool_on"
                break
            if any(k in seg for k in ("按摩", "揉捏")):
                op = "massage_on"
                break
            if any(k in seg for k in ("前移", "往前")):
                op = "forward"
                break
            if any(k in seg for k in ("后移", "往后")):
                op = "backward"
                break
        # 回退到整句匹配
        if op == "status":
            if any(k in text for k in ("加热", "暖座")):
                op = "heat_on"
            elif any(k in text for k in ("通风", "降温")):
                op = "cool_on"
            elif any(k in text for k in ("按摩", "揉捏")):
                op = "massage_on"
            elif any(k in text for k in ("前移", "往前")):
                op = "forward"
            elif any(k in text for k in ("后移", "往后")):
                op = "backward"

        # 座椅位置解析 — 支持四座独立控制
        if any(k in text for k in ("副驾", "副驾驶", "乘客")):
            position = "passenger"
        elif any(k in text for k in ("后排左", "左后座", "后排左侧")):
            position = "rear_left"
        elif any(k in text for k in ("后排右", "右后座", "后排右侧")):
            position = "rear_right"
        else:
            position = "driver"  # 默认主驾
        return {
            "Seat_Action": {
                "op": op, "position": position, "level": 1,
                "direction": op if op in ("forward", "backward") else None,
            }
        }

    def _extract_navigation(self, text: str) -> dict[str, Any]:
        # 位置查询优先 — 覆盖多种自然语言表达方式
        location_keywords = (
            # 基础位置查询
            "我在哪", "当前位置", "我在什么位置", "现在在哪", "我的位置",
            "我们在哪", "这是哪", "我在哪儿", "我们在哪儿", "这是哪里",
            # "哪里" 变体 — 覆盖 "我现在哪里"、"我在哪里" 等之前遗漏的表达
            "现在哪里", "我在哪里", "我们在哪里", "现在在哪儿", "在哪儿了",
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
            # "处于" 变体 — 覆盖 "我现在处于什么位置"、"处于哪个位置" 等表达
            "处于什么位置", "处于哪个位置", "处于位置", "现在处于", "我处于",
            # "什么位置" 通用匹配 — 组合上下文已足够特异
            "什么位置",
            # 定位相关
            "定位", "查看定位", "我的定位", "GPS位置", "GPS定位",
            # 其他常见表达
            "这是什么地方", "这里是哪", "当前位置信息",
        )
        if any(k in text for k in location_keywords):
            return {"Navigation_Action": {"op": "location", "destination": "", "waypoint": "", "mode": "drive"}}

        # P2 修复: 空调/车控语境排除 — "空调开到27度" 中的 "开到" 是温度设置，不是导航
        # 只有同时包含明确的导航关键词(导航/带我去/前往/去往)才不排除
        climate_keywords = ("空调", "车内温度", "风量", "风速", "制冷", "制热", "除雾", "座椅", "车窗", "车况")
        if any(k in text for k in climate_keywords):
            if not any(k in text for k in ("导航", "带我去", "前往", "去往", "回")):
                return {}

        nav_keywords = (
            "导航", "带我", "前往", "回家", "充电站",
            "去公司", "去学校", "去机场", "开去", "去往",
        )
        if not any(k in text for k in nav_keywords):
            # "开到" 单独检查 — 仅当后面不是数字(温度)时才视为导航
            if "开到" in text:
                after_kai_dao = text[text.index("开到") + 2:]
                if re.match(r"\d", after_kai_dao):
                    return {}  # "开到27度" → 空调语境，不触发导航
            elif not re.search(r"去[^，。！？?]{1,12}(家|公司|学校|机场|医院|商场|车站|充电站)", text):
                return {}

        destination = ""
        for keyword in ("回家", "去公司", "去学校", "充电站"):
            if keyword in text:
                destination = keyword.replace("去", "")
                break

        if not destination:
            match = re.search(r"(导航到|前往|去往|带我去|开去|去|到)([^，。！？?]+)", text)
            if match:
                destination = match.group(2)

        return {"Navigation_Action": {"destination": destination or "目的地", "waypoint": "", "mode": "drive"}}

    def _extract_media(self, text: str) -> dict[str, Any]:
        """解析媒体控制意图。

        分段解析：在包含媒体领域关键词的子句内解析操作动词，
        避免"关闭车窗，打开音乐"中车窗子句的"关闭"被误匹配为媒体 stop 操作。
        """
        if not any(k in text for k in ("音乐", "播放", "暂停", "停止", "下一首", "上一首", "音量", "切歌", "听歌", "歌曲", "歌")):
            return {}

        # 分段解析 — 仅在包含媒体关键词的子句内查找操作动词
        segments = self._split_segments(text)
        media_segments = [s for s in segments if any(k in s for k in ("音乐", "播放", "暂停", "停止", "下一首", "上一首", "音量", "切歌", "听歌", "歌曲", "歌"))]
        if not media_segments:
            media_segments = [text]

        # 操作动词解析 — 仅在媒体子句内匹配
        # P1 修复 + P6.4: 区分暂停和停止语义
        # "暂停" → pause (保留进度，可恢复)
        # "停止"/"关闭"/"别放" → stop (完全停止，重置进度)
        op = None
        for seg in media_segments:
            if any(k in seg for k in ("停止", "关闭", "关掉", "关了", "别放", "别唱", "关音乐", "停止播放", "关歌")):
                op = "stop"
                break
            if any(k in seg for k in ("暂停", "静音")):
                op = "pause"
                break
            if any(k in seg for k in ("下一首", "下一曲")):
                op = "next"
                break
            if any(k in seg for k in ("上一首", "上一曲")):
                op = "prev"
                break
            if any(k in seg for k in ("播放", "放音乐", "听歌", "听音乐", "放首歌", "来首")):
                op = "play"
                break
        # 回退到整句匹配
        if op is None:
            if any(k in text for k in ("停止", "关闭", "关掉", "关了", "别放", "别唱", "关音乐", "停止播放", "关歌")):
                op = "stop"
            elif any(k in text for k in ("暂停", "静音")):
                op = "pause"
            elif any(k in text for k in ("下一首", "下一曲")):
                op = "next"
            elif any(k in text for k in ("上一首", "上一曲")):
                op = "prev"
            elif any(k in text for k in ("播放", "放音乐", "听歌", "听音乐", "放首歌", "来首")):
                op = "play"
            else:
                op = "play"

        # 音量解析 — 在媒体子句内匹配
        volume = None
        for seg in media_segments:
            vol_match = re.search(r"音量(\d{1,2})", seg)
            if vol_match:
                volume = int(vol_match.group(1))
                break
        if volume is None:
            vol_match = re.search(r"音量(\d{1,2})", text)
            if vol_match:
                volume = int(vol_match.group(1))

        return {"Media_Action": {"op": op, "source": "local", "track": "", "volume": volume}}

    def _extract_vehicle_status(self, text: str) -> dict[str, Any]:
        # 位置查询 — 与 _extract_navigation 互斥，导航 extractor 已处理则跳过
        if any(k in text for k in ("我在哪", "当前位置", "我在什么位置", "现在在哪", "我的位置",
                                   "我们在哪", "这是哪", "现在哪里", "我在哪里", "我们在哪里",
                                   "现在在哪儿", "在哪儿了", "这是哪里", "什么位置", "处于")):
            return {}

        if not any(k in text for k in ("车况", "胎压", "续航", "油量", "电量", "保养", "车辆状态")):
            return {}
        return {"Vehicle_Status_Action": {"op": "status"}}

    def _extract_time(self, text: str) -> dict[str, Any]:
        """检测时间查询意图。

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

    def _extract_nearby_poi(self, text: str) -> dict[str, Any]:
        """检测周边 POI 搜索意图（附近美食、周边加油站等）。

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
            (
                ("好吃的", "美食", "餐厅", "吃饭", "吃饭的地方",
                 "外卖店", "餐馆", "小吃", "火锅", "烧烤", "面馆", "快餐"),
                "餐厅", "restaurant",
            ),
            # 加油站
            (("加油站", "加油", "加气站"), "加油站", "gas_station"),
            # 停车场
            (("停车场", "停车", "停车位", "停车区"), "停车场", "parking"),
            # 景点
            (("景点", "景区", "公园", "游玩", "旅游", "名胜", "遗迹"), "景点", "attraction"),
            # 超市
            (("超市", "便利店", "商场", "购物", "商店", "mall"), "超市", "supermarket"),
            # 酒店/酒旅
            (
                ("酒店", "宾馆", "住宿", "旅馆", "民宿",
                 "酒旅", "旅游", "旅行", "出游", "度假", "订房"),
                "酒店", "hotel",
            ),
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

    def _extract_weather(self, text: str) -> dict[str, Any]:
        """检测天气查询意图。

        当用户询问天气、温度、下雨、下雪等天气信息时，
        路由到和风天气 (QWeather) API 技能，
        而非 Tavily 通用搜索（后者返回的结果不准确且 LLM 合成容易超时）。
        """
        # 天气关键词
        weather_keywords = (
            "天气", "气温", "温度多少", "下雨", "下雪",
            "出太阳", "紫外线", "湿度", "风多大",
            "会下雨", "会下雪", "会天晴", "冷不冷", "热不热",
        )
        if not any(k in text for k in weather_keywords):
            return {}

        # 排除车控类温度查询（如"空调温度"已被前面的 _extract_climate 拦截）
        # 排除"车内温度"等
        if any(k in text for k in ("空调", "车内", "车里", "胎压")):
            return {}

        # 提取原始查询作为参数
        return {"Weather_Action": {"query": text}}

    def _extract_search(self, text: str) -> dict[str, Any]:
        """检测联网搜索意图"""
        # 如果包含周边搜索关键词，不拦截为通用搜索（已由 _extract_nearby_poi 处理）
        nearby_keywords = ("附近", "周边", "周围", "就近")
        nearby_poi_keywords = (
            "好吃的", "美食", "餐厅", "吃饭", "加油站", "停车场",
            "景点", "超市", "酒店", "医院", "银行", "洗车",
            "酒旅", "旅游", "旅行", "住宿", "民宿", "度假",
        )
        if any(k in text for k in nearby_keywords) and any(k in text for k in nearby_poi_keywords):
            return {}

        # 如果包含点餐关键词，不拦截为搜索
        food_keywords = ("点外卖", "饿了", "想吃", "点餐", "叫外卖", "吃什么", "帮我点")
        if any(k in text for k in food_keywords):
            return {}

        # 如果包含媒体关键词且有“推荐”，不拦截为搜索（让 _extract_media 处理推荐歌曲/音乐）
        media_keywords = ("音乐", "歌曲", "歌", "播放", "听歌")
        if any(k in text for k in media_keywords) and "推荐" in text and not any(k in text for k in ("美食", "餐厅", "酒旅", "旅游", "景点")):
            return {}

        # 如果包含天气关键词，不拦截为搜索（已由 _extract_weather 处理）
        weather_keywords = (
            "天气", "气温", "温度多少", "下雨", "下雪",
            "出太阳", "紫外线", "湿度", "风多大",
            "会下雨", "会下雪", "会天晴", "冷不冷", "热不热",
        )
        if any(k in text for k in weather_keywords):
            return {}

        # 如果包含位置查询关键词，不拦截为搜索（已由 _extract_navigation 处理）
        # 防止 "我现在哪里"、"我现在在哪" 等位置查询被 "在哪" 误匹配为搜索
        location_keywords = (
            "我在哪", "我们在哪", "这是哪", "现在哪里", "我在哪里",
            "我们在哪里", "现在在哪儿", "在哪儿了", "在哪儿", "现在在哪",
            "当前位置", "我的位置", "我的定位", "查看定位", "GPS位置", "GPS定位",
            "这是什么地方", "这里是哪", "什么位置", "处于",
        )
        if any(k in text for k in location_keywords):
            return {}

        # 搜索关键词（移除"天气"，避免与 _extract_weather 冲突）
        # 酒旅/美食推荐等非附近搜索也纳入
        search_keywords = (
            "搜索", "查一下", "查询", "查查", "帮我查", "请问",
            "附近", "周边", "附近有", "哪里有", "在哪",
            "新闻", "百科", "什么是", "是怎么回事",
            "怎么样", "好不好", "评分", "评价", "几点", "营业",
            "多少钱", "价格", "最新",
            # 酒旅/美食推荐类 — 不含“附近”时也触发搜索
            "酒旅", "旅游", "旅行", "出游", "度假",
            "美食推荐", "推荐美食", "好吃的地方", "餐饮推荐",
            "推荐",  # “推荐”作为通用搜索信号（如“推荐一些美食”“推荐好玩的景点”）
        )
        if not any(k in text for k in search_keywords):
            return {}

        # 如果是导航意图（包含“导航”“去”等），不拦截
        if any(k in text for k in ("导航", "带我", "前往", "开到", "去往")):
            return {}

        # 提取搜索 query：原文本即作为搜索关键词
        return {"Need_Search": text}

    def _extract_food(self, text: str) -> dict[str, Any]:
        """检测点餐意图"""
        food_keywords = ("点外卖", "饿了", "想吃", "点餐", "叫外卖", "吃什么", "帮我点")
        if not any(k in text for k in food_keywords):
            return {}
        # 提取食物名称
        match = re.search(r"(?:想吃|点|叫|来)([^，。！？?]+)", text)
        food = match.group(1) if match else "随便"
        return {"Call_elm": True, "Food_candidate": food}
