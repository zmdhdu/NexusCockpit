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

v2.1 变更:
  - 记录座舱级指标（chat_count / vehicle_cmd_count / latency）到 Redis
  - 持久化聊天记录到 MySQL chat_logs 表（按 cockpit_id 隔离，管理员不可见内容）
  - 从请求头 X-Cockpit-Id 获取座舱 ID

流程:
  1. 限流检查 → 2. 语义缓存查询 → 3. Supervisor 工作流执行 → 4. 指标记录 → 5. 聊天日志持久化 → 6. 写入缓存 → 7. 返回
"""

from __future__ import annotations

import json
import time

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from nexus.core.logger import get_logger
from nexus.core.tenant_context import get_cockpit_id
from nexus.middleware.rate_limiter import RateLimiter
from nexus.models.schemas import ChatRequest, ChatResponse
from nexus.models.state import create_initial_state
from nexus.observability.cockpit_metrics import get_cockpit_metrics
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


async def _record_chat_metrics(
    app, cockpit_id: str, user_id: str, latency_ms: float,
    cache_hit: bool, skill_action: str, user_input: str, response: str,
    session_id: str = "",
):
    """记录对话指标到 Redis + 持久化聊天日志到 MySQL。

    指标写入 Redis（实时看板），聊天日志写入 MySQL（用户隐私数据）。
    管理员只能看到聚合指标，无法查看具体对话内容。

    v2.2.2: 增加 session_id 参数，支持多会话管理

    Args:
        app: FastAPI 应用实例
        cockpit_id: 座舱 ID
        user_id: 用户 ID
        latency_ms: 响应延迟
        cache_hit: 是否命中缓存
        skill_action: 执行的技能动作
        user_input: 用户输入
        response: 助手回复
        session_id: 会话 ID（v2.2.2）
    """
    # 1. 记录实时指标到 Redis（供运营总览看板使用）
    try:
        metrics = get_cockpit_metrics()
        logger.info(f"record_chat_metrics: cockpit_id={cockpit_id}, redis={metrics._redis is not None}")
        await metrics.record_chat(cockpit_id, latency_ms, cache_hit)
        # 如果是车控指令，额外记录车控指标
        if skill_action and skill_action.startswith("vehicle_"):
            await metrics.record_vehicle_cmd(cockpit_id, success=True)
    except Exception as e:
        logger.error(f"Failed to record chat metrics: {e}")

    # 2. 持久化聊天日志到 MySQL（用户隐私数据，管理员不可见内容）
    try:
        db = getattr(app.state, "db_manager", None)
        if db and db.is_connected:
            await db.execute_update(
                "INSERT INTO chat_logs (cockpit_id, user_id, session_id, user_input, assistant_response, "
                "intent, action, latency_ms, cache_hit) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (cockpit_id, user_id, session_id, user_input[:2000], response[:2000],
                 skill_action, skill_action, latency_ms, cache_hit),
            )

            # v2.2.2: 自动创建/更新会话记录
            if session_id:
                # 尝试插入新会话（如果已存在则更新）
                title = user_input[:50] if user_input else "新对话"
                await db.execute_update(
                    "INSERT INTO chat_sessions (session_id, cockpit_id, user_id, title, message_count, last_message_at) "
                    "VALUES (%s, %s, %s, %s, 1, NOW()) "
                    "ON DUPLICATE KEY UPDATE message_count=message_count+1, last_message_at=NOW(), "
                    "title=IF(title='新对话' AND message_count=0, %s, title)",
                    (session_id, cockpit_id, user_id, title, title),
                )

            # 记录用户习惯（根据技能类型提取习惯特征）
            if skill_action:
                habit_key = f"action_{skill_action}"
                habit_value = user_input[:200]
                await db.record_user_habit(user_id, cockpit_id, habit_key, habit_value)
            # 记录常用指令
            if user_input:
                await db.record_user_habit(user_id, cockpit_id, "last_input", user_input[:200])
    except Exception as e:
        logger.error(f"Failed to persist chat log: {e}")


@router.post("", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest):
    """文本对话 (非流式)。

    流程: 限流 → 缓存查询 → Supervisor 执行 → 指标记录 → 日志持久化 → 缓存写入 → 返回

    Args:
        request: FastAPI 请求对象
        body: 包含 text、user_id、session_id 的请求体

    Returns:
        ChatResponse 包含回复文本和延迟信息
    """
    start = time.perf_counter()
    app = request.app
    cockpit_id = get_cockpit_id()

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
            # 记录缓存命中指标
            await _record_chat_metrics(
                app, cockpit_id, body.user_id, latency, True, "", body.text, cached.get("response", ""),
                session_id=body.session_id,
            )
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
    # 注入 cockpit_id 到 state，供 MainAgent 确认层使用
    state["cockpit_id"] = cockpit_id

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
    skill_action = state.get("skill_action", "")
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

    # v2.1: 记录指标 + 持久化聊天日志
    await _record_chat_metrics(
        app, cockpit_id, body.user_id, latency, False, skill_action, body.text, final_response,
        session_id=body.session_id,
    )

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
        action=skill_action,
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

    v2.1: 流式完成后记录指标 + 持久化聊天日志

    Args:
        request: FastAPI 请求对象
        body: 包含 text、user_id、session_id 的请求体

    Returns:
        StreamingResponse，media_type=text/event-stream
    """
    app = request.app
    cockpit_id = get_cockpit_id()

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
        # 注入 cockpit_id 到 state
        state["cockpit_id"] = cockpit_id

        full_response = ""
        skill_action = ""

        try:
            # v2.0: 使用 stream_with_events 获取结构化事件
            async for event in agent_graph.stream_with_events(state):
                if event.get("type") == "done":
                    full_response = event.get("data", {}).get("response", "")
                    skill_action = event.get("data", {}).get("action", "")
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            # 更新会话历史
            state_history = state.get("history", [])
            if session_store:
                await session_store.async_set(session_key, state_history)
            app.state.session_histories[session_key] = state_history[-20:]

            # v2.1: 流式完成后记录指标 + 持久化聊天日志
            latency = round((time.perf_counter() - start) * 1000, 2)
            await _record_chat_metrics(
                app, cockpit_id, body.user_id, latency, False, skill_action,
                body.text, full_response,
                session_id=body.session_id,
            )

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
