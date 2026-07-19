# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Context Compressor — 上下文动态压缩引擎

智能上下文记忆管理:
  - 关键信息提取: 从对话历史中提取位置/时间/偏好等关键实体（正则匹配，零 LLM 调用）
  - 查询增强: 当用户查询模糊时（如"明天天气如何"缺位置），自动从短期记忆补充关键词
  - 阈值压缩: 对话轮数超过阈值时自动将旧对话压缩为滚动摘要，保留近期完整对话
  - 滚动摘要持久化: running_summary 跨轮次保存，不丢失压缩后的上下文
  - 渐进式披露策略（Progressive Disclosure）
  - 分级压缩策略（四级）
  - 动态上下文预算分配（记忆 20% + 检索 30% + 历史 30% + 回复预留 20%）
  - 上下文质量评分（对召回结果打分，低质量记忆过滤）

分级压缩策略:
  Level 0: 未超标，直接返回
  Level 1: 压缩检索上下文（search_ctx）
  Level 2: 折叠旧历史对话为摘要（rolling summary）
  Level 3: 压缩记忆上下文（memory_str）

业界方案参考:
  - OpenAI Conversation Management: 滚动窗口 + 摘要策略
  - LangChain ConversationSummaryMemory: 增量摘要
  - MemGPT: 分层记忆 + 上下文溢出时自动压缩
"""

from __future__ import annotations

import re
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
    """上下文压缩器。

    核心能力:
        - tiktoken 精准 token 计数
        - 动态 max_context_tokens（按模型窗口计算，预留 30% 回复余量）
        - 四级渐进式压缩
        - 上下文质量评分与过滤
        - 动态预算分配（记忆/检索/历史/回复）
        - 关键信息提取（位置/时间/偏好，正则匹配零 LLM 调用）
        - 查询增强（模糊查询自动补充短期记忆关键词）
        - 阈值压缩（对话超阈值时自动摘要旧对话）

    压缩级别:
        Level 0: 未超标，直接返回
        Level 1: 压缩检索上下文
        Level 2: 折叠旧历史对话为摘要
        Level 3: 压缩记忆上下文（仅保留 Top-3 高分记忆）

    阈值压缩策略（业界 LangChain ConversationSummaryMemory 思路）:
        当对话轮数 > compress_threshold_turns 时，自动将旧对话压缩为滚动摘要。
        保留最近 keep_recent_turns 轮完整对话，其余折叠为摘要。
        摘要跨轮次持久化（通过 SessionStore 存储 running_summary）。
        以上参数均可通过 .env 环境变量调整（见 MemoryConfig）。
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

    # 阈值压缩参数已迁移至 MemoryConfig（config.py），
    # 可通过 .env 环境变量 MEMORY_COMPRESS_THRESHOLD_TURNS / MEMORY_KEEP_RECENT_TURNS /
    # MEMORY_MAX_SUMMARY_CHARS / MEMORY_MAX_HISTORY_LEN / MEMORY_CONTEXT_TOKEN_RATIO /
    # MEMORY_CONTEXT_TOKEN_HARD_CAP 自行调整，无需改代码。
    # 以下属性在 __init__ 中从 self._memory_cfg 加载，详见 __init__。

    # 关键信息提取的正则模式（零 LLM 调用，纯模式匹配）
    # 位置模式: "我在杭州", "我住在北京", "到上海了", "定位杭州电子科技大学"
    _LOCATION_PATTERNS = [
        re.compile(r"我在([一-龥A-Za-z]{2,10})"),
        re.compile(r"我住在([一-龥A-Za-z]{2,10})"),
        re.compile(r"我到了([一-龥A-Za-z]{2,10})"),
        re.compile(r"到([一-龥A-Za-z]{2,8})了"),
        re.compile(r"定位(?:在|是)?([一-龥A-Za-z]{2,15})"),
        re.compile(r"我在([一-龥A-Za-z]{2,15}(?:大学|学校|公司|商场|机场|车站|医院))"),
    ]
    # 偏好模式: "我喜欢咖啡", "我不吃香菜", "对花生过敏"
    _PREFERENCE_PATTERNS = [
        re.compile(r"我喜欢(?:吃|喝|听|看)?([一-龥A-Za-z]{1,10})"),
        re.compile(r"我爱(?:吃|喝)?([一-龥A-Za-z]{1,10})"),
        re.compile(r"我不(?:吃|喜欢|喝)([一-龥A-Za-z]{1,10})"),
        re.compile(r"(?:对|对)([一-龥A-Za-z]{1,10})过敏"),
        re.compile(r"我(?:是|做)([一-龥A-Za-z]{2,10})"),
    ]
    # 模糊查询判定模式: 缺少关键上下文的查询
    _AMBIGUOUS_QUERY_INDICATORS = {
        "location": ["天气", "温度", "附近", "周边", "美食", "餐厅", "加油站", "停车场", "超市", "医院"],
        "time": ["怎么样", "如何", "多少"],
    }

    def __init__(self, llm_client: Optional[AsyncOpenAI] = None):
        self.config = get_config().llm
        # 从 MemoryConfig 读取阈值压缩参数（可通过 .env 调整）
        self._memory_cfg = get_config().memory
        self.compress_threshold_turns = self._memory_cfg.compress_threshold_turns
        self.keep_recent_turns = self._memory_cfg.keep_recent_turns
        self.max_summary_chars = self._memory_cfg.max_summary_chars
        self.max_history_len = self._memory_cfg.max_history_len
        self.client = llm_client or AsyncOpenAI(
            api_key=self.config.ark_api_key,
            base_url=self.config.ark_base_url,
        )
        # 动态计算上下文上限（比例和硬上限从配置读取）
        self.max_context_tokens = self._calculate_max_context()

    def _calculate_max_context(self) -> int:
        """根据模型窗口动态计算上下文上限。

        比例和硬上限从 MemoryConfig 读取（可通过 .env 调整）。
        策略: 取模型窗口的 context_token_ratio（默认 70%，预留 30% 给回复），
        上限不超过 context_token_hard_cap（默认 4096，防止单次请求过大）。
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

        # 从配置读取比例和硬上限
        ratio = self._memory_cfg.context_token_ratio
        hard_cap = self._memory_cfg.context_token_hard_cap
        calculated = int(window * ratio)
        return min(calculated, hard_cap)

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """tiktoken 精准计数，fallback 到估算。"""
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
        """压缩旧对话，提取核心摘要。

        压缩提示词更注重保留稳定事实（位置/偏好/身份），
        过滤临时性对话（如简单车控指令），提升摘要的信息密度。
        """
        if not messages:
            return ""

        raw = "\n".join(
            [f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages]
        )
        prompt = [
            {
                "role": "system",
                "content": (
                    "你是对话记忆压缩器。请提炼这段对话的核心信息。\n\n"
                    "输出格式要求（严格遵守）：\n"
                    "【对话脉络】按时间顺序列出用户问过的问题（每个问题一句话概括），格式：\n"
                    "  1. 用户询问了XXX\n"
                    "  2. 用户询问了XXX\n\n"
                    "【关键事实】列出稳定信息：\n"
                    "  - 位置/目的地\n"
                    "  - 用户偏好/身份\n"
                    "  - 关键时间约定\n"
                    "  - 未解决问题\n\n"
                    "必须保留：用户问过的每个问题（这是最重要的）、位置/目的地、偏好、未完成事项。\n"
                    "可以省略：简单车控指令（空调/车窗）、寒暄、已完成查询的具体结果内容。\n"
                    "不超过300字，中文输出。"
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

    # ============================================================
    # 智能上下文记忆管理 — 关键信息提取 / 查询增强 / 阈值压缩
    # ============================================================

    def extract_key_context(self, history: List[Dict[str, str]]) -> Dict[str, str]:
        """从对话历史中提取关键上下文信息（零 LLM 调用，纯正则匹配）。

        从最近的对话历史中提取用户提到的关键实体，包括:
        - location: 用户当前/提及的位置（如 "杭州"、"杭州电子科技大学"）
        - preferences: 用户偏好列表（如 "喜欢咖啡"、"不吃香菜"）
        - identity: 用户身份/职业（如 "学生"、"程序员"）

        提取策略:
            1. 从后向前遍历对话历史（最新信息优先）
            2. 使用预编译正则模式匹配关键实体
            3. 同一类型只保留最新值（位置可能变化，取最新）
            4. 最多扫描最近 10 条消息（5 轮对话），避免全量扫描

        Args:
            history: 对话历史列表 [{role, content}, ...]

        Returns:
            提取的关键上下文字典，如 {"location": "杭州", "preferences": ["喜欢咖啡"]}
        """
        if not history:
            return {}

        key_ctx: Dict[str, Any] = {"preferences": []}
        # 只扫描最近 10 条消息（5 轮），避免全量扫描
        recent_history = history[-10:]

        # 从后向前遍历，最新信息优先
        for msg in reversed(recent_history):
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if not content:
                continue

            # 提取位置（只保留最新的一条）
            if "location" not in key_ctx:
                for pattern in self._LOCATION_PATTERNS:
                    match = pattern.search(content)
                    if match:
                        loc = match.group(1).strip()
                        # 过滤过短或无意义的匹配
                        if len(loc) >= 2 and loc not in ("这里", "那里", "这边", "那边"):
                            key_ctx["location"] = loc
                            break

            # 提取偏好（收集所有匹配）
            for pattern in self._PREFERENCE_PATTERNS:
                matches = pattern.findall(content)
                for m in matches:
                    m = m.strip()
                    if len(m) >= 1 and m not in key_ctx["preferences"]:
                        # 判断是喜好还是厌恶
                        if "不" in pattern.pattern or "过敏" in pattern.pattern:
                            key_ctx["preferences"].append(f"不吃{m}")
                        elif "是" in pattern.pattern or "做" in pattern.pattern:
                            key_ctx["identity"] = m
                        else:
                            key_ctx["preferences"].append(f"喜欢{m}")

        # 清理空列表
        if not key_ctx["preferences"]:
            del key_ctx["preferences"]
        # 只保留有值的字段
        return {k: v for k, v in key_ctx.items() if v}

    def augment_recall_query(self, query: str, key_context: Dict[str, Any]) -> str:
        """增强长期记忆召回查询 — 当用户查询模糊时补充关键上下文。

        核心场景:
            用户第 1-5 轮说 "我在杭州"，第 6 轮问 "明天天气如何"
            → 原始查询 "明天天气如何" 无法召回位置相关记忆
            → 增强查询 "明天天气如何 杭州" 能召回位置记忆

        增强策略:
            1. 检测查询是否包含位置相关关键词（天气/附近/美食等）但缺少具体位置
            2. 如果缺少位置，从 key_context 中补充
            3. 检测查询是否缺少时间信息但涉及时间敏感话题
            4. 最多补充 2 个关键词，避免查询过长影响向量检索精度

        Args:
            query: 用户原始查询
            key_context: 从 extract_key_context 提取的关键上下文

        Returns:
            增强后的查询字符串（如 "明天天气如何 杭州"）
        """
        if not key_context or not query:
            return query

        augmented = query
        additions = []

        # 检测查询是否需要位置但缺少位置
        location_keywords = self._AMBIGUOUS_QUERY_INDICATORS.get("location", [])
        needs_location = any(kw in query for kw in location_keywords)
        has_location_in_query = any(
            loc in query for loc in [key_context.get("location", "")]
            if key_context.get("location")
        )

        if needs_location and not has_location_in_query and key_context.get("location"):
            additions.append(key_context["location"])

        # 检测查询是否需要偏好上下文
        if key_context.get("preferences"):
            # 当用户问推荐类问题时，补充偏好
            recommend_keywords = ("推荐", "建议", "吃什么", "去哪", "有什么")
            if any(kw in query for kw in recommend_keywords):
                # 只补充第一个偏好，避免查询过长
                additions.append(key_context["preferences"][0])

        if additions:
            augmented = f"{query} {' '.join(additions)}"
            logger.info(
                f"Recall query augmented: '{query}' → '{augmented}' "
                f"(added: {additions})"
            )

        return augmented

    def should_compress(self, history: List[Dict[str, str]]) -> bool:
        """判断是否需要触发阈值压缩。

        当对话轮数超过 compress_threshold_turns 时返回 True。
        1 轮 = user + assistant = 2 条消息。

        Args:
            history: 对话历史列表

        Returns:
            是否需要压缩
        """
        if not history:
            return False
        # 每轮 2 条消息（user + assistant）
        turns = len(history) // 2
        return turns > self.compress_threshold_turns

    async def compress_history_with_threshold(
        self,
        history: List[Dict[str, str]],
        running_summary: str = "",
    ) -> Tuple[List[Dict[str, str]], str]:
        """阈值压缩 — 对话超阈值时自动将旧对话压缩为滚动摘要。

        核心逻辑（参考 LangChain ConversationSummaryMemory + MemGPT 分层记忆）:
            1. 判断对话轮数是否超过阈值
            2. 超过则将旧对话（保留 keep_recent_turns 轮）压缩为摘要
            3. 摘要与现有 running_summary 合并，形成增量滚动摘要
            4. 返回裁剪后的历史（仅保留近期对话）和更新后的摘要

        压缩示例（默认配置 compress_threshold_turns=6, keep_recent_turns=4）:
            历史: [u1, a1, u2, a2, u3, a3, u4, a4, u5, a5, u6, a6, u7, a7]  (7 轮)
            阈值: 6 轮，保留: 4 轮
            → 压缩 [u1,a1 ... u3,a3] 为摘要
            → 返回 [u4,a4, u5,a5, u6,a6, u7,a7] + 合并摘要

        配置:
            阈值和保留轮数可通过 .env 环境变量调整:
            MEMORY_COMPRESS_THRESHOLD_TURNS / MEMORY_KEEP_RECENT_TURNS

        Args:
            history: 完整对话历史
            running_summary: 现有的滚动摘要（来自上一轮）

        Returns:
            (压缩后的历史列表, 更新后的滚动摘要)
        """
        if not history or not self.should_compress(history):
            return history, running_summary

        # 计算需要保留的近期消息数
        keep_count = self.keep_recent_turns * 2  # 每轮 2 条消息
        # 需要压缩的旧消息
        old_messages = history[:-keep_count] if len(history) > keep_count else []
        recent_messages = history[-keep_count:] if len(history) > keep_count else history

        if not old_messages:
            return history, running_summary

        turns_compressed = len(old_messages) // 2
        logger.info(
            f"Threshold compression triggered: history={len(history)} msgs ({len(history)//2} turns), "
            f"compressing {turns_compressed} old turns, keeping {self.keep_recent_turns} recent turns"
        )

        # 压缩旧对话为摘要
        new_summary = await self.compress_messages(old_messages)

        # 与现有摘要合并（增量摘要策略）
        if running_summary and new_summary:
            # 合并旧摘要和新摘要，保持总长度在限制内
            combined = f"{running_summary}\n{new_summary}"
            # 如果合并后过长，重新压缩一次
            if len(combined) > self.max_summary_chars:
                combined = await self._merge_summaries(running_summary, new_summary)
            merged_summary = combined[:self.max_summary_chars]
        else:
            merged_summary = (new_summary or running_summary)[:self.max_summary_chars]

        logger.info(
            f"Threshold compression done: summary_len={len(merged_summary)}, "
            f"history_reduced={len(history)}→{len(recent_messages)} msgs"
        )

        return recent_messages, merged_summary

    async def _merge_summaries(self, old_summary: str, new_summary: str) -> str:
        """合并两个摘要片段，避免摘要无限膨胀。

        当滚动摘要总长度超过 max_summary_chars 时，调用 LLM 将
        旧摘要和新摘要融合为一个更精简的摘要。

        Args:
            old_summary: 之前的滚动摘要
            new_summary: 本轮新产生的摘要

        Returns:
            合并后的摘要（不超过 max_summary_chars）
        """
        prompt = [
            {
                "role": "system",
                "content": (
                    "你是记忆摘要合并器。请将两段对话摘要融合为一段。\n\n"
                    "合并规则：\n"
                    "1. 【对话脉络】按时间顺序合并两段摘要中的用户问题列表，去重保持顺序\n"
                    "2. 【关键事实】合并稳定信息（位置/偏好/身份/未完成事项），去重\n"
                    "3. 如有冲突（如位置变化），保留较新的信息\n\n"
                    "输出格式：\n"
                    "【对话脉络】\n  1. 用户询问了XXX\n  2. ...\n"
                    "【关键事实】\n  - 位置/目的地: ...\n  - 偏好: ...\n\n"
                    "不超过400字，中文输出。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"【旧摘要】\n{old_summary}\n\n"
                    f"【新摘要】\n{new_summary}"
                ),
            },
        ]
        try:
            res = await self.client.chat.completions.create(
                model=self.config.llm_model, messages=prompt, temperature=0.1
            )
            return res.choices[0].message.content.strip()[:self.max_summary_chars]
        except Exception as e:
            logger.error(f"Summary merge failed: {e}")
            # 降级：简单截断旧摘要，保留新摘要
            keep_old = old_summary[: self.max_summary_chars // 2]
            return f"{keep_old}\n{new_summary}"[:self.max_summary_chars]

    def _filter_low_quality_memories(self, memories: List[str]) -> List[str]:
        """过滤低质量记忆。

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
        """分级预算组装上下文。

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
        # 过滤低质量记忆
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
                {
                    "role": "system",
                    "content": (
                        f"【历史摘要】（之前对话的压缩记录，属于当前会话的上下文）:\n"
                        f"{running_summary}\n\n"
                        "注意：当用户询问\"之前问了什么\"、\"第一个问题\"等时，"
                        "请从上方【对话脉络】中查找并如实回答。"
                    ),
                }
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
            new_running_summary = (running_summary + "\n" + old_summary).strip()[:self.max_summary_chars]

        # 重新组装
        final_msgs: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if memory_str:
            final_msgs[0]["content"] += f"\n{memory_str}\n请在聊天中自然运用这些信息。"
        if new_running_summary:
            final_msgs.append(
                {
                    "role": "system",
                    "content": (
                        f"【历史摘要】（之前对话的压缩记录，属于当前会话的上下文）:\n"
                        f"{new_running_summary}\n\n"
                        "注意：当用户询问\"之前问了什么\"、\"第一个问题\"等时，"
                        "请从上方【对话脉络】中查找并如实回答。"
                    ),
                }
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
