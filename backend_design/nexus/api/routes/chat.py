"""
Chat Routes — 文本对话 REST + SSE 接口

本模块提供两个接口:
  POST /chat        — 非流式对话 (等待全部完成)
  POST /chat/stream — SSE 流式对话 (逐块输出)

流程:
  1. 限流检查 → 2. 语义缓存查询 → 3. Agent 工作流执行 → 4. 写入缓存 → 5. 返回
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from nexus.core.logger import get_logger
from nexus.middleware.rate_limiter import RateLimiter
from nexus.models.schemas import ChatRequest, ChatResponse
from nexus.observability.metrics import (
    AGENT_INVOCATIONS,
    CACHE_HITS,
    CACHE_MISSES,
    REQUEST_COUNT,
    REQUEST_LATENCY,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest):
    """文本对话 (非流式)。

    流程: 限流 → 缓存查询 → Agent 执行 → 缓存写入 → 返回

    Args:
        request: FastAPI 请求对象
        body: 包含 text、user_id、session_id 的请求体

    Returns:
        ChatResponse 包含回复文本和延迟信息
    """
    start = time.perf_counter()
    app = request.app

    # 限流检查
    rate_limiter: RateLimiter = app.state.rate_limiter
    if rate_limiter:
        await rate_limiter.check_or_raise(body.user_id, "chat")

    # 语义缓存查询
    cache = app.state.semantic_cache
    if cache and cache.is_enabled:
        cached = await cache.get(body.text, body.user_id)
        if cached:
            CACHE_HITS.inc()
            latency = round((time.perf_counter() - start) * 1000, 2)
            REQUEST_COUNT.labels(endpoint="chat", method="POST", status="cache_hit").inc()
            return ChatResponse(
                response=cached.get("response", ""),
                user_id=body.user_id,
                session_id=body.session_id,
                latency_ms=latency,
                metadata={"cache_hit": True},
                cache_hit=True,
            )
        CACHE_MISSES.inc()

    # 构建 Agent 状态并执行
    from nexus.models.state import AgentState

    state = AgentState(
        user_input=body.text,
        user_id=body.user_id,
        session_id=body.session_id,
        history=app.state.session_histories.get(body.session_id or body.user_id, []),
    )

    agent_graph = app.state.agent_graph
    try:
        state = await agent_graph.invoke(state)
        AGENT_INVOCATIONS.labels(agent_name="full_pipeline", status="success").inc()
    except Exception as e:
        logger.error(f"Agent invocation failed: {e}")
        AGENT_INVOCATIONS.labels(agent_name="full_pipeline", status="error").inc()
        state.final_response = f"处理失败: {e}"

    # 更新会话历史
    session_key = body.session_id or body.user_id
    app.state.session_histories[session_key] = state.history[-20:]

    # 写入缓存
    if cache and cache.is_enabled and state.final_response:
        await cache.set(
            body.text,
            {"response": state.final_response},
            body.user_id,
        )

    latency = round((time.perf_counter() - start) * 1000, 2)
    REQUEST_COUNT.labels(endpoint="chat", method="POST", status="success").inc()
    REQUEST_LATENCY.labels(endpoint="chat").observe(latency / 1000)

    return ChatResponse(
        response=state.final_response,
        user_id=body.user_id,
        session_id=body.session_id,
        latency_ms=latency,
        metadata=state.metadata,
    )


@router.post("/stream")
async def chat_stream(request: Request, body: ChatRequest):
    """文本对话 (SSE 流式)。

    使用 Server-Sent Events 逐块输出响应文本，前端可用 EventSource 接收。

    Args:
        request: FastAPI 请求对象
        body: 包含 text、user_id、session_id 的请求体

    Returns:
        StreamingResponse，media_type=text/event-stream
    """
    app = request.app

    async def event_generator():
        from nexus.models.state import AgentState

        state = AgentState(
            user_input=body.text,
            user_id=body.user_id,
            session_id=body.session_id,
            history=app.state.session_histories.get(body.session_id or body.user_id, []),
        )

        agent_graph = app.state.agent_graph
        start = time.perf_counter()

        try:
            async for chunk in agent_graph.stream(state):
                data = json.dumps({"content": chunk}, ensure_ascii=False)
                yield f"data: {data}\n\n"

            latency = round((time.perf_counter() - start) * 1000, 2)
            yield f"data: {json.dumps({'done': True, 'latency_ms': latency}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"Stream failed: {e}")
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

        # 更新会话历史
        session_key = body.session_id or body.user_id
        app.state.session_histories[session_key] = state.history[-20:]

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
