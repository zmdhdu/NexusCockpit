# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
LLM Client Factory — 统一 LLM 客户端创建

核心组件: langchain-openai ChatOpenAI
  - get_chat_model() 返回 ChatOpenAI 实例（LangChain 生态标准，推荐）
  - get_llm_client() 返回 AsyncOpenAI 实例（供需要直接调用 OpenAI SDK 的场景使用）

ChatOpenAI 优势:
  - 连接池管理（自动复用 HTTP 连接）
  - 重试机制（max_retries）
  - 回调集成（与 LangGraph / Langfuse 无缝对接）
  - 结构化输出（with_structured_output）
  - 流式输出（astream）

使用方式:
    # 推荐（LangChain 生态）:
    from nexus.agent.llm_client_factory import get_chat_model
    llm = get_chat_model()
    response = await llm.ainvoke([{"role": "user", "content": "你好"}])
    print(response.content)

    # 直接调用 OpenAI SDK（反思校验等场景）:
    from nexus.agent.llm_client_factory import get_llm_client
    client = get_llm_client()
    response = await client.chat.completions.create(...)
"""

from __future__ import annotations

from typing import Any

from nexus.config import get_config
from nexus.core.logger import get_logger

logger = get_logger(__name__)

# 全局单例缓存
_chat_model = None      # ChatOpenAI 单例
_primary_client = None  # AsyncOpenAI 单例
_fallback_client = None # AsyncOpenAI 降级单例


def get_chat_model():
    """获取 LangChain ChatOpenAI 实例（全局单例，推荐使用）。

    自带连接池管理、自动重试、回调集成、结构化输出。

    Returns:
        ChatOpenAI 实例
    """
    global _chat_model
    if _chat_model is not None:
        return _chat_model

    from langchain_openai import ChatOpenAI

    config = get_config().llm
    _chat_model = ChatOpenAI(
        model=config.llm_model,
        api_key=config.ark_api_key or "not-needed",
        base_url=config.ark_base_url,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        timeout=config.timeout,
        max_retries=2,
    )
    mode = "local llama.cpp" if config.is_local else "cloud API"
    logger.info(f"ChatOpenAI created: mode={mode}, model={config.llm_model}")
    return _chat_model


def get_llm_client():
    """获取 AsyncOpenAI 实例（全局单例）。

    供反思校验、流式输出等需要直接调用 OpenAI SDK 的场景使用。
    新代码推荐使用 get_chat_model() + ainvoke()。

    Returns:
        AsyncOpenAI 实例
    """
    global _primary_client
    if _primary_client is not None:
        return _primary_client

    from openai import AsyncOpenAI

    config = get_config().llm
    _primary_client = AsyncOpenAI(
        api_key=config.ark_api_key or "not-needed",
        base_url=config.ark_base_url,
        timeout=config.timeout,
    )
    mode = "local llama.cpp" if config.is_local else "cloud API"
    logger.info(f"AsyncOpenAI client created: mode={mode}, base_url={config.ark_base_url}")
    return _primary_client


def get_fallback_client():
    """获取降级 LLM 客户端（全局单例）。

    仅当 LLM_PROVIDER=cloud 且 LLM_FALLBACK_ENABLED=true 时返回降级客户端。

    Returns:
        AsyncOpenAI 实例或 None
    """
    global _fallback_client
    if _fallback_client is not None:
        return _fallback_client

    config = get_config().llm
    if config.is_local or not config.fallback_enabled:
        return None

    from openai import AsyncOpenAI
    _fallback_client = AsyncOpenAI(
        api_key=config.fallback_api_key or "not-needed",
        base_url=config.fallback_base_url,
        timeout=config.fallback_timeout,
    )
    logger.info(f"Fallback LLM client created: base_url={config.fallback_base_url}")
    return _fallback_client


def reset_clients() -> None:
    """重置客户端单例（用于配置热更新或测试）。"""
    global _chat_model, _primary_client, _fallback_client
    _chat_model = None
    _primary_client = None
    _fallback_client = None
    logger.info("LLM client singletons reset (ChatOpenAI + AsyncOpenAI)")


async def call_llm_with_fallback(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 512,
    stream: bool = False,
    **kwargs,
) -> Any:
    """带自动降级的 LLM 调用（使用 ChatOpenAI）。

    优先使用 ChatOpenAI.ainvoke()，失败时降级到 fallback LLM。

    Args:
        messages: OpenAI 格式消息列表
        model: 模型名称（可选，默认从配置读取）
        temperature: 生成温度
        max_tokens: 最大 token 数
        stream: 是否流式输出
        **kwargs: 其他参数

    Returns:
        AIMessage（ChatOpenAI 响应）或 OpenAI 响应对象（降级时）
    """
    config = get_config().llm

    try:
        chat_model = get_chat_model()
        # ChatOpenAI.ainvoke 返回 AIMessage
        response = await chat_model.ainvoke(messages)
        return response
    except Exception as e:
        logger.warning(f"Primary ChatOpenAI failed: {e}")
        fallback = get_fallback_client()
        if fallback is None:
            raise
        logger.warning("Falling back to local LLM (AsyncOpenAI)")
        return await fallback.chat.completions.create(
            model=config.fallback_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            **kwargs,
        )
