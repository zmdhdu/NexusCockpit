# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Expert Agents — v2.0 专家 Agent 模块

5 个独立专家 Agent，各自封装一组相关技能:
  - VehicleExpert:   车控（空调/车窗/座椅/媒体/状态）
  - NavExpert:       导航（路线规划/兴趣点）
  - LifestyleExpert: 生活推荐（搜索/点餐/本地生活）
  - HealthExpert:    车辆健康（诊断/故障码/保养）
  - ChatExpert:      闲聊（纯 LLM / 知识库问答）

每个专家的 run() 方法:
  1. 从 SupervisorState 读取 intent
  2. 判断是否需要执行（检查 active_experts）
  3. 调用对应技能
  4. 返回 partial state update（不修改原 state）
"""

from nexus.agent.experts.base import BaseExpertAgent
from nexus.agent.experts.chat_expert import ChatExpert
from nexus.agent.experts.health_expert import HealthExpert
from nexus.agent.experts.lifestyle_expert import LifestyleExpert
from nexus.agent.experts.nav_expert import NavExpert
from nexus.agent.experts.vehicle_expert import VehicleExpert

__all__ = [
    "BaseExpertAgent",
    "VehicleExpert",
    "NavExpert",
    "LifestyleExpert",
    "HealthExpert",
    "ChatExpert",
]
