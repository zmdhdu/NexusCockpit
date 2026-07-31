# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Responder Agent — 最终响应生成

Responder 是工作流的第三站，负责生成用户看到的最终回复。
根据前置阶段的结果，走三条分支:

  分支 A (需要澄清): 直接返回 Supervisor 生成的澄清提问
  分支 B (技能已处理): 返回技能执行结果 (如 "已将空调调到 24 度")
  分支 C (LLM 闲聊): 调用大模型生成自然语言回复

对于搜索类技能 (web_search)，会额外调用 LLM 根据搜索结果组织回答。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from time import perf_counter

from typing import Any

from nexus.agent.llm_client_factory import get_chat_model, get_llm_client, get_fallback_client
from nexus.config import get_config
from nexus.core.logger import get_logger
from nexus.memory.compressor import ContextCompressor
from nexus.models.state import SupervisorState

logger = get_logger(__name__)

SPLIT_PUNCT = ["。", "！", "？", "；", "...", ".", "!", "?"]


class ResponderAgent:
    """响应 Agent: 生成最终用户回复。

    Args:
        llm_client: OpenAI 兼容的异步 LLM 客户端 (可选)
        compressor: 上下文压缩器，用于截断过长的历史对话
    """

    def __init__(
        self,
        llm_client: Any = None,
        compressor: ContextCompressor | None = None,
    ):
        self.config = get_config().llm
        # ChatOpenAI 主 LLM (LangChain 生态)
        self._chat_model = get_chat_model()
        # AsyncOpenAI 客户端（供降级调用使用）
        self.client = llm_client or get_llm_client()
        self.compressor = compressor or ContextCompressor(self.client)
        # 降级客户端
        self._fallback_client = get_fallback_client()

    async def respond(self, state: SupervisorState) -> SupervisorState:
        """生成最终响应 (非流式，等待全部完成)。

        Args:
            state: 包含技能执行结果的 Agent 状态

        Returns:
            更新后的 state，包含 final_response 字段
        """
        t0 = perf_counter()
        full_response = ""

        # 分支 A: 需要澄清
        if state.get("need_clarification") and state.get("clarification_prompt"):
            full_response = state["clarification_prompt"]

        # 分支 B: 技能已处理
        elif state.get("skill_handled"):
            skill_result = state.get("skill_result")
            if skill_result and skill_result.reply:
                full_response = skill_result.reply

            # 如果是搜索类技能，需要 LLM 组织回答
            if state.get("skill_action") == "web_search" and state.get("search_context"):
                full_response = await self._generate_llm_response(
                    state, search_ctx=state.get("search_context", "")
                )

        # 分支 C: LLM 闲聊兜底
        else:
            full_response = await self._generate_llm_response(state)

        state["final_response"] = full_response
        state.setdefault("metadata", {})["responder_latency_ms"] = round((perf_counter() - t0) * 1000, 2)

        # 更新历史
        state.setdefault("history", []).append({"role": "user", "content": state.get("user_input", "")})
        state["history"].append({"role": "assistant", "content": full_response})

        logger.info(
            f"Responder done: response_len={len(full_response)}, "
            f"latency={state['metadata']['responder_latency_ms']}ms"
        )
        return state

    async def stream_respond(self, state: SupervisorState) -> AsyncGenerator[str, None]:
        """流式生成最终响应，逐块输出。

        用于 SSE / WebSocket 场景，用户能看到文字逐步出现。

        Args:
            state: Agent 状态

        Yields:
            响应文本块
        """
        t0 = perf_counter()
        full_response = ""

        # 分支 A: 需要澄清
        if state.get("need_clarification") and state.get("clarification_prompt"):
            full_response = state["clarification_prompt"]
            yield full_response

        # 分支 B: 技能已处理 (非搜索类)
        elif state.get("skill_handled") and state.get("skill_action") != "web_search":
            skill_result = state.get("skill_result")
            if skill_result and skill_result.reply:
                full_response = skill_result.reply
                yield skill_result.reply

        # 分支 C: 搜索类 / LLM 闲聊
        else:
            search_ctx = state.get("search_context", "") if state.get("skill_action") == "web_search" else ""
            async for chunk in self._stream_llm_response(state, search_ctx=search_ctx):
                full_response += chunk
                yield chunk

        state["final_response"] = full_response
        state.setdefault("metadata", {})["responder_latency_ms"] = round((perf_counter() - t0) * 1000, 2)

        # 更新历史
        state.setdefault("history", []).append({"role": "user", "content": state.get("user_input", "")})
        state["history"].append({"role": "assistant", "content": full_response})

    async def _generate_llm_response(
        self, state: SupervisorState, search_ctx: str = ""
    ) -> str:
        """非流式 LLM 回复"""
        # 搜索类技能使用专用提示词
        if state.get("skill_action") == "web_search" and search_ctx:
            system_msg = (
                "你是车载语音助手小千。用户进行了联网搜索，请根据以下搜索结果组织回答。\n\n"
                f"搜索结果：\n{search_ctx}\n\n"
                "回答要求：\n"
                "1. 根据搜索结果中的信息回答用户问题，不要编造\n"
                "2. 回答要简洁实用，直接给出用户关心的核心信息\n"
                "3. 如果搜索结果与问题相关，请总结关键信息\n"
                "4. 回答不超过200字，使用自然口语化的表达"
            )
        else:
            system_msg = "你叫小千，是一个活泼可爱的车载语音助手。请结合上下文极简回答用户，不超过30字。"

        msgs, new_summary = await self.compressor.build_context(
            system_prompt=system_msg,
            user_input=state.get("user_input", ""),
            history=state.get("history", []),
            running_summary=state.get("running_summary", ""),
            memory_str=state.get("memory_str", ""),
            search_ctx=search_ctx,
        )
        state["running_summary"] = new_summary

        try:
            response = await self._chat_model.ainvoke(msgs)
            return response.content.strip()
        except Exception as e:
            logger.error(f"LLM response failed: {e}")
            # 云端 LLM 失败时降级到本地 LLM
            if self._fallback_client:
                logger.warning("Falling back to local LLM")
                try:
                    fb_response = await self._fallback_client.chat.completions.create(
                        model=self.config.fallback_model,
                        messages=msgs,
                        temperature=0.7,
                        max_tokens=self.config.max_tokens,
                    )
                    return fb_response.choices[0].message.content.strip()
                except Exception as fb_err:
                    logger.error(f"Local LLM fallback also failed: {fb_err}")
            # 安全：异常细节仅写入日志，不透传给用户，避免泄露内部信息
            return "抱歉，我现在有点忙不过来，请稍后再试。"

    async def _stream_llm_response(
        self, state: SupervisorState, search_ctx: str = ""
    ) -> AsyncGenerator[str, None]:
        """流式 LLM 回复"""
        # 搜索类技能使用专用提示词
        if state.get("skill_action") == "web_search" and search_ctx:
            system_msg = (
                "你是车载语音助手小千。用户进行了联网搜索，请根据以下搜索结果组织回答。\n\n"
                f"搜索结果：\n{search_ctx}\n\n"
                "回答要求：\n"
                "1. 根据搜索结果中的信息回答用户问题，不要编造\n"
                "2. 回答要简洁实用，直接给出用户关心的核心信息\n"
                "3. 如果搜索结果与问题相关，请总结关键信息\n"
                "4. 回答不超过200字，使用自然口语化的表达"
            )
        else:
            system_msg = "你叫小千，是一个活泼可爱的车载语音助手。请结合上下文极简回答用户，不超过30字。"

        msgs, new_summary = await self.compressor.build_context(
            system_prompt=system_msg,
            user_input=state.get("user_input", ""),
            history=state.get("history", []),
            running_summary=state.get("running_summary", ""),
            memory_str=state.get("memory_str", ""),
            search_ctx=search_ctx,
        )
        state["running_summary"] = new_summary

        try:
            response = await self._chat_model.astream(msgs)
            async for chunk in response:
                content = chunk.content
                if content:
                    yield content
        except Exception as e:
            logger.error(f"LLM streaming failed: {e}")
            # 云端 LLM 失败时降级到本地 LLM
            if self._fallback_client:
                logger.warning("Falling back to local LLM (streaming)")
                try:
                    fb_response = await self._fallback_client.chat.completions.create(
                        model=self.config.fallback_model,
                        messages=msgs,
                        stream=True,
                        temperature=0.7,
                        max_tokens=self.config.max_tokens,
                    )
                    async for chunk in fb_response:
                        content = chunk.choices[0].delta.content
                        if content:
                            yield content
                    return
                except Exception as fb_err:
                    logger.error(f"Local LLM streaming fallback also failed: {fb_err}")
            # 安全：异常细节仅写入日志，不透传给用户，避免泄露内部信息
            yield "抱歉，我现在有点忙不过来，请稍后再试。"
