# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Responder Node — 回复生成节点

职责：汇总专家输出，按分支选择回复策略（澄清/工具合成/LLM闲聊），
构建System Prompt并注入画像/记忆/习惯/位置/关键上下文，
执行闲聊预校验与后校验。
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import TYPE_CHECKING, Any

from nexus.agent.nodes.context import NodeContext
from nexus.config import get_config
from nexus.core.logger import get_logger
from nexus.models.state import SupervisorState
from nexus.observability.langfuse import observe, update_current_span
from nexus.observability.metrics import LLM_CALLS, LLM_LATENCY

if TYPE_CHECKING:
    from nexus.agent.nodes.reflection_node import ReflectionNode

logger = get_logger(__name__)


class ResponderNode:
    """Responder 节点：汇总专家输出生成最终回复。

    通过 NodeContext 依赖注入获取共享服务，不持有 SupervisorGraph 引用。
    通过 reflection_node 引用调用闲聊预校验/后校验（避免循环依赖，
    在 SupervisorGraph.__init__() 中设置）。

    Args:
        ctx: NodeContext 共享依赖容器
    """

    def __init__(self, ctx: NodeContext):
        self._ctx = ctx
        self._reflection: ReflectionNode | None = None

    def set_reflection_node(self, reflection: ReflectionNode) -> None:
        """设置 ReflectionNode 引用，用于闲聊预校验/后校验。"""
        self._reflection = reflection

    # ------------------------------------------------------------------
    # 主节点方法
    # ------------------------------------------------------------------

    @observe(name="responder-node")
    async def run(self, state: SupervisorState) -> dict[str, Any]:
        """Responder 节点：按分支选择回复策略生成最终回复。

        分支策略:
            A: 需要澄清 → 直接返回 clarification_prompt
            B1: 搜索类技能 → LLM 用 search 提示词生成
            B2: 工具返回结构化数据 → Tool→LLM 合成
            B3: 简单车控指令 → 聚合所有专家回复
            B5: 复合查询混合 → 车控回复 + LLM 合成搜索结果拼接
            C: LLM 闲聊兜底

        增强特性:
            - 分支 B 优化: 当工具返回结构化数据时，将结果回传 LLM 做自然语言合成
            - 不再直接返回原始工具消息，而是经过 LLM 解读后输出
            - 返回 running_summary 确保 LangGraph 持久化滚动摘要
            - 使用压缩后的历史作为 history_update 的基础
        """
        t0 = perf_counter()
        full_response = ""

        # 分支 A: 需要澄清
        if state.get("need_clarification") and state.get("clarification_prompt"):
            full_response = state["clarification_prompt"]

        # 分支 B: 专家已处理
        elif state.get("skill_handled"):
            # B1: 搜索类技能用专用 search 提示词
            if state.get("skill_action") == "web_search" and state.get("search_context"):
                full_response = await self.generate_llm_response(state)

            # B2: 工具返回了结构化数据 → Tool→LLM 合成
            elif state.get("tool_result") and state.get("tool_result", {}).get("data"):
                full_response = await self.synthesize_tool_response(state)

            # B3: 简单车控指令，直接使用工具返回的自然语言消息
            else:
                expert_results = state.get("expert_results", [])
                # 多专家/多动作并行时汇总所有回复，避免丢失其他专家的执行结果
                # 按 expert 分组聚合，同一专家的多条结果合并为一段
                expert_replies: dict[str, list[str]] = {}
                for er in expert_results:
                    if er.get("handled") and er.get("reply"):
                        expert_name = er.get("expert", "unknown")
                        expert_replies.setdefault(expert_name, []).append(er["reply"])
                # 每个专家的回复合并为一段，多专家之间用换行分隔
                replies = []
                for expert_name, parts in expert_replies.items():
                    if len(parts) == 1:
                        replies.append(parts[0])
                    else:
                        # 同一专家多条结果合并
                        replies.append("；".join(parts))
                full_response = "\n".join(replies) if replies else ""

                # 空回复兜底 — 专家标记 handled=True 但回复为空时，返回标准化提示
                if not full_response:
                    logger.warning("Responder B3: skill_handled=True but all replies empty, applying fallback")
                    full_response = "指令已执行，但未返回详细信息。"

            # B5: 复合查询混合场景 — 车控指令 + 搜索/POI 结果
            # 当车控专家已执行指令（B3），同时生活专家返回了搜索结果时，
            # 需要额外调用 LLM 合成搜索结果，并与车控回复拼接。
            # 场景: "帮我查酒旅服务，推荐美食，打开车窗"
            # → vehicle 专家回复"已打开车窗"
            # → LLM 合成搜索结果"为您找到以下酒店..."
            # → 两者拼接为完整回复
            if (
                full_response
                and state.get("search_context")
                and "lifestyle" in state.get("active_experts", [])
                and state.get("skill_action") != "web_search"  # 避免与 B1 重复
            ):
                try:
                    original_action = state.get("skill_action", "")
                    state["skill_action"] = "web_search"
                    search_response = await self.generate_llm_response(state)
                    state["skill_action"] = original_action
                    if search_response and search_response.strip():
                        full_response = f"{full_response}\n{search_response}"
                        logger.info(
                            f"Compound search synthesis: search_len={len(search_response)}, "
                            f"total_len={len(full_response)}"
                        )
                except Exception as e:
                    logger.error(f"Compound search synthesis failed: {e}")

        # 分支 C: LLM 闲聊兜底
        else:
            full_response = await self.generate_llm_response(state)

        # 更新历史 — 新的一轮追加到压缩后的历史（如果进行了阈值压缩）
        # 这样 SessionStore 保存的就是压缩后的历史 + 新轮次
        history_update = [
            {"role": "user", "content": state.get("user_input", "")},
            {"role": "assistant", "content": full_response},
        ]

        latency_ms = round((perf_counter() - t0) * 1000, 2)
        logger.info(f"Responder done: response_len={len(full_response)}, latency={latency_ms}ms")

        # 返回 running_summary 确保 LangGraph 持久化
        # generate_llm_response / synthesize_tool_response 已将新摘要写入 state
        result: dict[str, Any] = {
            "final_response": full_response,
            "history": history_update,
            "metadata": {"responder_latency_ms": latency_ms},
        }
        # 如果有压缩后的历史，返回它以便 LangGraph 更新 state
        compressed = state.get("_compressed_history")
        if compressed is not None:
            result["_compressed_history"] = compressed + history_update
        # 返回更新后的滚动摘要
        running_summary = state.get("running_summary", "")
        if running_summary:
            result["running_summary"] = running_summary

        return result

    # ------------------------------------------------------------------
    # Tool→LLM 合成
    # ------------------------------------------------------------------

    @observe(name="llm-tool-synthesis", as_type="generation")
    async def synthesize_tool_response(self, state: SupervisorState) -> str:
        """Tool→LLM 合成：将工具调用结果回传 LLM，生成自然语言回复。

        核心思路（CoT 模式）:
            1. 工具返回的结构化数据作为事实依据
            2. LLM 根据用户问题 + 工具结果，推理生成自然回复
            3. 确保回复基于工具真实数据，不编造额外信息

        安全约束:
            - 工具返回失败/未知结果时跳过 LLM 合成，直接返回原始消息
            - 强化提示词，明确禁止添加天气/新闻等工具结果外的信息
            - 不注入记忆和习惯，避免 LLM 基于历史记忆编造信息

        Args:
            state: 包含 tool_result、user_input 等的 SupervisorState

        Returns:
            LLM 生成的自然语言回复，或工具原始消息
        """
        ctx = self._ctx
        tool_result = state.get("tool_result", {})
        tool_message = tool_result.get("message", "")
        tool_data = tool_result.get("data", {})
        tool_name = tool_result.get("tool_name", "")

        user_input = state.get("user_input", "")

        # 工具返回失败/未知结果时，跳过 LLM 合成，直接返回原始消息
        # 避免 LLM 在"未知位置"基础上编造天气、地址等虚假信息
        failure_indicators = ("未知", "不可用", "失败", "错误", "无法", "不支持")
        if any(indicator in tool_message for indicator in failure_indicators):
            logger.info(
                f"Tool synthesis SKIPPED (failure detected): tool={tool_name}, "
                f"message={tool_message[:80]}"
            )
            return tool_message

        # 快速路径: 短工具消息已是自然语言，无需 LLM 合成
        # 场景: 位置查询返回 "您当前位于北京市。" — LLM 合成只改几个字却耗时 10s+
        # 阈值 50 字符: 车控/导航/时间的工具消息通常 < 50 字且已是完整句子
        _FAST_SYNTHESIS_MAX_LEN = 50
        if len(tool_message.strip()) <= _FAST_SYNTHESIS_MAX_LEN:
            logger.info(
                f"Tool synthesis FAST-SKIP (short message): tool={tool_name}, "
                f"len={len(tool_message)}, message={tool_message[:80]}"
            )
            return tool_message

        # 构建包含工具结果的系统提示
        # 针对导航类工具增加专门约束，防止编造路线/路况/距离信息
        navigation_constraint = ""
        if "nav" in tool_name.lower() or "navigation" in tool_name.lower():
            navigation_constraint = (
                "\n7. **导航类工具特殊约束（极其重要）**:\n"
                "   - 工具只返回了目的地坐标和名称，**没有路线规划、路况、距离、预计时间等信息**\n"
                "   - **绝对禁止编造**具体路线（如'沿XX路直行'）、路况（如'畅通'）、"
                "距离（如'约5公里'）、预计时间（如'约15分钟'）\n"
                "   - 只需告知用户已开始导航到目的地，并给出目的地名称和坐标即可\n"
                "   - 不要描述沿途 landmarks 或道路名称，除非工具结果中明确包含\n"
            )

        system_msg = (
            "你是车载语音助手小千。你刚刚通过工具获取了真实数据，"
            "请基于以下工具返回的结果回答用户问题。\n\n"
            f"## 工具调用结果\n"
            f"- 工具名称: {tool_name}\n"
            f"- 结果摘要: {tool_message}\n"
            f"- 结构化数据: {json.dumps(tool_data, ensure_ascii=False, default=str)}\n\n"
            "## 回答要求（严格遵守）\n"
            "1. **只能基于工具返回的数据回答**，绝对禁止添加任何工具结果中没有的信息\n"
            "2. **禁止添加**天气、新闻、时事、推荐、建议等工具结果外的内容\n"
            "3. **禁止使用记忆或历史对话中的信息**来补充工具结果\n"
            "4. 用自然口语化的方式转述工具结果，像在跟用户聊天一样\n"
            "5. 回答简洁明了，直接给出用户关心的核心信息\n"
            "6. 如果工具结果已经是一句完整的话，可以自然地转述即可"
            f"{navigation_constraint}\n"
        )

        # 不注入记忆和习惯，避免 LLM 基于历史记忆编造信息

        # 使用压缩后的历史（如果 supervisor 节点执行了阈值压缩）
        history = state.get("_compressed_history", state.get("history", []))

        # 构建对话上下文
        msgs, new_summary = await ctx.responder.compressor.build_context(
            system_prompt=system_msg,
            user_input=user_input,
            history=history,
            running_summary=state.get("running_summary", ""),
            memory_str="",  # 不注入记忆
            search_ctx="",
        )

        # 保存更新后的滚动摘要到 state
        if new_summary and new_summary != state.get("running_summary", ""):
            state["running_summary"] = new_summary

        try:
            _llm_t0 = perf_counter()
            response = await ctx.chat_model.ainvoke(
                msgs,
                temperature=0.3,  # 低温度确保事实准确性
                max_tokens=get_config().llm.max_tokens,
            )
            _llm_latency = (perf_counter() - _llm_t0) * 1000
            LLM_CALLS.labels(model=get_config().llm.llm_model, status="success").inc()
            LLM_LATENCY.observe(_llm_latency / 1000)
            synthesized = (response.content or "").strip()
            # Langfuse: 记录 LLM 模型名和 Token 用量
            _usage = getattr(response, "usage_metadata", None)
            update_current_span(
                metadata={
                    "model": get_config().llm.llm_model,
                    "temperature": 0.3,
                    "token_input": getattr(_usage, "input_tokens", None) if _usage else None,
                    "token_output": getattr(_usage, "output_tokens", None) if _usage else None,
                    "latency_ms": round(_llm_latency, 2),
                }
            )
            logger.info(
                f"Tool synthesis done: tool={tool_name}, "
                f"raw_len={len(tool_message)}, synth_len={len(synthesized)}, "
                f"llm_latency={_llm_latency:.0f}ms"
            )
            return synthesized
        except Exception as e:
            LLM_CALLS.labels(model=get_config().llm.llm_model, status="error").inc()
            logger.error(f"Tool response synthesis failed: {e}, falling back to raw message")
            return tool_message  # 降级：返回原始工具消息

    # ------------------------------------------------------------------
    # LLM 闲聊生成（非流式 + 流式）
    # ------------------------------------------------------------------

    @observe(name="llm-chat-generation", as_type="generation")
    async def generate_llm_response(self, state: SupervisorState) -> str:
        """调用 LLM 生成回复（非流式）。

        特性:
            - 使用压缩后的历史（如果 _supervisor_node 执行了阈值压缩）
            - 将 build_context 返回的 new_summary 保存回 state，确保滚动摘要跨轮次持久化
            - 预校验和后校验，防止编造对话历史
        """
        ctx = self._ctx

        # 预校验 — 拦截明显的问题，不浪费 LLM 调用
        pre_check = None
        if self._reflection is not None:
            pre_check = self._reflection.pre_check_chat_response(state)
        if pre_check is not None:
            return pre_check

        system_msg = self.get_system_prompt(state)

        # 搜索类技能不需要重复传入 search_ctx（已在 system_msg 中）
        search_ctx = "" if state.get("skill_action") == "web_search" else state.get("search_context", "")

        # 使用压缩后的历史（如果 supervisor 节点执行了阈值压缩）
        history = state.get("_compressed_history", state.get("history", []))

        msgs, new_summary = await ctx.responder.compressor.build_context(
            system_prompt=system_msg,
            user_input=state.get("user_input", ""),
            history=history,
            running_summary=state.get("running_summary", ""),
            memory_str=state.get("memory_str", ""),
            search_ctx=search_ctx,
        )

        # 保存更新后的滚动摘要到 state
        if new_summary and new_summary != state.get("running_summary", ""):
            state["running_summary"] = new_summary

        try:
            _llm_t0 = perf_counter()
            response = await ctx.chat_model.ainvoke(
                msgs,
                temperature=0.7,
                max_tokens=get_config().llm.max_tokens,
            )
            _llm_latency = (perf_counter() - _llm_t0) * 1000
            LLM_CALLS.labels(model=get_config().llm.llm_model, status="success").inc()
            LLM_LATENCY.observe(_llm_latency / 1000)
            result = (response.content or "").strip()
            # Langfuse: 记录 LLM 模型名和 Token 用量
            _usage = getattr(response, "usage_metadata", None)
            update_current_span(
                metadata={
                    "model": get_config().llm.llm_model,
                    "temperature": 0.7,
                    "token_input": getattr(_usage, "input_tokens", None) if _usage else None,
                    "token_output": getattr(_usage, "output_tokens", None) if _usage else None,
                    "latency_ms": round(_llm_latency, 2),
                }
            )

            # 后校验 — 检测 LLM 是否编造了对话历史
            post_check = None
            if self._reflection is not None:
                post_check = self._reflection.post_check_chat_response(state, result)
            if post_check is not None:
                return post_check

            return result
        except Exception as e:
            LLM_CALLS.labels(model=get_config().llm.llm_model, status="error").inc()
            logger.error(f"LLM response failed: {e}")
            # 搜索类回复 LLM 超时/失败时，直接返回搜索结果作为兜底
            # 避免用户等待 60 秒后只收到"我遇到了一些问题"
            search_ctx = state.get("search_context", "")
            if search_ctx:
                logger.info("LLM failed, returning raw search results as fallback")
                return f"根据搜索结果：\n{search_ctx[:800]}"
            return "抱歉，AI 服务暂时繁忙，请稍后再试。"

    async def stream_llm_response(self, state: SupervisorState) -> AsyncGenerator[str, None]:
        """流式调用 LLM 生成回复。

        使用压缩后的历史，保存滚动摘要。
        增加预校验，如果预校验拦截则直接返回替代回复。
        """
        ctx = self._ctx

        # 预校验 — 拦截明显的问题，不浪费 LLM 调用
        pre_check = None
        if self._reflection is not None:
            pre_check = self._reflection.pre_check_chat_response(state)
        if pre_check is not None:
            yield pre_check
            return

        system_msg = self.get_system_prompt(state)

        # 搜索类技能不需要重复传入 search_ctx（已在 system_msg 中）
        search_ctx = "" if state.get("skill_action") == "web_search" else state.get("search_context", "")

        # 使用压缩后的历史
        history = state.get("_compressed_history", state.get("history", []))

        msgs, new_summary = await ctx.responder.compressor.build_context(
            system_prompt=system_msg,
            user_input=state.get("user_input", ""),
            history=history,
            running_summary=state.get("running_summary", ""),
            memory_str=state.get("memory_str", ""),
            search_ctx=search_ctx,
        )

        # 保存滚动摘要
        if new_summary and new_summary != state.get("running_summary", ""):
            state["running_summary"] = new_summary

        try:
            async for chunk in ctx.chat_model.astream(
                msgs,
                temperature=0.7,
                max_tokens=get_config().llm.max_tokens,
            ):
                if chunk.content:
                    yield chunk.content
        except Exception as e:
            logger.error(f"LLM streaming failed: {e}")
            # 搜索类回复 LLM 超时/失败时，返回搜索结果作为兜底
            search_ctx = state.get("search_context", "")
            if search_ctx:
                logger.info("LLM stream failed, returning raw search results as fallback")
                yield f"根据搜索结果：\n{search_ctx[:800]}"
            else:
                yield "抱歉，AI 服务暂时繁忙，请稍后再试。"

    # ------------------------------------------------------------------
    # System Prompt 构建
    # ------------------------------------------------------------------

    def get_system_prompt(self, state: SupervisorState) -> str:
        """根据技能类型选择合适的系统提示词，注入用户画像和记忆。

        增强特性:
            - 注入 key_context（从短期对话历史提取的关键信息：位置/偏好/身份）
            - 注入 user_habits（用户习惯，从 MySQL 加载）
            - 注入 user_profile（用户画像，从 Neo4j 加载）
            - 动态选择 prompt 模板（chat / search / vehicle）
            - 搜索类提示词注入位置状态，无位置时禁止编造地址
            - 闲聊提示词注入位置状态，避免 LLM 基于记忆编造位置
        """
        ctx = self._ctx

        # 获取当前位置状态
        location_status = self.get_location_status(state)

        # 注入当前东八区时间，让 LLM 能正确回答时间相关问题
        # 同时计算今天/明天/后天的日期，注入搜索提示词防止日期混淆
        cn_tz = timezone(timedelta(hours=8))
        now_cn = datetime.now(cn_tz)
        weekday_map = {"Monday": "星期一", "Tuesday": "星期二", "Wednesday": "星期三",
                        "Thursday": "星期四", "Friday": "星期五", "Saturday": "星期六",
                        "Sunday": "星期日"}
        weekday_cn = weekday_map.get(now_cn.strftime("%A"), now_cn.strftime("%A"))
        current_time_str = (
            f"{now_cn.strftime('%Y年%m月%d日')} {weekday_cn} "
            f"{now_cn.strftime('%H:%M')}"
        )
        # 计算今天/明天/后天的日期字符串
        today_date_str = now_cn.strftime("%m月%d日")
        tomorrow_date_str = (now_cn + timedelta(days=1)).strftime("%m月%d日")
        day_after_tomorrow_str = (now_cn + timedelta(days=2)).strftime("%m月%d日")

        # 搜索类技能使用专用 search 提示词
        if state.get("skill_action") == "web_search" and state.get("search_context"):
            search_prompt = ctx.prompt_manager.render(
                "search",
                search_context=state.get("search_context", ""),
                current_time=current_time_str,
                today_date=today_date_str,
                tomorrow_date=tomorrow_date_str,
                day_after_tomorrow_date=day_after_tomorrow_str,
            )
            if search_prompt:
                # 追加位置状态约束
                if location_status:
                    search_prompt += f"\n\n## 当前位置状态\n{location_status}\n"
                return search_prompt

        # 加载用户画像和习惯
        user_profile = state.get("user_profile", {})
        profile_str = ""
        if user_profile:
            # get_user_profile 返回 {"user_id": "...", "relations": [...]}
            # 需要将 relations 列表格式化为可读文本
            relations = user_profile.get("relations", [])
            if relations:
                profile_str = "; ".join(
                    f"{r.get('relation', '')}: {r.get('target', '')}"
                    for r in relations
                    if r.get("relation") and r.get("target")
                )
            elif user_profile.get("user_id"):
                profile_str = f"用户: {user_profile['user_id']}"

        # 从 state 中获取习惯记忆（已在 recall 中加载）
        memory_str = state.get("memory_str", "")
        habits_str = state.get("habits_str", "")

        # 默认使用 chat 提示词
        prompt = ctx.prompt_manager.render(
            "chat",
            user_profile=profile_str,
            memory=memory_str,
            user_habits=habits_str,
            current_time=current_time_str,
        )
        if prompt:
            # 追加位置状态约束
            if location_status:
                prompt += f"\n\n## 当前位置状态\n{location_status}\n"
            # 注入从短期对话历史提取的关键上下文
            key_ctx = state.get("key_context", {})
            if key_ctx:
                key_ctx_str = self.format_key_context(key_ctx)
                if key_ctx_str:
                    prompt += f"\n\n## 当前对话关键上下文\n{key_ctx_str}\n"
            # 当用户询问对话历史且存在滚动摘要时，引导 LLM 从摘要中查找
            user_input = state.get("user_input", "")
            running_summary = state.get("running_summary", "")
            if running_summary and self._is_history_query(user_input):
                prompt += (
                    "\n\n## 重要指引 — 对话历史查询\n"
                    "上方【历史摘要】包含了之前对话的压缩摘要，其中【对话脉络】部分按时间顺序列出了用户问过的所有问题。\n"
                    "当用户询问\"我之前问了什么\"、\"第一个问题是什么\"等时，请从【历史摘要】的【对话脉络】中查找并回答。\n"
                    "如果摘要中有相关信息，请如实告知；如果摘要中确实没有，才说\"不记得了\"。\n"
                    "绝不能声称\"这是新对话\"或\"没有之前的交流\"，因为【历史摘要】证明之前有过对话。\n"
                )
            return prompt

        # Fallback
        fallback = (
            "你叫小千，是一个智能车载语音助手。"
            f"当前时间: {current_time_str}\n"
            f"{profile_str}\n{memory_str}"
        )
        if location_status:
            fallback += f"\n{location_status}"
        # Fallback 也注入关键上下文
        key_ctx = state.get("key_context", {})
        if key_ctx:
            key_ctx_str = self.format_key_context(key_ctx)
            if key_ctx_str:
                fallback += f"\n{key_ctx_str}"
        return fallback

    @staticmethod
    def format_key_context(key_context: dict[str, Any]) -> str:
        """格式化关键上下文为可读文本，注入系统提示词。

        将 extract_key_context 提取的字典格式化为 LLM 可理解的自然语言。
        例如: {"location": "杭州", "preferences": ["喜欢咖啡"]}
        → "用户位置：杭州\n用户偏好：喜欢咖啡"

        Args:
            key_context: 关键上下文字典

        Returns:
            格式化后的文本
        """
        if not key_context:
            return ""
        lines = []
        if key_context.get("location"):
            lines.append(f"- 用户提及位置：{key_context['location']}")
        if key_context.get("preferences"):
            prefs = "、".join(key_context["preferences"])
            lines.append(f"- 用户偏好：{prefs}")
        if key_context.get("identity"):
            lines.append(f"- 用户身份：{key_context['identity']}")
        return "\n".join(lines) if lines else ""

    def get_location_status(self, state: SupervisorState) -> str:
        """获取当前位置状态，用于注入提示词防止幻觉。

        优先级:
            1. current_location 缓存（已有逆地理编码地址）
            2. GPS 坐标可用但地址未缓存 → 触发逆地理编码获取地址
            3. GPS 坐标可用但逆地理编码失败 → 告知 LLM 坐标可用
            4. GPS 坐标不可用 → 告知 LLM 定位服务不可用
        """
        try:
            adapter = None
            # 尝试从多座舱适配器获取
            cockpit_id = state.get("cockpit_id", "")
            if cockpit_id:
                from nexus.vehicle.factory import get_cockpit_vehicle_adapter
                adapter = get_cockpit_vehicle_adapter(cockpit_id)
            else:
                from nexus.vehicle.factory import build_vehicle_adapter
                adapter = build_vehicle_adapter()

            if adapter and hasattr(adapter, "navigation"):
                nav = adapter.navigation
                loc = nav.get("current_location", "")
                lat = nav.get("latitude")
                lon = nav.get("longitude")

                # 1. 已有缓存的逆地理编码地址
                if loc and "未知" not in loc and "不可用" not in loc:
                    return f"用户当前位置：{loc}（可在回复中使用此位置信息）"

                # 2. GPS 坐标可用但地址未缓存 → 触发逆地理编码
                if lat is not None and lon is not None:
                    # 调用 NavigationState 的逆地理编码方法获取地址
                    # _fetch_ip_location 是同步方法（使用 httpx.get），可在同步上下文中调用
                    try:
                        if hasattr(adapter, "_navigation"):
                            addr = adapter._navigation._fetch_ip_location(
                                float(lat), float(lon)
                            )
                        elif hasattr(adapter, "vehicle_navigation"):
                            # 回退: 通过 vehicle_navigation 方法触发逆地理编码
                            result = adapter.vehicle_navigation(
                                op="location", latitude=float(lat), longitude=float(lon)
                            )
                            addr = result.message
                        else:
                            addr = ""

                        if addr and "未知" not in addr and "不可用" not in addr:
                            nav["current_location"] = addr
                            logger.info(f"Location reverse-geocoded on demand: {addr}")
                            return f"用户当前位置：{addr}（可在回复中使用此位置信息）"
                        # 逆地理编码失败，但坐标可用
                        return (
                            f"用户当前坐标：({lat:.4f}, {lon:.4f})"
                            "（地址解析中，可使用此坐标进行周边搜索）"
                        )
                    except Exception as e:
                        logger.warning(f"Reverse geocoding failed in get_location_status: {e}")
                        return (
                            f"用户当前坐标：({lat:.4f}, {lon:.4f})"
                            "（地址解析中，可使用此坐标进行周边搜索）"
                        )

                # 3. GPS 坐标不可用
                return (
                    "⚠️ 当前位置未知（定位服务不可用）。"
                    "禁止在回复中编造或猜测用户的位置信息。"
                    "如果用户询问位置相关问题，请告知定位服务不可用。"
                )
        except Exception as e:
            logger.debug(f"Failed to get location status: {e}")

        return ""

    def _is_history_query(self, user_input: str) -> bool:
        """检测用户是否在询问当前对话的历史记录。

        委托给 ReflectionNode（持有模式匹配列表）。
        如果 ReflectionNode 尚未注入，返回 False（安全降级）。
        """
        if self._reflection is not None:
            return self._reflection.is_history_query(user_input)
        return False
