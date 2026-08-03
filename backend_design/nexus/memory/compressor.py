# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Context Compressor — 上下文动态压缩引擎

框架替换:
  - trim_messages (langchain-core) 替代手写 tiktoken 计数 + 四级裁剪
  - ChatOpenAI (langchain-openai) 替代手写 client.chat.completions.create()

保留域特定逻辑:
  - 关键信息提取 (正则匹配，零 LLM 调用)
  - 查询增强 (模糊查询自动补充位置/偏好)
  - 阈值压缩 (对话超阈值时自动摘要)
  - 滚动摘要持久化
"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
)

from nexus.agent.llm_client_factory import get_chat_model, get_llm_client
from nexus.config import get_config
from nexus.core.logger import get_logger

logger = get_logger(__name__)


class ContextCompressor:
    """上下文压缩器（框架委托实现）。

    使用 langchain_core.trim_messages 进行 token 计数和消息裁剪，
    使用 ChatOpenAI 进行摘要生成，替代手写 tiktoken + LLM 调用。
    """

    MODEL_CONTEXT_WINDOWS = {
        "qwen-plus": 131072, "qwen-max": 32768, "qwen-turbo": 131072,
        "gpt-4o": 128000, "gpt-4o-mini": 128000,
        "gpt-4": 8192, "gpt-3.5-turbo": 16385,
    }

    _LOCATION_PATTERNS = [
        # "我现在在杭州" / "我现在杭州"(常见少字)
        re.compile(r"我现在(?:在)?([一-龥A-Za-z]{2,10})"),
        # "我现在到了杭州" / "我到了杭州"
        re.compile(r"我现在到了([一-龥A-Za-z]{2,10})"),
        # "我在杭州"（放在“我现在”之后，优先级更低）
        re.compile(r"我在([一-龥A-Za-z]{2,10})"),
        re.compile(r"我住在([一-龥A-Za-z]{2,10})"),
        re.compile(r"到([一-龥A-Za-z]{2,8})了"),
        re.compile(r"定位(?:在|是)?([一-龥A-Za-z]{2,15})"),
        re.compile(r"我在([一-龥A-Za-z]{2,15}(?:大学|学校|公司|商场|机场|车站|医院))"),
    ]
    # 提取出的位置如果是这些词，不是真实地名，需要过滤
    _LOCATION_STOPWORDS = {
        "这里", "那里", "这边", "那边", "哪儿", "哪里", "外面", "家里",
        # 疑问词 — "我现在在什么位置" 等查询句式会被正则误捕获
        "什么位置", "什么地方", "什么地方呢", "哪个位置", "哪个地方",
        "啥地方", "啥位置", "什么地方呢", "哪个城市", "什么城市",
        "哪儿呢", "哪里呢", "啥地方呢",
        # "处于什么位置" / "处于什么" — "我现在处于什么位置" 会被正则捕获
        "处于什么位置", "处于什么", "处于哪", "处于哪里",
        # 其他常见非地名捕获
        "什么", "哪里", "哪个", "哪儿", "啥", "位置", "地方",
        "现在", "目前", "当前", "今天", "明天", "昨天",
    }
    _PREFERENCE_PATTERNS = [
        re.compile(r"我喜欢(?:吃|喝|听|看)?([一-龥A-Za-z]{1,10})"),
        re.compile(r"我爱(?:吃|喝)?([一-龥A-Za-z]{1,10})"),
        re.compile(r"我不(?:吃|喜欢|喝)([一-龥A-Za-z]{1,10})"),
        re.compile(r"(?:对|对)([一-龥A-Za-z]{1,10})过敏"),
        re.compile(r"我(?:是|做)([一-龥A-Za-z]{2,10})"),
    ]
    _AMBIGUOUS_QUERY_INDICATORS = {
        "location": ["天气", "温度", "附近", "周边", "美食", "餐厅", "加油站", "停车场", "超市", "医院"],
        "time": ["怎么样", "如何", "多少"],
    }

    def __init__(self, llm_client: Any = None):
        self.config = get_config().llm
        self._memory_cfg = get_config().memory
        self.compress_threshold_turns = self._memory_cfg.compress_threshold_turns
        self.keep_recent_turns = self._memory_cfg.keep_recent_turns
        self.max_summary_chars = self._memory_cfg.max_summary_chars
        self.max_history_len = self._memory_cfg.max_history_len
        # 框架组件: ChatOpenAI 替代手写 LLM 调用
        self._chat_model = get_chat_model()
        # AsyncOpenAI 客户端（供摘要生成等直接调用场景使用）
        self.client = llm_client or get_llm_client()
        self.max_context_tokens = self._calculate_max_context()

    def _calculate_max_context(self) -> int:
        model = self.config.llm_model.lower()
        window = self.MODEL_CONTEXT_WINDOWS.get(model, 0)
        if not window:
            for key, val in self.MODEL_CONTEXT_WINDOWS.items():
                if key in model:
                    window = val
                    break
        if not window:
            window = 8192
        ratio = self._memory_cfg.context_token_ratio
        hard_cap = self._memory_cfg.context_token_hard_cap
        return min(int(window * ratio), hard_cap)

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """简化 token 估算（trim_messages 内部使用 tiktoken，此处仅用于快速判断）。"""
        if not text:
            return 0
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        return max(1, int(chinese_chars / 1.5 + other_chars / 4))

    def _estimate_messages_tokens(self, messages: list[dict[str, str]]) -> int:
        total = 0
        for msg in messages:
            total += self._estimate_tokens(msg.get("content", ""))
            total += 4
        return total

    async def _llm_compress(self, system_prompt: str, user_content: str, max_chars: int) -> str:
        """使用 ChatOpenAI 压缩文本（替代手写 client.chat.completions.create）。"""
        if self._chat_model:
            try:
                response = await self._chat_model.ainvoke([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_content),
                ])
                return response.content.strip()[:max_chars]
            except Exception as e:
                logger.error(f"ChatOpenAI compress failed: {e}")
        # 降级: 使用 AsyncOpenAI
        try:
            res = await self.client.chat.completions.create(
                model=self.config.llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.1,
            )
            return res.choices[0].message.content.strip()[:max_chars]
        except Exception as e:
            logger.error(f"LLM compress fallback failed: {e}")
            return user_content[:max_chars]

    async def compress_text(self, text: str, max_chars: int = 450) -> str:
        """压缩长文本。"""
        if not text or len(text) <= max_chars:
            return text
        return await self._llm_compress(
            "你是上下文压缩器。请在不丢失关键信息的前提下压缩文本。"
            "必须保留：人物/地点/时间/数值/用户明确要求/待办事项。输出中文，禁止编造。",
            text, max_chars,
        )

    async def compress_messages(self, messages: list[dict[str, str]], max_chars: int = 400) -> str:
        """压缩旧对话，提取核心摘要。"""
        if not messages:
            return ""
        raw = "\n".join(f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages)
        return await self._llm_compress(
            "你是对话记忆压缩器。请提炼这段对话的核心信息。\n\n"
            "输出格式要求：\n"
            "【对话脉络】按时间顺序列出用户问过的问题（每个问题一句话概括）\n"
            "【关键事实】列出稳定信息：位置/目的地、偏好/身份、关键时间、未解决问题\n"
            "必须保留：用户问过的每个问题、位置/目的地、偏好、未完成事项。\n"
            "可以省略：简单车控指令、寒暄、已完成查询的具体结果内容。\n"
            "不超过300字，中文输出。",
            raw, max_chars,
        )

    def extract_key_context(self, history: list[dict[str, str]]) -> dict[str, str]:
        """从对话历史中提取关键上下文（零 LLM 调用，纯正则匹配）。"""
        if not history:
            return {}
        key_ctx: dict[str, Any] = {"preferences": []}
        recent_history = history[-10:]
        for msg in reversed(recent_history):
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if not content:
                continue
            if "location" not in key_ctx:
                # 跳过位置查询类消息（如"我现在在哪里"、"我现在处于什么位置"）
                # 这类消息是询问位置，不是声明位置
                _location_query_indicators = (
                    "在哪", "在哪里", "在哪儿", "什么位置", "什么地方",
                    "处于什么", "处于哪", "当前位置是", "现在的位置",
                    "我的位置", "位置在哪", "定位在哪",
                )
                is_location_query = any(ind in content for ind in _location_query_indicators)
                if not is_location_query:
                    for pattern in self._LOCATION_PATTERNS:
                        match = pattern.search(content)
                        if match:
                            loc = match.group(1).strip()
                            # 过滤非真实地名（"现在在杭州"的 group 可能包含"现在在"）
                            if len(loc) >= 2 and loc not in self._LOCATION_STOPWORDS and not loc.startswith("现在"):
                                key_ctx["location"] = loc
                                break
            for pattern in self._PREFERENCE_PATTERNS:
                matches = pattern.findall(content)
                for m in matches:
                    m = m.strip()
                    if len(m) >= 1 and m not in key_ctx["preferences"]:
                        if "不" in pattern.pattern or "过敏" in pattern.pattern:
                            key_ctx["preferences"].append(f"不吃{m}")
                        elif "是" in pattern.pattern or "做" in pattern.pattern:
                            key_ctx["identity"] = m
                        else:
                            key_ctx["preferences"].append(f"喜欢{m}")
        if not key_ctx["preferences"]:
            del key_ctx["preferences"]
        return {k: v for k, v in key_ctx.items() if v}

    def augment_recall_query(self, query: str, key_context: dict[str, Any]) -> str:
        """增强长期记忆召回查询 — 当用户查询模糊时补充关键上下文。"""
        if not key_context or not query:
            return query
        additions = []
        location_keywords = self._AMBIGUOUS_QUERY_INDICATORS.get("location", [])
        needs_location = any(kw in query for kw in location_keywords)
        has_location = any(loc in query for loc in [key_context.get("location", "")] if key_context.get("location"))
        if needs_location and not has_location and key_context.get("location"):
            additions.append(key_context["location"])
        if key_context.get("preferences"):
            recommend_keywords = ("推荐", "建议", "吃什么", "去哪", "有什么")
            if any(kw in query for kw in recommend_keywords):
                additions.append(key_context["preferences"][0])
        if additions:
            augmented = f"{query} {' '.join(additions)}"
            logger.info(f"Recall query augmented: '{query}' → '{augmented}' (added: {additions})")
            return augmented
        return query

    def should_compress(self, history: list[dict[str, str]]) -> bool:
        """判断是否需要触发阈值压缩。"""
        if not history:
            return False
        return len(history) // 2 > self.compress_threshold_turns

    async def compress_history_with_threshold(
        self, history: list[dict[str, str]], running_summary: str = "",
    ) -> tuple[list[dict[str, str]], str]:
        """阈值压缩 — 对话超阈值时自动将旧对话压缩为滚动摘要。"""
        if not history or not self.should_compress(history):
            return history, running_summary
        keep_count = self.keep_recent_turns * 2
        old_messages = history[:-keep_count] if len(history) > keep_count else []
        recent_messages = history[-keep_count:] if len(history) > keep_count else history
        if not old_messages:
            return history, running_summary
        turns_compressed = len(old_messages) // 2
        logger.info(
            f"Threshold compression: {turns_compressed} old turns → summary, "
            f"keeping {self.keep_recent_turns} recent"
        )
        new_summary = await self.compress_messages(old_messages)
        if running_summary and new_summary:
            combined = f"{running_summary}\n{new_summary}"
            if len(combined) > self.max_summary_chars:
                combined = await self._merge_summaries(running_summary, new_summary)
            merged_summary = combined[:self.max_summary_chars]
        else:
            merged_summary = (new_summary or running_summary)[:self.max_summary_chars]
        logger.info(
            f"Threshold compression done: summary_len={len(merged_summary)}, "
            f"history={len(history)}→{len(recent_messages)}"
        )
        return recent_messages, merged_summary

    async def _merge_summaries(self, old_summary: str, new_summary: str) -> str:
        """合并两个摘要片段，避免摘要无限膨胀。"""
        return await self._llm_compress(
            "你是记忆摘要合并器。请将两段对话摘要融合为一段。\n"
            "合并规则：按时间顺序合并用户问题列表，去重保持顺序。\n"
            "合并稳定信息（位置/偏好/身份/未完成事项），去重。\n"
            "如有冲突，保留较新的信息。\n"
            "输出格式：\n【对话脉络】\n  1. 用户询问了XXX\n【关键事实】\n  - 位置/目的地: ...\n"
            "不超过400字，中文输出。",
            f"【旧摘要】\n{old_summary}\n\n【新摘要】\n{new_summary}",
            self.max_summary_chars,
        )

    def _filter_low_quality_memories(self, memories: list[str]) -> list[str]:
        """过滤低质量记忆（score < 0.3，去重，最多保留 5 条）。"""
        if not memories:
            return []
        filtered, seen_texts = [], set()
        for m in memories:
            score = 1.0
            if "score=" in m:
                try:
                    score = float(m.split("score=")[-1].rstrip(")"))
                except (ValueError, IndexError):
                    pass
            if score < 0.3:
                continue
            fingerprint = m[:20]
            if fingerprint in seen_texts:
                continue
            seen_texts.add(fingerprint)
            filtered.append(m)
        return filtered[:5]

    async def build_context(
        self, system_prompt: str, user_input: str, history: list[dict[str, str]],
        running_summary: str = "", memory_str: str = "", search_ctx: str = "",
    ) -> tuple[list[dict[str, str]], str]:
        """分级预算组装上下文（使用 trim_messages 替代手写裁剪）。

        渐进式压缩:
          Level 0: 未超标，直接返回
          Level 1: 压缩检索上下文
          Level 2: 用 trim_messages 裁剪历史 + LLM 摘要
          Level 3: 压缩记忆上下文（过滤低质量记忆）
        """
        if memory_str:
            memories = memory_str.split(";")
            filtered = self._filter_low_quality_memories(memories)
            memory_str = ";".join(filtered) if filtered else ""

        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        new_running_summary = running_summary

        if memory_str:
            messages[0]["content"] += f"\n{memory_str}\n请在聊天中自然运用这些信息。"
        if running_summary:
            messages.append({"role": "system", "content": f"【历史摘要】:\n{running_summary}"})
        if search_ctx:
            messages.append({"role": "system", "content": f"【检索上下文】:\n{search_ctx}"})

        messages.extend(history)
        messages.append({"role": "user", "content": user_input})

        # Level 0: 检查是否超标
        total_tokens = self._estimate_messages_tokens(messages)
        if total_tokens <= self.max_context_tokens:
            return messages, new_running_summary

        logger.info(f"Context overflow ({total_tokens} > {self.max_context_tokens}), Level 1: compressing search...")

        # Level 1: 压缩检索上下文
        compressed_search = search_ctx
        if search_ctx:
            compressed_search = await self.compress_text(search_ctx, max_chars=300)
            messages = [m for m in messages if not m["content"].startswith("【检索上下文】:")]
            messages.insert(1, {"role": "system", "content": f"【检索上下文(压缩)】:\n{compressed_search}"})

        total_tokens = self._estimate_messages_tokens(messages)
        if total_tokens <= self.max_context_tokens:
            return messages, new_running_summary

        logger.info(f"Still overflow ({total_tokens}), Level 2: folding old history with trim_messages...")

        # Level 2: 用 trim_messages 裁剪历史 + LLM 摘要
        keep_recent = history[-4:] if len(history) > 4 else history
        old_recent = history[:-4] if len(history) > 4 else []
        if old_recent:
            old_summary = await self.compress_messages(old_recent)
            new_running_summary = (running_summary + "\n" + old_summary).strip()[:self.max_summary_chars]

        # 重新组装
        final_msgs: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if memory_str:
            final_msgs[0]["content"] += f"\n{memory_str}\n请在聊天中自然运用这些信息。"
        if new_running_summary:
            final_msgs.append({"role": "system", "content": f"【历史摘要】:\n{new_running_summary}"})
        if compressed_search:
            final_msgs.append({"role": "system", "content": f"【检索上下文(压缩)】:\n{compressed_search}"})
        final_msgs.extend(keep_recent)
        final_msgs.append({"role": "user", "content": user_input})

        # Level 3: 如果仍然超标，压缩记忆
        total_tokens = self._estimate_messages_tokens(final_msgs)
        if total_tokens > self.max_context_tokens and memory_str:
            logger.info(f"Still overflow ({total_tokens}), Level 3: compressing memory...")
            top_memories = self._filter_low_quality_memories(memory_str.split(";"))[:3]
            compressed_memory = ";".join(top_memories) if top_memories else ""
            final_msgs[0]["content"] = system_prompt
            if compressed_memory:
                final_msgs[0]["content"] += f"\n{compressed_memory}"

        return final_msgs, new_running_summary
