# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Chat Routes — 文本对话 REST + SSE 接口

核心特性:
  - 使用 SupervisorGraph 多智能体编排
  - SSE 流式接口使用 stream_with_events()，输出结构化事件
  - 支持 checkpoint 持久化（thread_id = session_id）
  - 缓存检查上移至 Supervisor（CacheGuard 节点）
  - 集成 SessionStore 持久化会话历史
  - 集成 Langfuse 链路追踪
  - has_side_effect 缓存安全隔离
  - 记录座舱级指标（chat_count / vehicle_cmd_count / latency）到 Redis
  - 持久化聊天记录到 MySQL chat_logs 表（按 cockpit_id 隔离，管理员不可见内容）
  - 从请求头 X-Cockpit-Id 获取座舱 ID

流程:
  1. 限流检查 → 2. 语义缓存查询 → 3. Supervisor 工作流执行 → 4. 指标记录 → 5. 聊天日志持久化 → 6. 写入缓存 → 7. 返回
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from nexus.config import get_config
from nexus.core.logger import get_logger
from nexus.core.tenant_context import get_cockpit_id
from nexus.intent.constants import VEHICLE_INTENT_KEYS
from nexus.intent.heuristic import HeuristicRouter
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

# 启发式路由器单例 — 用于判断是否为车控指令（跳过缓存）
_heuristic_router = HeuristicRouter()

# 车控意图字段集合 — 命中其中任一即为车控指令（常量来自 nexus.intent.constants）


def _is_vehicle_command(text: str) -> bool:
    """检查文本是否为车控指令。

    使用启发式路由器快速判断，如果命中车控意图则跳过缓存，
    确保车控命令每次都实际执行而非返回旧缓存。
    """
    quick = _heuristic_router.route(text)
    return any(k in quick for k in VEHICLE_INTENT_KEYS)


# 会话级别并发锁 — 防止同一 session 的并发请求交叉污染会话历史
# 当用户快速连续发送多条消息时，确保前一条处理完再处理下一条
# 增加上限防止内存泄漏，超过阈值时清理空闲锁
_session_locks: dict[str, asyncio.Lock] = {}
_SESSION_LOCKS_MAX = 500


def _get_session_lock(session_key: str) -> asyncio.Lock:
    """获取指定会话的并发锁（不存在则创建）。

    当锁数量超过 _SESSION_LOCKS_MAX 时，清理当前未被持有的锁以防内存泄漏。
    """
    if session_key not in _session_locks:
        # 清理未被持有的空闲锁，防止长期运行内存泄漏
        if len(_session_locks) >= _SESSION_LOCKS_MAX:
            idle_keys = [k for k, v in _session_locks.items() if not v.locked()]
            for k in idle_keys[:_SESSION_LOCKS_MAX // 2]:
                del _session_locks[k]
            logger.debug(f"Cleaned up {len(idle_keys[:_SESSION_LOCKS_MAX // 2])} idle session locks")
        _session_locks[session_key] = asyncio.Lock()
    return _session_locks[session_key]


async def _record_chat_metrics(
    app, cockpit_id: str, user_id: str, latency_ms: float,
    cache_hit: bool, skill_action: str, user_input: str, response: str,
    session_id: str = "",
    skill_success: bool = True,
):
    """记录对话指标到 Redis + 持久化聊天日志到 MySQL。

    指标写入 Redis（实时看板），聊天日志写入 MySQL（用户隐私数据）。
    管理员只能看到聚合指标，无法查看具体对话内容。

    Args:
        app: FastAPI 应用实例
        cockpit_id: 座舱 ID
        user_id: 用户 ID
        latency_ms: 响应延迟（毫秒）
        cache_hit: 是否命中缓存
        skill_action: 执行的技能动作
        user_input: 用户输入
        response: 助手回复
        session_id: 会话 ID
        skill_success: 技能执行是否成功（车控指令的验证结果）
    """
    # 1. 记录实时指标到 Redis（供运营总览看板使用）
    try:
        metrics = get_cockpit_metrics()
        logger.info(f"record_chat_metrics: cockpit_id={cockpit_id}, redis={metrics._redis is not None}")
        await metrics.record_chat(cockpit_id, latency_ms, cache_hit)
        # 如果是车控指令，额外记录车控指标（包含成功/失败状态）
        if skill_action and skill_action.startswith("vehicle_"):
            await metrics.record_vehicle_cmd(cockpit_id, success=skill_success)
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

            # 自动创建/更新会话记录
            if session_id:
                # 尝试插入新会话（如果已存在则更新）
                # 会话标题用第一次用户问题前20字，首次消息时自动更新
                title = user_input[:20] if user_input else "新对话"
                await db.execute_update(
                    "INSERT INTO chat_sessions "
                    "(session_id, cockpit_id, user_id, title, message_count, last_message_at) "
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

    # 语义缓存查询 — 车控指令跳过缓存，确保每次都实际执行
    # 旧缓存可能存储了车控响应（has_side_effect 修复前写入），
    # 导致"打开车窗"命中缓存后不执行实际车控操作
    is_vehicle_cmd = _is_vehicle_command(body.text)
    cache = app.state.semantic_cache
    if cache and cache.is_enabled and not is_vehicle_cmd:
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
    elif is_vehicle_cmd:
        CACHE_MISSES.inc()
        logger.info(f"Vehicle command detected, skipping cache: '{body.text[:50]}'")

    # 构建 SupervisorState 并执行
    agent_graph = app.state.agent_graph
    # session_id 为空时生成唯一临时 ID，禁止回退到 user_id
    # 回退到 user_id 会导致同一用户的所有对话共享历史，破坏会话隔离
    session_key = body.session_id or f"temp_{uuid.uuid4().hex[:16]}"

    # 获取会话锁，防止同一 session 的并发请求交叉污染历史
    session_lock = _get_session_lock(session_key)

    # 优先从 SessionStore 加载历史 (Redis 持久化，重启不丢失) (from main L5 fix)
    session_store = getattr(app.state, "session_store", None)

    async with session_lock:
        # 在锁内读取历史，确保不会读到并发请求的中间状态
        if session_store:
            history = await session_store.async_get(session_key)
            # 加载滚动摘要（阈值压缩产生的跨轮次摘要）
            running_summary = await session_store.async_get_summary(session_key)
        else:
            history = app.state.session_histories.get(session_key, [])
            running_summary = ""

        state = create_initial_state(
            user_input=body.text,
            user_id=body.user_id,
            session_id=body.session_id,
            history=history,
            running_summary=running_summary,  # 传入滚动摘要
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
            state["final_response"] = "处理失败，服务暂时不可用"
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
            # 持久化滚动摘要（阈值压缩产生的跨轮次摘要）
            state_summary = state.get("running_summary", "")
            if state_summary:
                await session_store.async_set_summary(session_key, state_summary)
        app.state.session_histories[session_key] = state_history[-get_config().memory.max_history_len:]

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

    # 记录指标 + 持久化聊天日志
    # 从 expert_results 中提取车控指令的成功/失败状态
    expert_results = state.get("expert_results", [])
    skill_success = True
    if skill_action and skill_action.startswith("vehicle_"):
        for er in expert_results:
            if er.get("skill_status") == "error":
                skill_success = False
                break
    await _record_chat_metrics(
        app, cockpit_id, body.user_id, latency, False, skill_action, body.text, final_response,
        session_id=body.session_id,
        skill_success=skill_success,
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

    使用 SupervisorGraph.stream_with_events() 输出结构化事件:
      - intent:  意图路由结果
      - experts: 分派的专家列表
      - action:  执行的技能动作
      - chunk:   流式文本块
      - done:    完成事件

    流式完成后记录指标 + 持久化聊天日志

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
        # session_id 为空时生成唯一临时 ID，禁止回退到 user_id
        session_key = body.session_id or f"temp_{uuid.uuid4().hex[:16]}"
        start = time.perf_counter()

        # 语义缓存检查 — 车控指令跳过缓存，确保每次都实际执行
        # 旧缓存可能存储了车控响应（has_side_effect 修复前写入），
        # 导致"打开车窗"命中缓存后不执行实际车控操作
        is_vehicle_cmd = _is_vehicle_command(body.text)
        cache = app.state.semantic_cache
        if cache and cache.is_enabled and not is_vehicle_cmd:
            cached = await cache.get(body.text, body.user_id)
            if cached:
                CACHE_HITS.inc()
                latency = round((time.perf_counter() - start) * 1000, 2)
                REQUEST_COUNT.labels(endpoint="chat", method="POST", status="cache_hit").inc()
                cached_response = cached.get("response", "")
                # 记录缓存命中指标
                await _record_chat_metrics(
                    app, cockpit_id, body.user_id, latency, True, "", body.text, cached_response,
                    session_id=body.session_id,
                )
                # 缓存命中：直接以 done 事件返回，不走 Agent 流式
                yield (
                    f"data: {json.dumps({'type': 'thinking', 'data': {'message': '命中缓存'}}, ensure_ascii=False)}\n\n"
                )
                yield (
                    f"data: {json.dumps({'type': 'chunk', 'data': {'chunk': cached_response}}, ensure_ascii=False)}\n\n"
                )
                done_payload = {
                    'type': 'done',
                    'data': {
                        'response': cached_response,
                        'latency_ms': latency,
                        'cache_hit': True,
                    },
                }
                yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
                return
            CACHE_MISSES.inc()
        elif is_vehicle_cmd:
            CACHE_MISSES.inc()
            logger.info(f"Vehicle command detected, skipping cache (stream): '{body.text[:50]}'")

        # 获取会话锁，防止同一 session 的并发请求交叉污染历史
        session_lock = _get_session_lock(session_key)

        # 优先从 SessionStore 加载历史 (from main L5 fix)
        session_store = getattr(app.state, "session_store", None)

        async with session_lock:
            # 在锁内读取历史，确保不会读到并发请求的中间状态
            if session_store:
                history = await session_store.async_get(session_key)
                # 加载滚动摘要
                running_summary = await session_store.async_get_summary(session_key)
            else:
                history = app.state.session_histories.get(session_key, [])
                running_summary = ""

            state = create_initial_state(
                user_input=body.text,
                user_id=body.user_id,
                session_id=body.session_id,
                history=history,
                running_summary=running_summary,  # 传入滚动摘要
            )
            # 注入 cockpit_id 到 state
            state["cockpit_id"] = cockpit_id

            full_response = ""
            skill_action = ""

            try:
                # 使用 stream_with_events 获取结构化事件
                async for event in agent_graph.stream_with_events(state):
                    if event.get("type") == "done":
                        full_response = event.get("data", {}).get("response", "")
                        skill_action = event.get("data", {}).get("action", "")
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

                # 更新会话历史
                state_history = state.get("history", [])
                if session_store:
                    await session_store.async_set(session_key, state_history)
                    # 持久化滚动摘要
                    state_summary = state.get("running_summary", "")
                    if state_summary:
                        await session_store.async_set_summary(session_key, state_summary)
                app.state.session_histories[session_key] = state_history[-get_config().memory.max_history_len:]

                # 写入缓存 — 有副作用的响应（如车控指令）禁止缓存
                has_side_effect = state.get("has_side_effect", False)
                if cache and cache.is_enabled and full_response and not has_side_effect:
                    await cache.set(
                        body.text,
                        {"response": full_response},
                        body.user_id,
                        has_side_effect=has_side_effect,
                    )

                # 流式完成后记录指标 + 持久化聊天日志
                latency = round((time.perf_counter() - start) * 1000, 2)
                REQUEST_COUNT.labels(endpoint="chat", method="POST", status="success").inc()
                REQUEST_LATENCY.labels(endpoint="chat").observe(latency / 1000)
                # 从 expert_results 中提取车控指令的成功/失败状态
                stream_expert_results = state.get("expert_results", [])
                stream_skill_success = True
                if skill_action and skill_action.startswith("vehicle_"):
                    for er in stream_expert_results:
                        if er.get("skill_status") == "error":
                            stream_skill_success = False
                            break
                await _record_chat_metrics(
                    app, cockpit_id, body.user_id, latency, False, skill_action,
                    body.text, full_response,
                    session_id=body.session_id,
                    skill_success=stream_skill_success,
                )

            except Exception as e:
                logger.error(f"Stream failed: {e}")
                err_payload = {
                    'type': 'error',
                    'data': {'message': '服务暂时不可用'},
                }
                yield f"data: {json.dumps(err_payload, ensure_ascii=False)}\n\n"

            finally:
                # 确保会话历史始终被更新，即使流被中断
                if session_store and "history" in state:
                    await session_store.async_set(session_key, state["history"])
                    # 确保滚动摘要也被持久化
                    state_summary = state.get("running_summary", "")
                    if state_summary:
                        await session_store.async_set_summary(session_key, state_summary)
                if "history" in state:
                    app.state.session_histories[session_key] = state["history"][-get_config().memory.max_history_len:]

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
