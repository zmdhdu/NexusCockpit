# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
LLM Client Factory — 统一 LLM 客户端创建

核心组件: langchain-openai ChatOpenAI
  - get_chat_model() 返回 ChatOpenAI 实例（LangChain 生态标准，推荐）
  - call_llm_with_fallback() 统一 LLM 调用入口（带降级，推荐使用）
  - get_llm_client() 返回 AsyncOpenAI 实例（已弃用，保留向后兼容）

ChatOpenAI 优势:
  - 连接池管理（自动复用 HTTP 连接）
  - 重试机制（max_retries）
  - 回调集成（与 LangGraph / Langfuse 无缝对接）
  - 结构化输出（with_structured_output）
  - 流式输出（astream）

使用方式:
    # 推荐（统一入口，带降级）:
    from nexus.agent.llm_client_factory import call_llm_with_fallback
    content = await call_llm_with_fallback(
        messages=[{"role": "user", "content": "你好"}],
        temperature=0.3,
        max_tokens=300,
    )

    # 直接使用 ChatOpenAI:
    from nexus.agent.llm_client_factory import get_chat_model
    llm = get_chat_model()
    response = await llm.ainvoke([{"role": "user", "content": "你好"}])
    logger.info(response.content)
"""

from __future__ import annotations

from nexus.config import get_config
from nexus.core.circuit_breaker import CircuitBreaker
from nexus.core.exceptions import CircuitBreakerError
from nexus.core.logger import get_logger

logger = get_logger(__name__)

# 全局单例缓存
_chat_model = None      # ChatOpenAI 单例
_primary_client = None  # AsyncOpenAI 单例
_fallback_client = None # AsyncOpenAI 降级单例

# LLM 调用熔断器 — 连续失败 5 次后熔断，30s 后试探恢复
# 熔断期间直接降级到 fallback LLM，不再等待主 LLM 超时
_llm_circuit = CircuitBreaker(
    name="llm-primary",
    failure_threshold=5,
    recovery_period=30.0,
)


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
        max_retries=1,  # 1 次重试 = 最多 2 次尝试，避免用户等待 90 秒
    )
    mode = "local llama.cpp" if config.is_local else "cloud API"
    logger.info(f"ChatOpenAI created: mode={mode}, model={config.llm_model}")
    return _chat_model


def get_llm_client():
    """获取 AsyncOpenAI 实例（全局单例，已弃用）。

    ⚠️ 已弃用: 新代码请使用 get_chat_model().ainvoke()。
    保留此函数仅为向后兼容 (memory/manager.py, memory/compressor.py 仍在使用)。

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
) -> str:
    """带自动降级的 LLM 调用（统一使用 ChatOpenAI）。

    优先使用 ChatOpenAI.ainvoke()，失败时降级到 fallback ChatOpenAI。
    返回纯文本内容，调用方无需处理响应对象格式差异。

    Args:
        messages: OpenAI 格式消息列表 [{"role": "...", "content": "..."}, ...]
        model: 模型名称（可选，已从 ChatOpenAI 单例获取，此参数仅用于日志）
        temperature: 生成温度
        max_tokens: 最大 token 数
        stream: 是否流式输出（当前不支持，忽略）
        **kwargs: 其他参数

    Returns:
        LLM 生成的文本内容字符串
    """
    config = get_config().llm

    # 熔断器保护: 如果主 LLM 连续失败，直接跳过到 fallback
    try:
        chat_model = get_chat_model()
        # ChatOpenAI.ainvoke 返回 AIMessage，取 .content
        response = await _llm_circuit.call(
            chat_model.ainvoke,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        return response.content or ""
    except CircuitBreakerError:
        # 熔断器开启 — 直接降级
        logger.warning("LLM circuit breaker OPEN, skipping primary, falling back")
    except Exception as e:
        logger.warning(f"Primary ChatOpenAI failed: {e}")

    fallback = get_fallback_client()
    if fallback is None:
        raise
    logger.warning("Falling back to local LLM (AsyncOpenAI)")
    # fallback 仍使用 AsyncOpenAI（降级场景，ChatOpenAI 单例可能已损坏）
    response = await fallback.chat.completions.create(
        model=config.fallback_model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=stream,
        **kwargs,
    )
    return response.choices[0].message.content or ""
