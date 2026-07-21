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
