"""
Context Compressor — 上下文动态压缩引擎
分级压缩策略: 检索上下文 → 历史对话 → 滚动摘要
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from openai import AsyncOpenAI

from nexus.config import get_config
from nexus.core.logger import get_logger

logger = get_logger(__name__)


class ContextCompressor:
    """上下文压缩器"""

    def __init__(self, llm_client: Optional[AsyncOpenAI] = None):
        self.config = get_config().llm
        self.client = llm_client or AsyncOpenAI(
            api_key=self.config.ark_api_key,
            base_url=self.config.ark_base_url,
        )
        self.max_context_tokens = 1600
        self.max_history_len = 20

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """中文场景粗估 token 数量"""
        return max(1, int(len(text) / 1.8)) if text else 0

    def _estimate_messages_tokens(self, messages: List[Dict[str, str]]) -> int:
        joined = "\n".join(
            [f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages]
        )
        return self._estimate_tokens(joined)

    async def compress_text(self, text: str, max_chars: int = 450) -> str:
        """压缩长文本（如检索结果）"""
        if not text or len(text) <= max_chars:
            return text

        prompt = [
            {
                "role": "system",
                "content": (
                    "你是上下文压缩器。请在不丢失关键信息的前提下压缩文本。"
                    "必须保留：人物/地点/时间/数值/用户明确要求/待办事项。"
                    "输出中文，禁止编造。"
                ),
            },
            {"role": "user", "content": text},
        ]
        try:
            res = await self.client.chat.completions.create(
                model=self.config.llm_model, messages=prompt, temperature=0.1
            )
            summary = res.choices[0].message.content.strip()
            return summary[:max_chars]
        except Exception as e:
            logger.error(f"Text compression failed: {e}")
            return text[:max_chars]

    async def compress_messages(self, messages: List[Dict[str, str]], max_chars: int = 400) -> str:
        """压缩旧对话，提取核心摘要"""
        if not messages:
            return ""

        raw = "\n".join(
            [f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages]
        )
        prompt = [
            {
                "role": "system",
                "content": (
                    "你是对话记忆压缩器。请提炼这段对话的核心脉络、稳定事实和未完成问题。"
                    "要求极致精简，不超过200字，中文输出。"
                ),
            },
            {"role": "user", "content": raw},
        ]
        try:
            res = await self.client.chat.completions.create(
                model=self.config.llm_model, messages=prompt, temperature=0.1
            )
            return res.choices[0].message.content.strip()[:max_chars]
        except Exception as e:
            logger.error(f"Message compression failed: {e}")
            return ""

    async def build_context(
        self,
        system_prompt: str,
        user_input: str,
        history: List[Dict[str, str]],
        running_summary: str = "",
        memory_str: str = "",
        search_ctx: str = "",
    ) -> Tuple[List[Dict[str, str]], str]:
        """
        分级预算组装上下文
        返回 (组装好的messages, 更新后的滚动摘要)

        压缩级别:
        - Level 0: 未超标，直接返回
        - Level 1: 压缩检索上下文
        - Level 2: 折叠旧历史对话为摘要
        """
        messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        new_running_summary = running_summary

        if memory_str:
            messages[0]["content"] += f"\n{memory_str}\n请在聊天中自然运用这些信息。"
        if running_summary:
            messages.append(
                {"role": "system", "content": f"【历史摘要】:\n{running_summary}"}
            )
        if search_ctx:
            messages.append(
                {"role": "system", "content": f"【检索上下文】:\n{search_ctx}"}
            )

        messages.extend(history)
        messages.append({"role": "user", "content": user_input})

        # Level 0: 检查是否超标
        total_tokens = self._estimate_messages_tokens(messages)
        if total_tokens <= self.max_context_tokens:
            return messages, new_running_summary

        logger.info(f"Context overflow ({total_tokens} > {self.max_context_tokens}), Level 1: compressing search context...")

        # Level 1: 压缩检索上下文
        compressed_search = search_ctx
        if search_ctx:
            compressed_search = await self.compress_text(search_ctx, max_chars=300)
            messages = [
                m for m in messages if not m["content"].startswith("【检索上下文】:")
            ]
            messages.insert(
                1,
                {"role": "system", "content": f"【检索上下文(压缩)】:\n{compressed_search}"},
            )

        total_tokens = self._estimate_messages_tokens(messages)
        if total_tokens <= self.max_context_tokens:
            return messages, new_running_summary

        logger.info(f"Still overflow ({total_tokens}), Level 2: folding old history...")

        # Level 2: 折叠历史对话
        keep_recent = history[-4:] if len(history) > 4 else history
        old_recent = history[:-4] if len(history) > 4 else []

        if old_recent:
            old_summary = await self.compress_messages(old_recent)
            new_running_summary = (running_summary + "\n" + old_summary).strip()[:800]

        # 重新组装
        final_msgs: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if memory_str:
            final_msgs[0]["content"] += f"\n{memory_str}\n请在聊天中自然运用这些信息。"
        if new_running_summary:
            final_msgs.append(
                {"role": "system", "content": f"【历史摘要】:\n{new_running_summary}"}
            )
        if compressed_search:
            final_msgs.append(
                {
                    "role": "system",
                    "content": f"【检索上下文(压缩)】:\n{compressed_search}",
                }
            )

        final_msgs.extend(keep_recent)
        final_msgs.append({"role": "user", "content": user_input})

        return final_msgs, new_running_summary
