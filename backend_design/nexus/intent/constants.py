# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Intent Constants — 意图路由常量

集中定义车控意图字段，避免在多处硬编码。
"""

# 车控意图字段集合 — 命中其中任一即为车控指令
VEHICLE_INTENT_KEYS = (
    "Climate_Action",
    "Window_Action",
    "Seat_Action",
    "Media_Action",
    "Vehicle_Status_Action",
)

# 非车控意图字段集合 — 当这些意图与车控意图同时出现时，
# 不应走快速路径跳过记忆召回，需要执行完整链路
NON_VEHICLE_INTENT_KEYS = (
    "History_Query_Action",  # 对话历史查询
    "Need_Search",           # 联网搜索
    "Weather_Action",       # 天气查询
    "Poi_Search_Action",    # 周边搜索
    "Call_elm",             # 点餐
    "Health_Action",        # 车辆健康诊断
    "Habit_Action",         # 用户习惯画像
    "Reminder_Action",     # 日程提醒
)

# 车控关键词列表 — 用于语义缓存清理时识别旧的车控缓存条目
# 与 VEHICLE_INTENT_KEYS 配合使用，确保车控指令不被缓存
VEHICLE_CACHE_KEYWORDS = (
    "车窗", "天窗", "开窗", "关窗", "升窗",
    "空调", "车内温度", "风量", "制冷", "制热", "除雾",
    "座椅", "按摩", "加热", "通风",
    "播放", "暂停", "下一首", "上一首", "音量", "切歌", "听歌",
    "车况", "胎压", "续航", "油量", "电量", "保养",
)

# 流式输出分句标点 — 用于 TTS 流式播放时按句拆分输出块
STREAM_SPLIT_PUNCT = ["。", "！", "？", "；", "...", ".", "!", "?"]

# LLM 编造对话历史的可疑模式 — 用于 ReflectionNode 和 OutputGateway 统一引用
# 当 LLM 回复中出现这些模式且对话历史为空时，判定为幻觉
HALLUCINATED_HISTORY_PATTERNS = [
    "您最初是问", "你最初是问", "您第一次问", "你第一次问",
    "您刚才问的是", "你刚才问的是", "您之前问的是", "你之前问的是",
    "您的第一个问题", "你的第一个问题", "您第一句话", "你第一句话",
]
