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
