"""
Responder Agent — 最终响应生成

Responder 是工作流的第三站，负责生成用户看到的最终回复。
根据前置阶段的结果，走三条分支:

  分支 A (需要澄清): 直接返回 Planner 生成的澄清提问
  分支 B (技能已处理): 返回技能执行结果 (如 "已将空调调到 24 度")
  分支 C (LLM 闲聊): 调用大模型生成自然语言回复

对于搜索类技能 (web_search)，会额外调用 LLM 根据搜索结果组织回答。
"""

from __future__ import annotations

from time import perf_counter
from typing import AsyncGenerator, List

from openai import AsyncOpenAI

from nexus.config import get_config
from nexus.core.logger import get_logger
from nexus.memory.compressor import ContextCompressor
from nexus.models.state import AgentState

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
        llm_client: AsyncOpenAI | None = None,
        compressor: ContextCompressor | None = None,
    ):
        self.config = get_config().llm
        self.client = llm_client or AsyncOpenAI(
            api_key=self.config.ark_api_key,
            base_url=self.config.ark_base_url,
        )
        self.compressor = compressor or ContextCompressor(self.client)

    async def respond(self, state: AgentState) -> AgentState:
        """生成最终响应 (非流式，等待全部完成)。

        Args:
            state: 包含技能执行结果的 Agent 状态

        Returns:
            更新后的 state，包含 final_response 字段
        """
        t0 = perf_counter()
        full_response = ""

        # 分支 A: 需要澄清
        if state.need_clarification and state.clarification_prompt:
            full_response = state.clarification_prompt

        # 分支 B: 技能已处理
        elif state.skill_handled:
            skill_result = state.skill_result
            if skill_result and skill_result.reply:
                full_response = skill_result.reply

            # 如果是搜索类技能，需要 LLM 组织回答
            if state.skill_action == "web_search" and state.search_context:
                full_response = await self._generate_llm_response(
                    state, search_ctx=state.search_context
                )

        # 分支 C: LLM 闲聊兜底
        else:
            full_response = await self._generate_llm_response(state)

        state.final_response = full_response
        state.metadata["responder_latency_ms"] = round((perf_counter() - t0) * 1000, 2)

        # 更新历史
        state.history.append({"role": "user", "content": state.user_input})
        state.history.append({"role": "assistant", "content": full_response})

        logger.info(
            f"Responder done: response_len={len(full_response)}, "
            f"latency={state.metadata['responder_latency_ms']}ms"
        )
        return state

    async def stream_respond(self, state: AgentState) -> AsyncGenerator[str, None]:
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
        if state.need_clarification and state.clarification_prompt:
            full_response = state.clarification_prompt
            yield full_response

        # 分支 B: 技能已处理 (非搜索类)
        elif state.skill_handled and state.skill_action != "web_search":
            skill_result = state.skill_result
            if skill_result and skill_result.reply:
                full_response = skill_result.reply
                yield skill_result.reply

        # 分支 C: 搜索类 / LLM 闲聊
        else:
            search_ctx = state.search_context if state.skill_action == "web_search" else ""
            async for chunk in self._stream_llm_response(state, search_ctx=search_ctx):
                full_response += chunk
                yield chunk

        state.final_response = full_response
        state.metadata["responder_latency_ms"] = round((perf_counter() - t0) * 1000, 2)

        # 更新历史
        state.history.append({"role": "user", "content": state.user_input})
        state.history.append({"role": "assistant", "content": full_response})

    async def _generate_llm_response(
        self, state: AgentState, search_ctx: str = ""
    ) -> str:
        """非流式 LLM 回复"""
        # 搜索类技能使用专用提示词
        if state.skill_action == "web_search" and search_ctx:
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
            user_input=state.user_input,
            history=state.history,
            running_summary=state.running_summary,
            memory_str=state.memory_str,
            search_ctx=search_ctx,
        )
        state.running_summary = new_summary

        try:
            response = await self.client.chat.completions.create(
                model=self.config.llm_model,
                messages=msgs,
                temperature=0.7,
                max_tokens=self.config.max_tokens,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"LLM response failed: {e}")
            return f"抱歉，我遇到了一些问题: {e}"

    async def _stream_llm_response(
        self, state: AgentState, search_ctx: str = ""
    ) -> AsyncGenerator[str, None]:
        """流式 LLM 回复"""
        # 搜索类技能使用专用提示词
        if state.skill_action == "web_search" and search_ctx:
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
            user_input=state.user_input,
            history=state.history,
            running_summary=state.running_summary,
            memory_str=state.memory_str,
            search_ctx=search_ctx,
        )
        state.running_summary = new_summary

        try:
            response = await self.client.chat.completions.create(
                model=self.config.llm_model,
                messages=msgs,
                stream=True,
                temperature=0.7,
                max_tokens=self.config.max_tokens,
            )
            async for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
        except Exception as e:
            logger.error(f"LLM streaming failed: {e}")
            yield f"抱歉，连接模型出错: {e}"
