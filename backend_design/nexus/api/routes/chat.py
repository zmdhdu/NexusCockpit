"""
Chat Routes — 文本对话 REST + SSE 接口

v2.0 变更:
  - 使用 SupervisorGraph 替代 AgentGraph
  - SSE 流式接口改用 stream_with_events()，输出结构化事件
  - 支持 checkpoint 持久化（thread_id = session_id）
  - 缓存检查上移至 Supervisor（CacheGuard 节点，Phase 5 实现）
  - 集成 SessionStore 持久化会话历史 (from main L5 fix)
  - 集成 Langfuse 链路追踪 (from main L7 fix)
  - has_side_effect 缓存安全隔离 (from main L5 fix)

流程:
  1. 限流检查 → 2. 语义缓存查询 → 3. Supervisor 工作流执行 → 4. 写入缓存 → 5. 返回
"""

from __future__ import annotations

import json
import time

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from nexus.core.logger import get_logger
from nexus.middleware.rate_limiter import RateLimiter
from nexus.models.schemas import ChatRequest, ChatResponse
from nexus.models.state import create_initial_state
from nexus.observability.langfuse import LangfuseMonitor
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

    流程: 限流 → 缓存查询 → Supervisor 执行 → 缓存写入 → 返回

    Args:
        request: FastAPI 请求对象
        body: 包含 text、user_id、session_id 的请求体

    Returns:
        ChatResponse 包含回复文本和延迟信息
    """
    start = time.perf_counter()
    app = request.app

    # Langfuse 链路追踪: 在 API 层创建 trace，贯穿整个请求生命周期
    langfuse: LangfuseMonitor = getattr(app.state, "langfuse", None)
    trace = None
    if langfuse:
        trace = langfuse.start_trace(
            name="chat",
            user_id=body.user_id,
            metadata={"session_id": body.session_id, "input": body.text[:200]},
        )

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

    # 构建 v2.0 SupervisorState 并执行
    agent_graph = app.state.agent_graph
    session_key = body.session_id or body.user_id

    # 优先从 SessionStore 加载历史 (Redis 持久化，重启不丢失) (from main L5 fix)
    session_store = getattr(app.state, "session_store", None)
    if session_store:
        history = await session_store.async_get(session_key)
    else:
        history = app.state.session_histories.get(session_key, [])

    state = create_initial_state(
        user_input=body.text,
        user_id=body.user_id,
        session_id=body.session_id,
        history=history,
    )

    # Langfuse span: 记录 Agent 执行耗时
    agent_span = None
    if langfuse and trace:
        agent_span = langfuse.start_span(trace, name="agent_invoke")

    try:
        state = await agent_graph.invoke(state)
        AGENT_INVOCATIONS.labels(agent_name="supervisor_pipeline", status="success").inc()
    except Exception as e:
        logger.error(f"Agent invocation failed: {e}")
        AGENT_INVOCATIONS.labels(agent_name="supervisor_pipeline", status="error").inc()
        state["final_response"] = f"处理失败: {e}"
    finally:
        if langfuse and agent_span:
            langfuse.end_observation(
                agent_span,
                output=state.get("final_response", "")[:200],
            )

    # 更新会话历史 (优先使用 SessionStore 持久化) (from main L5 fix)
    state_history = state.get("history", [])
    if session_store:
        await session_store.async_set(session_key, state_history)
    app.state.session_histories[session_key] = state_history[-20:]

    # 写入缓存 — 有副作用的响应（如车控指令）禁止缓存，避免命中缓存后车控不执行 (from main L5 fix)
    final_response = state.get("final_response", "")
    has_side_effect = state.get("has_side_effect", False)
    if cache and cache.is_enabled and final_response and not has_side_effect:
        await cache.set(
            body.text,
            {"response": final_response},
            body.user_id,
            has_side_effect=has_side_effect,  # 二次安全防护
        )

    latency = round((time.perf_counter() - start) * 1000, 2)
    REQUEST_COUNT.labels(endpoint="chat", method="POST", status="success").inc()
    REQUEST_LATENCY.labels(endpoint="chat").observe(latency / 1000)

    # 结束 Langfuse trace
    if langfuse and trace:
        langfuse.end_observation(
            trace,
            output=final_response[:200] if final_response else "",
            metadata={"latency_ms": latency, "cache_hit": False, "has_side_effect": has_side_effect},
        )

    return ChatResponse(
        response=final_response,
        user_id=body.user_id,
        session_id=body.session_id,
        latency_ms=latency,
        metadata=state.get("metadata", {}),
        intent=state.get("intent", {}).get("Route_Source", "") if state.get("intent") else "",
        action=state.get("skill_action", ""),
        trace_id=state.get("trace_id", ""),
    )


@router.post("/stream")
async def chat_stream(request: Request, body: ChatRequest):
    """文本对话 (SSE 流式)。

    v2.0 使用 SupervisorGraph.stream_with_events() 输出结构化事件:
      - intent:  意图路由结果
      - experts: 分派的专家列表
      - action:  执行的技能动作
      - chunk:   流式文本块
      - done:    完成事件

    Args:
        request: FastAPI 请求对象
        body: 包含 text、user_id、session_id 的请求体

    Returns:
        StreamingResponse，media_type=text/event-stream
    """
    app = request.app

    async def event_generator():
        agent_graph = app.state.agent_graph
        session_key = body.session_id or body.user_id
        start = time.perf_counter()

        # 优先从 SessionStore 加载历史 (from main L5 fix)
        session_store = getattr(app.state, "session_store", None)
        if session_store:
            history = await session_store.async_get(session_key)
        else:
            history = app.state.session_histories.get(session_key, [])

        state = create_initial_state(
            user_input=body.text,
            user_id=body.user_id,
            session_id=body.session_id,
            history=history,
        )

        try:
            # v2.0: 使用 stream_with_events 获取结构化事件
            async for event in agent_graph.stream_with_events(state):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            # 更新会话历史
            state_history = state.get("history", [])
            if session_store:
                await session_store.async_set(session_key, state_history)
            app.state.session_histories[session_key] = state_history[-20:]

        except Exception as e:
            logger.error(f"Stream failed: {e}")
            yield f"data: {json.dumps({'type': 'error', 'data': {'message': str(e)}}, ensure_ascii=False)}\n\n"

        finally:
            # 确保会话历史始终被更新，即使流被中断
            if session_store and "history" in state:
                await session_store.async_set(session_key, state["history"])
            if "history" in state:
                app.state.session_histories[session_key] = state["history"][-20:]

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
