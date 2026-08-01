# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Reflection Node — 反思校验节点

从 supervisor_graph.py 的以下方法抽取:
    - _reflection_node()           → run()
    - _deterministic_date_check()  → deterministic_date_check()
    - _reflect_search_response()   → reflect_search_response()
    - _reflect_chat_response()      → reflect_chat_response()
    - _regenerate_with_feedback()  → regenerate_with_feedback()
    - _is_history_query()           → is_history_query()
    - _has_history()                 → has_history()
    - _is_hallucinated_history()     → is_hallucinated_history()
    - _pre_check_chat_response()    → pre_check_chat_response()
    - _post_check_chat_response()   → post_check_chat_response()

职责:
    1. 事实性校验（工具数据 vs 回复一致性）
    2. 搜索类回复反思（无幻觉 + 时效性 + 日期正确性）
    3. 通用闲聊反思（渐进式校验 + retry 重新生成）
    4. 确定性日期校验（正则，无 LLM 调用）
    5. 幻觉兜底检查（防止编造对话历史）
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import TYPE_CHECKING, Any

from nexus.agent.nodes.context import NodeContext
from nexus.config import get_config
from nexus.core.logger import get_logger
from nexus.models.state import SupervisorState
from nexus.observability.langfuse import observe

if TYPE_CHECKING:
    from nexus.agent.nodes.responder_node import ResponderNode

logger = get_logger(__name__)


class ReflectionNode:
    """反思校验节点：对 LLM 输出做事实性、一致性、无幻觉检查。

    通过 NodeContext 依赖注入获取共享服务，不持有 SupervisorGraph 引用。
    通过 responder_node 引用调用 get_system_prompt()（避免循环依赖，
    在 SupervisorGraph.__init__() 中设置）。

    Args:
        ctx: NodeContext 共享依赖容器
    """

    def __init__(self, ctx: NodeContext):
        self._ctx = ctx
        self._responder: ResponderNode | None = None

    def set_responder_node(self, responder: ResponderNode) -> None:
        """设置 ResponderNode 引用，用于 regenerate_with_feedback 调用 get_system_prompt。"""
        self._responder = responder

    # ------------------------------------------------------------------
    # 模式匹配类属性
    # ------------------------------------------------------------------

    # 用户询问对话历史的关键词模式
    _HISTORY_QUERY_PATTERNS = [
        "第一个问题", "第一句话", "第一次问", "刚才问", "之前问",
        "刚才说", "之前说", "上次问", "刚才聊", "之前聊",
        "还记得我", "你还记得", "我说了什么", "我问了什么",
        "我们聊了什么", "对话历史", "聊天记录",
    ]

    # LLM 编造对话历史的可疑模式
    _HALLUCINATED_HISTORY_PATTERNS = [
        "您最初是问", "你最初是问", "您第一次问", "你第一次问",
        "您刚才问的是", "你刚才问的是", "您之前问的是", "你之前问的是",
        "您的第一个问题", "你的第一个问题", "您第一句话", "你第一句话",
    ]

    # ------------------------------------------------------------------
    # 主节点方法
    # ------------------------------------------------------------------

    @observe(name="reflection-node")
    async def run(self, state: SupervisorState) -> dict[str, Any]:
        """反思校验节点：对 LLM 输出做事实性、一致性、无幻觉检查。

        反思策略:
            - 有工具数据时：执行 LLM 反思（CoT 自我批评）
            - 有搜索结果时：执行 LLM 反思
            - 无工具数据时：轻量检查（非空、长度合理）

        可通过 REFLECTION_ENABLED=false 关闭以减少 LLM 调用。

        Args:
            state: 包含 final_response 和 tool_result 的 SupervisorState

        Returns:
            Partial state update，可能修正 final_response
        """
        t0 = perf_counter()
        tool_result = state.get("tool_result", {})
        final_response = state.get("final_response", "")
        user_input = state.get("user_input", "")
        search_context = state.get("search_context", "")

        update: dict[str, Any] = {"metadata": {}}

        # 反思开关 — 关闭时跳过所有 LLM 反思，仅做轻量检查
        if not get_config().llm.reflection_enabled:
            if not final_response or len(final_response.strip()) < 2:
                update["final_response"] = "抱歉，我没有理解你的意思，能再说一次吗？"
                update["metadata"]["reflection_result"] = "fallback_empty"
            else:
                update["metadata"]["reflection_result"] = "disabled_by_config"

            # 即使反思禁用，也要做幻觉兜底检查
            # 防止 LLM 编造对话历史（如"您最初是问..."）
            hallucination_fix = self.post_check_chat_response(state, final_response)
            if hallucination_fix is not None:
                update["final_response"] = hallucination_fix
                update["metadata"]["reflection_result"] = "hallucination_guard"

            latency_ms = round((perf_counter() - t0) * 1000, 2)
            update["metadata"]["reflection_latency_ms"] = latency_ms
            logger.info(f"Reflection skipped (disabled by config): latency={latency_ms}ms")
            return update

        # 搜索类回复也做反思校验
        if not tool_result or not tool_result.get("message"):
            if search_context and state.get("skill_action") == "web_search":
                # 搜索类反思：检查回复是否基于搜索结果，是否有时效性问题
                return await self.reflect_search_response(
                    state, user_input, final_response, search_context, t0
                )

            # 通用闲聊反思 — 对所有非工具类回复做 LLM 质量校验（渐进式校验机制）
            # 不再只做轻量检查，而是走完整的 LLM 反思 + retry 流程
            return await self.reflect_chat_response(
                state, user_input, final_response, t0
            )

        # 有工具数据时，执行 LLM 反思
        tool_message = tool_result.get("message", "")
        tool_data = tool_result.get("data", {})
        tool_name = tool_result.get("tool_name", "")

        reflection_prompt = (
            "你是一个响应质量审查员。请检查助手的回复是否准确、一致、无幻觉。\n\n"
            f"## 用户问题\n{user_input}\n\n"
            f"## 工具返回的真实数据\n"
            f"- 工具名称: {tool_name}\n"
            f"- 结果摘要: {tool_message}\n"
            f"- 详细数据: {json.dumps(tool_data, ensure_ascii=False, default=str)}\n\n"
            f"## 助手回复\n{final_response}\n\n"
            "## 检查标准（逐条分析）\n"
            "1. **事实性**: 回复中的信息是否与工具返回的数据一致？有没有歪曲数据？\n"
            "2. **完整性**: 回复是否包含了用户关心的关键信息？\n"
            "3. **无幻觉**: 回复中是否有工具数据不支持的编造信息？\n"
            "4. **相关性**: 回复是否直接回答了用户的问题？\n\n"
            "请先简要分析，然后输出以下 JSON（只输出 JSON，不要其他内容）:\n"
            '{"valid": true或false, "reason": "简短原因", '
            '"suggested_response": "如果不合格，给出修正后的回复；如果合格则留空"}'
        )

        try:
            response = await self._ctx.chat_model.ainvoke(
                [{"role": "user", "content": reflection_prompt}],
                temperature=0.0,
                max_tokens=500,
            )
            content = (response.content or "").strip()

            # 解析 JSON
            cleaned = content.replace("```json", "").replace("```", "").strip()
            match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if match:
                cleaned = match.group(0)
            result = json.loads(cleaned)

            if result.get("valid") is True:
                logger.info(f"Reflection PASSED: {result.get('reason', '')}")
                update["metadata"]["reflection_result"] = "passed"
                update["metadata"]["reflection_reason"] = result.get("reason", "")
            else:
                # 反思不通过，使用修正后的回复
                suggested = result.get("suggested_response", "").strip()
                if suggested:
                    logger.warning(
                        f"Reflection FAILED: {result.get('reason', '')}, "
                        f"applying corrected response"
                    )
                    update["final_response"] = suggested
                    update["metadata"]["reflection_result"] = "corrected"
                    update["metadata"]["reflection_reason"] = result.get("reason", "")
                    update["metadata"]["original_response"] = final_response[:200]
                else:
                    logger.warning(
                        f"Reflection FAILED but no suggestion: {result.get('reason', '')}"
                    )
                    update["metadata"]["reflection_result"] = "failed_no_suggestion"
                    update["metadata"]["reflection_reason"] = result.get("reason", "")

        except Exception as e:
            logger.error(f"Reflection LLM call failed: {e}")
            update["metadata"]["reflection_result"] = "error"
            update["metadata"]["reflection_error"] = str(e)

        latency_ms = round((perf_counter() - t0) * 1000, 2)
        update["metadata"]["reflection_latency_ms"] = latency_ms
        logger.info(f"Reflection done: latency={latency_ms}ms")

        return update

    # ------------------------------------------------------------------
    # 确定性日期校验
    # ------------------------------------------------------------------

    def deterministic_date_check(
        self, user_input: str, response: str,
    ) -> str | None:
        """确定性日期校验 — 使用正则表达式检测日期错误，无需 LLM 调用。

        检测场景:
            1. 用户问"明天"，但回复中"明天"后面跟着的日期等于今天的日期
            2. 用户问"后天"，但回复中"后天"后面跟着的日期等于今天或明天的日期
            3. 用户问"今天"，但回复中"今天"后面跟着的日期不等于今天的日期

        Returns:
            如果检测到错误，返回修正后的回复；否则返回 None 表示无问题。
        """
        cn_tz = timezone(timedelta(hours=8))
        now_cn = datetime.now(cn_tz)
        today_str = now_cn.strftime("%m月%d日").lstrip("0").replace("月0", "月")
        tomorrow = now_cn + timedelta(days=1)
        tomorrow_str = tomorrow.strftime("%m月%d日").lstrip("0").replace("月0", "月")
        day_after = now_cn + timedelta(days=2)
        day_after_str = day_after.strftime("%m月%d日").lstrip("0").replace("月0", "月")

        # 检测用户是否询问了"明天"或"后天"
        asks_tomorrow = "明天" in user_input or "明日" in user_input
        asks_day_after = "后天" in user_input or "後天" in user_input
        asks_today = "今天" in user_input or "今日" in user_input

        if not (asks_tomorrow or asks_day_after or asks_today):
            return None

        # 提取回复中"明天"后面紧跟的日期（支持 "7月19日" 和 "07月19日" 格式）
        # 匹配模式: "明天" 后面的 50 字符内出现 X月X日
        date_pattern = r"(\d{1,2})月(\d{1,2})日"

        if asks_tomorrow:
            # 找到"明天"后面出现的日期
            for match in re.finditer(r"明天.{0,50}?" + date_pattern, response):
                month, day = int(match.group(1)), int(match.group(2))
                resp_date_str = f"{month}月{day}日"
                if resp_date_str == today_str:
                    # 明天后面跟了今天的日期 → 错误
                    logger.warning(
                        f"Date check FAILED: user asked '明天' but response says "
                        f"'明天{resp_date_str}' (today={today_str}, tomorrow={tomorrow_str})"
                    )
                    # 直接替换错误日期
                    corrected = response.replace(
                        f"明天{resp_date_str}", f"明天{tomorrow_str}"
                    ).replace(
                        f"明天 {resp_date_str}", f"明天 {tomorrow_str}"
                    )
                    # 如果替换后没有变化，尝试更宽泛的替换
                    if corrected == response:
                        corrected = response.replace(resp_date_str, tomorrow_str, 1)
                    return corrected

        if asks_day_after:
            for match in re.finditer(r"后天.{0,50}?" + date_pattern, response):
                month, day = int(match.group(1)), int(match.group(2))
                resp_date_str = f"{month}月{day}日"
                if resp_date_str in (today_str, tomorrow_str):
                    logger.warning(
                        f"Date check FAILED: user asked '后天' but response says "
                        f"'后天{resp_date_str}' (today={today_str}, day_after={day_after_str})"
                    )
                    corrected = response.replace(resp_date_str, day_after_str, 1)
                    return corrected

        return None

    # ------------------------------------------------------------------
    # 搜索类回复反思
    # ------------------------------------------------------------------

    async def reflect_search_response(
        self, state: SupervisorState, user_input: str,
        final_response: str, search_context: str, t0: float,
    ) -> dict[str, Any]:
        """搜索类回复反思：检查回复是否基于搜索结果，是否正确传达时效性。

        检查项:
            1. 回复中的信息是否都能在搜索结果中找到对应（无幻觉）
            2. 回复是否正确传达了搜索结果的时效性
            3. 回复是否添加了搜索结果中不存在的具体数据（如温度、时间等）
        """
        update: dict[str, Any] = {"metadata": {}}

        # 确定性日期校验（正则，无 LLM 调用，即时完成）
        # 如果检测到日期错误，直接修正并跳过 LLM 反思，大幅减少延迟
        date_fix = self.deterministic_date_check(user_input, final_response)
        if date_fix is not None:
            update["final_response"] = date_fix
            update["metadata"]["reflection_result"] = "date_corrected_deterministic"
            update["metadata"]["reflection_reason"] = "确定性日期校验检测到日期错误，已自动修正"
            update["metadata"]["original_response"] = final_response[:200]
            latency_ms = round((perf_counter() - t0) * 1000, 2)
            update["metadata"]["reflection_latency_ms"] = latency_ms
            logger.info(f"Search reflection: deterministic date check corrected, latency={latency_ms}ms")
            return update

        # 注入当前日期到反思 prompt，防止日期混淆
        cn_tz = timezone(timedelta(hours=8))
        now_cn = datetime.now(cn_tz)
        current_date_str = now_cn.strftime("%Y年%m月%d日 %H:%M")

        # 计算今天/明天的确切日期，注入反思 prompt
        today_str = now_cn.strftime("%m月%d日").lstrip("0").replace("月0", "月")
        tomorrow = now_cn + timedelta(days=1)
        tomorrow_str = tomorrow.strftime("%m月%d日").lstrip("0").replace("月0", "月")

        reflection_prompt = (
            "你是一个响应质量审查员。请检查助手的回复是否准确基于搜索结果。\n\n"
            f"## 当前准确时间\n{current_date_str}\n\n"
            f"## 日期对照（绝对准确）\n- 今天: {today_str}\n- 明天: {tomorrow_str}\n\n"
            f"## 用户问题\n{user_input}\n\n"
            f"## 搜索结果（真实数据）\n{search_context[:2000]}\n\n"
            f"## 助手回复\n{final_response}\n\n"
            "## 检查标准（逐条分析）\n"
            "1. **无幻觉**: 回复中的每个具体数据（温度、时间、风速等）是否都能在搜索结果中找到？\n"
            "2. **日期正确性（极其重要）**: 用户问'明天'时，请根据上方的日期对照验证：\n"
            f"   - 今天是 {today_str}，明天是 {tomorrow_str}\n"
            "   - 如果助手回复中的日期与当前日期相同却声称是'明天'，则判定为不合格\n"
            "   - 如果助手回复中的日期是正确的明天日期，则判定为合格\n"
            "3. **时效性**: 搜索结果开头标注了当前时间。回复中的数据时间是否与当前时间差距过大？\n"
            "   - 如果搜索结果数据时间距当前超过3小时，回复是否提到了'信息可能不够及时'？\n"
            "4. **无编造**: 回复是否添加了搜索结果中没有的具体信息（如来源网站名、额外建议等）？\n"
            "5. **相关性**: 回复是否直接回答了用户的问题？\n\n"
            "请先简要分析，然后输出以下 JSON（只输出 JSON，不要其他内容）:\n"
            '{"valid": true或false, "reason": "简短原因", '
            '"suggested_response": "如果不合格，给出修正后的回复；如果合格则留空"}'
        )

        try:
            response = await self._ctx.chat_model.ainvoke(
                [{"role": "user", "content": reflection_prompt}],
                temperature=0.0,
                max_tokens=500,
            )
            content = (response.content or "").strip()

            cleaned = content.replace("```json", "").replace("```", "").strip()
            match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if match:
                cleaned = match.group(0)
            result = json.loads(cleaned)

            if result.get("valid") is True:
                logger.info(f"Search reflection PASSED: {result.get('reason', '')}")
                update["metadata"]["reflection_result"] = "search_passed"
                update["metadata"]["reflection_reason"] = result.get("reason", "")
            else:
                suggested = result.get("suggested_response", "").strip()
                if suggested:
                    logger.warning(
                        f"Search reflection FAILED: {result.get('reason', '')}, "
                        f"applying corrected response"
                    )
                    update["final_response"] = suggested
                    update["metadata"]["reflection_result"] = "search_corrected"
                    update["metadata"]["reflection_reason"] = result.get("reason", "")
                    update["metadata"]["original_response"] = final_response[:200]
                else:
                    logger.warning(
                        f"Search reflection FAILED but no suggestion: {result.get('reason', '')}"
                    )
                    update["metadata"]["reflection_result"] = "search_failed_no_suggestion"
                    update["metadata"]["reflection_reason"] = result.get("reason", "")

        except Exception as e:
            logger.error(f"Search reflection LLM call failed: {e}")
            update["metadata"]["reflection_result"] = "search_error"
            update["metadata"]["reflection_error"] = str(e)

        latency_ms = round((perf_counter() - t0) * 1000, 2)
        update["metadata"]["reflection_latency_ms"] = latency_ms
        logger.info(f"Search reflection done: latency={latency_ms}ms")

        return update

    # ------------------------------------------------------------------
    # 通用闲聊反思
    # ------------------------------------------------------------------

    async def reflect_chat_response(
        self, state: SupervisorState, user_input: str,
        final_response: str, t0: float,
    ) -> dict[str, Any]:
        """通用闲聊反思：对所有非工具类回复做 LLM 质量校验。

        反思 prompt 注入完整对话历史，防止反思 LLM 误判"编造对话历史"，
        当用户询问对话历史时，反思 LLM 能对照实际历史记录判断。

        渐进式校验机制（Loop Engineering）:
            1. 首次反思：检查回复的相关性、准确性、一致性、完整性
            2. 如果反思不通过且有修正建议 → 直接采用修正建议
            3. 如果反思不通过但无修正建议 → 带反馈重新生成（最多 1 次重试）
            4. 重试后再次反思，无论结果如何都返回（防止无限循环）

        检查项:
            - 相关性：回复是否直接回答了用户的问题
            - 准确性：回复中是否有明显的 factual error
            - 一致性：回复是否自相矛盾
            - 完整性：回复是否过于简短或遗漏关键信息
            - 无幻觉：回复是否编造了不存在的信息
        """
        update: dict[str, Any] = {"metadata": {}}

        # 注入当前时间，防止时间相关的幻觉
        cn_tz = timezone(timedelta(hours=8))
        now_cn = datetime.now(cn_tz)
        current_date_str = now_cn.strftime("%Y年%m月%d日 %H:%M %A")

        # 如果回复为空或极短，直接返回兜底
        if not final_response or len(final_response.strip()) < 2:
            update["final_response"] = "抱歉，我没有理解你的意思，能再说一次吗？"
            update["metadata"]["reflection_result"] = "chat_fallback_empty"
            latency_ms = round((perf_counter() - t0) * 1000, 2)
            update["metadata"]["reflection_latency_ms"] = latency_ms
            return update

        # 提取对话历史，注入反思 prompt，防止反思 LLM 误判"编造对话历史"
        history = state.get("history", [])
        history_str = ""
        if history:
            history_lines = []
            for msg in history:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "user":
                    history_lines.append(f"用户: {content}")
                elif role == "assistant":
                    history_lines.append(f"助手: {content}")
            history_str = "\n".join(history_lines)
        else:
            history_str = "（无历史记录，这是新对话的第一轮）"

        reflection_prompt = (
            "你是一个响应质量审查员。请检查助手的回复是否准确、相关、无幻觉。\n\n"
            f"## 当前准确时间\n{current_date_str}\n\n"
            f"## 当前对话历史（真实记录，用于判断助手是否编造历史）\n{history_str}\n\n"
            f"## 用户问题\n{user_input}\n\n"
            f"## 助手回复\n{final_response}\n\n"
            "## 检查标准（逐条分析）\n"
            "1. **相关性**: 回复是否直接回答了用户的问题？有没有答非所问？\n"
            "2. **准确性**: 回复中是否有明显的 factual error？时间、地点、数据是否正确？\n"
            "3. **一致性**: 回复是否自相矛盾？前后说法是否一致？\n"
            "4. **完整性**: 回复是否过于简短？是否遗漏了用户关心的关键信息？\n"
            "5. **无幻觉**: 回复是否编造了不存在的信息？是否捏造了数据、事件或事实？\n"
            "   ⚠️ **对话历史判断（极其重要）**: 当用户询问对话历史（如'我之前问了什么'、'你还记得吗'）时：\n"
            "   - 请对照上方'当前对话历史'中的真实记录来验证助手回复\n"
            "   - 如果助手回复中提到的历史问题能在对话历史中找到对应，则**不算编造**，判定为合格\n"
            "   - 只有当助手回复中提到的历史在对话历史中**完全找不到对应**时，才判定为编造\n"
            "   - 如果对话历史为空（新对话），但助手声称用户之前问过某些问题，才判定为编造\n\n"
            "请先简要分析，然后输出以下 JSON（只输出 JSON，不要其他内容）:\n"
            '{"valid": true或false, "reason": "简短原因", '
            '"suggested_response": "如果不合格，给出修正后的回复；如果合格则留空"}'
        )

        try:
            response = await self._ctx.chat_model.ainvoke(
                [{"role": "user", "content": reflection_prompt}],
                temperature=0.0,
                max_tokens=500,
            )
            content = (response.content or "").strip()

            # 解析 JSON
            cleaned = content.replace("```json", "").replace("```", "").strip()
            match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if match:
                cleaned = match.group(0)
            result = json.loads(cleaned)

            if result.get("valid") is True:
                logger.info(f"Chat reflection PASSED: {result.get('reason', '')}")
                update["metadata"]["reflection_result"] = "chat_passed"
                update["metadata"]["reflection_reason"] = result.get("reason", "")
            else:
                suggested = result.get("suggested_response", "").strip()
                if suggested:
                    logger.warning(
                        f"Chat reflection FAILED: {result.get('reason', '')}, "
                        f"applying corrected response"
                    )
                    update["final_response"] = suggested
                    update["metadata"]["reflection_result"] = "chat_corrected"
                    update["metadata"]["reflection_reason"] = result.get("reason", "")
                    update["metadata"]["original_response"] = final_response[:200]
                else:
                    # 反思不通过但没有修正建议 → 带反馈重新生成（最多 1 次）
                    logger.warning(
                        f"Chat reflection FAILED, no suggestion, retrying with feedback: "
                        f"{result.get('reason', '')}"
                    )
                    retry_response = await self.regenerate_with_feedback(
                        state, user_input, final_response, result.get("reason", "")
                    )
                    if retry_response and retry_response != final_response:
                        update["final_response"] = retry_response
                        update["metadata"]["reflection_result"] = "chat_retried"
                        update["metadata"]["reflection_reason"] = result.get("reason", "")
                        update["metadata"]["original_response"] = final_response[:200]
                    else:
                        update["metadata"]["reflection_result"] = "chat_failed_no_suggestion"
                        update["metadata"]["reflection_reason"] = result.get("reason", "")

        except Exception as e:
            logger.error(f"Chat reflection LLM call failed: {e}")
            update["metadata"]["reflection_result"] = "chat_error"
            update["metadata"]["reflection_error"] = str(e)

        latency_ms = round((perf_counter() - t0) * 1000, 2)
        update["metadata"]["reflection_latency_ms"] = latency_ms
        logger.info(f"Chat reflection done: latency={latency_ms}ms")

        return update

    # ------------------------------------------------------------------
    # 带反馈重新生成
    # ------------------------------------------------------------------

    async def regenerate_with_feedback(
        self, state: SupervisorState, user_input: str,
        original_response: str, feedback: str,
    ) -> str | None:
        """带反思反馈重新生成回复（渐进式校验的 retry 环节）。

        使用压缩后的历史，保存滚动摘要。

        Args:
            state: 当前状态
            user_input: 用户原始输入
            original_response: 首次生成的（有问题的）回复
            feedback: 反思反馈的原因

        Returns:
            重新生成的回复，或 None 表示重试失败
        """
        ctx = self._ctx

        # 获取系统提示词（委托给 ResponderNode）
        system_msg = ""
        if self._responder is not None:
            system_msg = self._responder.get_system_prompt(state)
        search_ctx = "" if state.get("skill_action") == "web_search" else state.get("search_context", "")

        # 使用压缩后的历史
        history = state.get("_compressed_history", state.get("history", []))

        msgs, new_summary = await ctx.responder.compressor.build_context(
            system_prompt=system_msg,
            user_input=user_input,
            history=history,
            running_summary=state.get("running_summary", ""),
            memory_str=state.get("memory_str", ""),
            search_ctx=search_ctx,
        )

        # 保存滚动摘要
        if new_summary and new_summary != state.get("running_summary", ""):
            state["running_summary"] = new_summary

        # 在对话末尾添加反思反馈，引导 LLM 修正
        msgs.append({
            "role": "assistant",
            "content": original_response,
        })
        msgs.append({
            "role": "user",
            "content": (
                f"【系统校验反馈】你上面的回复存在问题：{feedback}\n"
                "请基于用户最初的问题重新给出一个更准确、更相关的回复。"
                "只输出修正后的回复内容，不要解释。"
            ),
        })

        try:
            response = await ctx.chat_model.ainvoke(
                msgs,
                temperature=0.5,
                max_tokens=get_config().llm.max_tokens,
            )
            result = (response.content or "").strip()
            logger.info(f"Regeneration with feedback done, len={len(result)}")
            return result
        except Exception as e:
            logger.error(f"Regeneration with feedback failed: {e}")
            return None

    # ------------------------------------------------------------------
    # 闲聊预校验 & 幻觉兜底
    # ------------------------------------------------------------------

    def is_history_query(self, user_input: str) -> bool:
        """检测用户是否在询问当前对话的历史记录。"""
        return any(p in user_input for p in self._HISTORY_QUERY_PATTERNS)

    def has_history(self, state: SupervisorState) -> bool:
        """检查当前对话是否有历史记录（排除当前这一轮）。

        即使对话被阈值压缩，只要 running_summary 存在，
        就说明之前有对话历史（只是被折叠为摘要了）。
        """
        history = state.get("history", [])
        # history 中每轮包含 user + assistant 两条，至少 2 条才算有历史
        if bool(history) and len(history) >= 2:
            return True
        # 如果有滚动摘要，说明之前有对话（被压缩了）
        running_summary = state.get("running_summary", "")
        if running_summary and len(running_summary.strip()) > 0:
            return True
        return False

    def is_hallucinated_history(self, response: str) -> bool:
        """检测 LLM 回复是否包含编造的对话历史。"""
        return any(p in response for p in self._HALLUCINATED_HISTORY_PATTERNS)

    def pre_check_chat_response(self, state: SupervisorState) -> str | None:
        """闲聊预校验 — 在调用 LLM 之前拦截明显的问题。

        只有在「既无对话历史」且「无滚动摘要」时才判定为新对话。
        如果有滚动摘要（对话被压缩了），不拦截，让 LLM 基于摘要回答。

        检查场景:
            1. 用户询问对话历史，但当前对话完全无历史且无摘要
               → 直接返回"这是新对话"，不交给 LLM 编造

        Returns:
            如果拦截成功，返回替代回复文本；否则返回 None 表示需要继续调用 LLM。
        """
        user_input = state.get("user_input", "")

        # 场景 1: 用户问对话历史，但当前对话完全没有历史（包括无摘要）
        if self.is_history_query(user_input) and not self.has_history(state):
            logger.info(
                f"Pre-check intercepted: history query with empty history, "
                f"user_input='{user_input[:50]}'"
            )
            return "这是一个新的对话，我们还没有之前的交流记录。请问有什么可以帮您的？"

        return None

    def post_check_chat_response(self, state: SupervisorState, response: str) -> str | None:
        """闲聊后校验 — 在 LLM 回复返回后、呈现给用户前检查。

        只有在「无历史」且「LLM 编造了历史模式」时才判定为幻觉。
        如果有对话历史，不在此处拦截（交给 LLM 反思校验判断）。

        检查场景:
            1. 当前对话无历史，但 LLM 回复中出现了"您最初是问"等编造历史的模式
               → 覆盖为安全回复

        Returns:
            如果检测到问题，返回修正后的回复；否则返回 None 表示原回复可用。
        """
        user_input = state.get("user_input", "")

        # 场景 1: 无历史但 LLM 编造了对话历史
        # 只有在确实没有历史的情况下，才检查是否编造了历史
        # 如果有对话历史，助手引用历史是合理的，不在此处拦截
        if (not self.has_history(state)
                and self.is_hallucinated_history(response)):
            logger.warning(
                f"Post-check intercepted: hallucinated history detected (no history in state), "
                f"user_input='{user_input[:50]}', response='{response[:80]}'"
            )
            return "这是一个新的对话，我们还没有之前的交流记录。请问有什么可以帮您的？"

        return None
