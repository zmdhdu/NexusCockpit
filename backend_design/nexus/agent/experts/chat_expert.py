# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Chat Expert — 闲聊专家 Agent

封装纯 LLM 闲聊和声纹注册。
当用户意图不匹配任何技能时，由 Supervisor 分派到此专家。
"""

from __future__ import annotations

from typing import Any

from nexus.agent.experts.base import BaseExpertAgent
from nexus.core.logger import get_logger
from nexus.models.state import SupervisorState
from nexus.skills.base import SkillGroup

logger = get_logger(__name__)


class ChatExpert(BaseExpertAgent):
    """闲聊专家：处理声纹注册和纯 LLM 闲聊。

    声纹注册返回 ACTION_REGISTER 指令供前端处理；
    纯闲聊时不返回 skill_handled=True，让 Responder 走 LLM 分支。
    """

    expert_name = "chat"
    group = SkillGroup.CHAT

    async def _execute(self, state: SupervisorState) -> dict[str, Any]:
        intent = state.get("intent", {})

        # 声纹注册
        register_name = intent.get("Register_Action") or ""
        if register_name and isinstance(register_name, str) and register_name.strip():
            result = await self.registry.execute(
                "register_voice", {"user_name": register_name.strip()}
            )
            return self._build_expert_result(
                action="register_voice",
                reply=result.message,
                handled=result.handled,
                skill_status=result.status,
            )

        # 纯闲聊：不标记 handled，让 Responder 走 LLM 分支
        return self._build_expert_result(
            action="chat",
            reply="",
            handled=False,
        )
