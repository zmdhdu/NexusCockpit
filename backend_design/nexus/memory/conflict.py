# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Memory Conflict Detector — 记忆冲突检测与一致性维护
当新记忆与旧记忆冲突时，自动裁决并删除过期记忆
"""

from __future__ import annotations

import json
import re
from typing import Any

from openai import AsyncOpenAI

from nexus.config import get_config
from nexus.core.logger import get_logger

logger = get_logger(__name__)


class ConflictDetector:
    """记忆冲突检测器"""

    def __init__(self, llm_client: AsyncOpenAI | None = None):
        self.config = get_config().llm
        self.client = llm_client or AsyncOpenAI(
            api_key=self.config.ark_api_key,
            base_url=self.config.ark_base_url,
        )

    async def detect_conflict(
        self,
        new_memory: str,
        existing_memories: list[dict[str, Any]],
        user_input: str = "",
    ) -> dict[str, Any]:
        """
        检测新记忆与现有记忆的冲突
        返回: {"action": "DELETE"|"IGNORE"|"NONE", "ids": [...]}
        """
        if not existing_memories:
            return {"action": "NONE"}

        context_str = "\n".join(
            [
                f"ID:{m['id']} | 内容: {m['text']} (相似度:{m.get('score', 0):.2f})"
                for m in existing_memories
            ]
        )

        prompt = f"""
        你是一个记忆一致性管理员。请根据【原始对话】和【新提取信息】，判断与【现有记忆】的冲突。

        【原始对话语境】(最高优先级):
        "{user_input}"
        (注意：如果用户在对话中明确表示了"不再"、"搬家"、"换工作"、"改做"等变更意图，请坚决删除旧状态。)

        【现有记忆】:
        {context_str}

        【新提取信息】:
        {new_memory}

        请严格根据以下规则裁决：
        1. **显式终止 (DELETE)**: 原始对话中出现 "不让做了"、"戒了"、"改喝..." 等，必须删除旧习惯。
        2. **状态/身份变更 (DELETE)**: "考上公务员"、"回老家"、"搬家"等，旧状态已失效。
        3. **属性冲突 (DELETE)**: "喜欢辣" vs "一点辣都不能吃"。
        4. **冗余 (IGNORE)**: 内容完全一致。
        5. **共存 (NONE)**: 无逻辑冲突。

        输出格式 (JSON):
        - 需删除: {{"action": "DELETE", "ids": [123]}}
        - 冗余: {{"action": "IGNORE"}}
        - 无操作: {{"action": "NONE"}}
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.config.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )
            content = response.choices[0].message.content.strip()
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                return json.loads(match.group())
            return {"action": "NONE"}
        except Exception as e:
            logger.error(f"Conflict detection failed: {e}")
            return {"action": "NONE"}


class MemoryExtractor:
    """从对话中提取长期用户画像"""

    RELATION_TYPES = {
        "LIKES": "喜好",
        "DISLIKES": "厌恶",
        "ALLERGY": "过敏",
        "HABIT": "习惯",
        "IS_A": "身份/职业",
        "LIVES_IN": "居住地",
        "STATUS": "状态",
    }

    def __init__(self, llm_client: AsyncOpenAI | None = None):
        self.config = get_config().llm
        self.client = llm_client or AsyncOpenAI(
            api_key=self.config.ark_api_key,
            base_url=self.config.ark_base_url,
        )

    async def extract(self, user_text: str) -> list[dict[str, str]]:
        """
        从用户输入中提取结构化记忆三元组
        返回: [{"relation": "LIKES", "target": "咖啡", "type": "Food"}, ...]
        """
        prompt = f"""
        ### 任务
        从用户的话中提取**长期用户画像**，并转化为结构化的 JSON 数据以便存入知识图谱。

        ### 提取规则
        1. 识别用户 (User) 与 实体 (Entity) 之间的关系。
        2. 仅提取以下关系类型：
           - LIKES/DISLIKES: 喜好
           - ALLERGY: 过敏
           - HABIT: 习惯
           - IS_A: 身份/职业 (如: 我是学生)
           - LIVES_IN: 居住地 (如: 我住在北京, 我定居上海)
           - STATUS: 状态 (如: 我单身, 我刚搬家)
        3. 如果没有长期有效的信息，输出 "NONE"。

        ### 输出格式 (JSON List)
        [
            {{"relation": "RELATION_TYPE", "target": "Entity_Name", "type": "Entity_Type"}}
        ]

        ### 示例
        输入: "我不吃香菜，我对花生过敏"
        输出: [
            {{"relation": "DISLIKES", "target": "香菜", "type": "Food"}},
            {{"relation": "ALLERGY", "target": "花生", "type": "Ingredient"}}
        ]

        输入: "我是一个程序员"
        输出: [{{"relation": "IS_A", "target": "程序员", "type": "Job"}}]

        输入: "今天天气不错"
        输出: NONE

        ### 用户输入
        "{user_text}"

        ### 你的输出 (仅JSON)
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.config.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )
            content = response.choices[0].message.content.strip()

            if "NONE" in content or "{" not in content:
                return []

            content = content.replace("```json", "").replace("```", "")
            return json.loads(content)
        except Exception as e:
            logger.error(f"Memory extraction failed: {e}")
            return []
