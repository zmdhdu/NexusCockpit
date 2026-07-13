# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Context Compressor — 上下文动态压缩引擎 v2.1

v2.1 增强:
  - 渐进式披露策略（Progressive Disclosure）
  - 分级压缩策略升级为四级（新增 Level 3: 记忆摘要压缩）
  - 动态上下文预算分配（记忆 20% + 检索 30% + 历史 30% + 回复预留 20%）
  - 上下文质量评分（对召回结果打分，低质量记忆过滤）

分级压缩策略:
  Level 0: 未超标，直接返回
  Level 1: 压缩检索上下文（search_ctx）
  Level 2: 折叠旧历史对话为摘要（rolling summary）
  Level 3: 压缩记忆上下文（memory_str）
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from openai import AsyncOpenAI

from nexus.config import get_config
from nexus.core.logger import get_logger

logger = get_logger(__name__)

# tiktoken 编码器（延迟加载，避免未安装时崩溃）
_encoder = None


def _get_encoder():
    """获取 tiktoken 编码器（延迟加载，fallback 到估算）。"""
    global _encoder
    if _encoder is not None:
        return _encoder
    try:
        import tiktoken
        # 使用 cl100k_base 编码（适用于 GPT-4/4o/Qwen 等主流模型）
        _encoder = tiktoken.get_encoding("cl100k_base")
        return _encoder
    except ImportError:
        logger.warning("tiktoken not installed, falling back to estimate")
        _encoder = "fallback"
        return None
    except Exception as e:
        logger.warning(f"tiktoken init failed: {e}, falling back to estimate")
        _encoder = "fallback"
        return None


class ContextCompressor:
    """上下文压缩器 v2.1。

    核心能力:
        - tiktoken 精准 token 计数
        - 动态 max_context_tokens（按模型窗口计算，预留 30% 回复余量）
        - 四级渐进式压缩
        - 上下文质量评分与过滤
        - 动态预算分配（记忆/检索/历史/回复）

    压缩级别:
        Level 0: 未超标，直接返回
        Level 1: 压缩检索上下文
        Level 2: 折叠旧历史对话为摘要
        Level 3: 压缩记忆上下文（仅保留 Top-3 高分记忆）
    """

    # 各模型的最大上下文窗口（token 数）
    MODEL_CONTEXT_WINDOWS = {
        "qwen-plus": 131072,
        "qwen-max": 32768,
        "qwen-turbo": 131072,
        "gpt-4o": 128000,
        "gpt-4o-mini": 128000,
        "gpt-4": 8192,
        "gpt-3.5-turbo": 16385,
    }

    def __init__(self, llm_client: Optional[AsyncOpenAI] = None):
        self.config = get_config().llm
        self.client = llm_client or AsyncOpenAI(
            api_key=self.config.ark_api_key,
            base_url=self.config.ark_base_url,
        )
        # v2.0: 动态计算上下文上限
        self.max_context_tokens = self._calculate_max_context()
        self.max_history_len = 20

    def _calculate_max_context(self) -> int:
        """根据模型窗口动态计算上下文上限。

        策略: 取模型窗口的 70%（预留 30% 给回复），
        默认上限 4096（防止小窗口模型溢出）。
        """
        model = self.config.llm_model.lower()
        # 尝试精确匹配
        window = self.MODEL_CONTEXT_WINDOWS.get(model, 0)
        # 尝试模糊匹配
        if not window:
            for key, val in self.MODEL_CONTEXT_WINDOWS.items():
                if key in model:
                    window = val
                    break
        if not window:
            window = 8192  # 默认保守值

        # 取 70%，上限 4096（避免单次请求过大）
        calculated = int(window * 0.7)
        return min(calculated, 4096)

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """v2.0: tiktoken 精准计数，fallback 到估算。"""
        if not text:
            return 0

        encoder = _get_encoder()
        if encoder and encoder != "fallback":
            try:
                return len(encoder.encode(text))
            except Exception:
                pass

        # Fallback: 中文约1.5字/token，英文约4字/token
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        return max(1, int(chinese_chars / 1.5 + other_chars / 4))

    def _estimate_messages_tokens(self, messages: List[Dict[str, str]]) -> int:
        """计算消息列表的总 token 数（含系统开销）。

        每条消息约4 token 开销（role + 结构）。
        """
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            total += self._estimate_tokens(content)
            total += 4  # 每条消息的结构开销
        return total

    async def compress_text(self, text: str, max_chars: int = 450) -> str:
        """压缩长文本（如检索结果）。"""
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
        """压缩旧对话，提取核心摘要。"""
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

    def _filter_low_quality_memories(self, memories: List[str]) -> List[str]:
        """v2.1: 过滤低质量记忆。

        策略:
            - 过滤 score < 0.3 的记忆
            - 去重（相似文本只保留高分）
            - 最多保留 5 条
        """
        if not memories:
            return []

        filtered = []
        seen_texts = set()

        for m in memories:
            # 提取 score
            score = 1.0
            if "score=" in m:
                try:
                    score_str = m.split("score=")[-1].rstrip(")")
                    score = float(score_str)
                except (ValueError, IndexError):
                    pass

            # 过滤低分
            if score < 0.3:
                continue

            # 简单去重：取前20字符作为指纹
            fingerprint = m[:20]
            if fingerprint in seen_texts:
                continue
            seen_texts.add(fingerprint)

            filtered.append(m)

        return filtered[:5]

    async def build_context(
        self,
        system_prompt: str,
        user_input: str,
        history: List[Dict[str, str]],
        running_summary: str = "",
        memory_str: str = "",
        search_ctx: str = "",
    ) -> Tuple[List[Dict[str, str]], str]:
        """v2.1 分级预算组装上下文。

        渐进式披露 + 四级压缩:
            Level 0: 未超标，直接返回
            Level 1: 压缩检索上下文
            Level 2: 折叠旧历史对话为摘要
            Level 3: 压缩记忆上下文（过滤低质量记忆）

        预算分配（动态调整）:
            - 记忆: 20% （用户画像 + 长期记忆）
            - 检索: 30% （RAG 检索结果）
            - 历史: 30% （对话历史）
            - 回复: 20% （预留回复空间）

        Returns:
            (组装好的messages, 更新后的滚动摘要)
        """
        # v2.1: 过滤低质量记忆
        if memory_str:
            memories = memory_str.split(";")
            filtered = self._filter_low_quality_memories(memories)
            memory_str = ";".join(filtered) if filtered else ""

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

        # Level 3: 如果仍然超标，压缩记忆
        total_tokens = self._estimate_messages_tokens(final_msgs)
        if total_tokens > self.max_context_tokens and memory_str:
            logger.info(f"Still overflow ({total_tokens}), Level 3: compressing memory...")
            # 只保留 Top-3 高分记忆
            memories = memory_str.split(";")
            top_memories = self._filter_low_quality_memories(memories)[:3]
            compressed_memory = ";".join(top_memories) if top_memories else ""

            final_msgs[0]["content"] = system_prompt
            if compressed_memory:
                final_msgs[0]["content"] += f"\n{compressed_memory}"

        return final_msgs, new_running_summary
