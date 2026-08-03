# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Chat Routes — 文本对话 REST + SSE 接口

作用：SupervisorGraph 多智能体编排 + SSE 流式事件 + checkpoint 持久化 + 语义缓存 + 座舱级指标记录；
场景：车载语音对话的 REST 与 SSE 流式接口。
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


def _store_client_ip_in_adapter(request: Request, cockpit_id: str) -> None:
    """从请求中提取客户端 IP 并存入 vehicle adapter，供 IP 定位使用。

    优先级:
        1. X-Forwarded-For 头（经过 Go 网关代理时设置）
        2. request.client.host（直连 FastAPI 时的客户端 IP）

    场景: 用户浏览器 GPS 定位失败时，后端 IP 定位会使用此 IP，
    而非服务器自身的 IP（服务器可能在北京，但用户在杭州）。
    """
    try:
        # 优先从 X-Forwarded-For 获取（Go 网关代理时会设置）
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else ""

        if not client_ip or client_ip in ("127.0.0.1", "localhost", "::1"):
            return  # 本地回环地址不存储

        if cockpit_id:
            from nexus.vehicle.factory import get_cockpit_vehicle_adapter
            adapter = get_cockpit_vehicle_adapter(cockpit_id)
            if adapter and hasattr(adapter, "navigation"):
                adapter.navigation["client_ip"] = client_ip
    except Exception as e:
        logger.debug(f"Failed to store client IP in adapter: {e}")

# 车控意图字段集合 — 命中其中任一即为车控指令（常量来自 nexus.intent.constants）

# 上下文敏感关键词 — 这类查询的答案依赖于对话上下文（位置/时间/历史），
# 缓存命中可能返回错误的上下文信息，因此跳过缓存
_CONTEXT_SENSITIVE_KEYWORDS = (
    # 时间相关（答案随时变化）
    "天气", "温度", "明天", "后天", "今天", "昨天",
    "这周", "下周", "上周", "这月", "下月", "现在",
    # 位置相关（答案依赖用户当前位置）
    "附近", "周边", "周围",
    # 历史相关（答案依赖对话上下文）
    "我之前", "上次", "你刚说", "我们聊了", "还记得",
    # 推荐类（答案依赖用户偏好/历史）
    "推荐", "建议",
)


def _is_context_sensitive(text: str) -> bool:
    """检查查询是否为上下文敏感型，这类查询不应命中缓存。

    天气/周边/推荐等查询的答案依赖于用户当前位置和对话历史，
    缓存命中可能返回错误的上下文信息（例如不同城市/不同偏好）。
    """
    return any(kw in text for kw in _CONTEXT_SENSITIVE_KEYWORDS)


def _is_vehicle_command(text: str) -> bool:
    """检查文本是否为车控指令。

    使用启发式路由器快速判断，如果命中车控意图则跳过缓存，
    确保车控命令每次都实际执行而非返回旧缓存。
    """
    quick = _heuristic_router.route(text)
    return any(k in quick for k in VEHICLE_INTENT_KEYS)


# ---- 以下为 chat() 和 chat_stream() 共用的辅助函数 (S2-S3 重构) ----

async def _check_semantic_cache(
    cache, user_id: str, text: str, is_vehicle_cmd: bool,
) -> dict | None:
    """语义缓存查询 — 车控指令和上下文敏感查询跳过缓存。

    chat() 和 chat_stream() 的公共缓存查询逻辑。

    跳过缓存的场景:
        1. 车控指令 — 必须每次实际执行
        2. 上下文敏感查询 — 答案依赖于对话历史/位置/时间，缓存可能返回错误信息

    Returns:
        命中缓存时返回 {"response": str, ...}，未命中返回 None。
    """
    # 上下文敏感查询检查（天气/附近/推荐等依赖对话上下文的查询）
    is_ctx_sensitive = _is_context_sensitive(text)

    if not cache or not cache.is_enabled or is_vehicle_cmd or is_ctx_sensitive:
        if cache and cache.is_enabled:
            if is_vehicle_cmd:
                CACHE_MISSES.inc()
                logger.info(f"Vehicle command detected, skipping cache: '{text[:50]}'")
            elif is_ctx_sensitive:
                CACHE_MISSES.inc()
                logger.info(f"Context-sensitive query, skipping cache: '{text[:50]}'")
        return None

    cached = await cache.get(text, user_id)
    if cached:
        CACHE_HITS.inc()
        REQUEST_COUNT.labels(endpoint="chat", method="POST", status="cache_hit").inc()
        return cached

    CACHE_MISSES.inc()
    return None


async def _async_load_session_history(
    app, session_key: str,
) -> tuple[list, str]:
    """异步加载会话历史和滚动摘要。

    优先从 SessionStore (Redis) 加载，不可用时回退到内存 dict。
    chat() 和 chat_stream() 的公共历史加载逻辑。

    Returns:
        (history_list, running_summary_str)
    """
    session_store = getattr(app.state, "session_store", None)
    if session_store:
        history = await session_store.async_get(session_key)
        running_summary = await session_store.async_get_summary(session_key)
        return history, running_summary
    return app.state.session_histories.get(session_key, []), ""


async def _save_session_history(
    app, session_key: str, state: dict,
) -> None:
    """保存会话历史和滚动摘要。

    优先使用 SessionStore (Redis) 持久化，不可用时回退到内存 dict。
    chat() 和 chat_stream() 的公共历史保存逻辑。
    """
    session_store = getattr(app.state, "session_store", None)
    state_history = state.get("history", [])
    if session_store:
        await session_store.async_set(session_key, state_history)
        state_summary = state.get("running_summary", "")
        if state_summary:
            await session_store.async_set_summary(session_key, state_summary)
    else:
        app.state.session_histories[session_key] = state_history[-get_config().memory.max_history_len:]


async def _write_cache(
    cache, user_id: str, text: str, response: str,
    has_side_effect: bool, session_id: str = "",
) -> None:
    """写入语义缓存 — 有副作用和上下文敏感的响应禁止缓存。

    chat() 和 chat_stream() 的公共缓存写入逻辑。
    """
    # 上下文敏感查询不写入缓存，避免后续类似查询命中错误上下文的缓存
    if _is_context_sensitive(text):
        return
    if cache and cache.is_enabled and response and not has_side_effect:
        await cache.set(
            text,
            {"response": response},
            user_id,
            has_side_effect=has_side_effect,
            session_id=session_id,
        )


def _extract_skill_success(state: dict) -> bool:
    """从 expert_results 中提取车控指令的成功/失败状态。

    chat() 和 chat_stream() 的公共技能状态提取逻辑。
    """
    skill_action = state.get("skill_action", "")
    if not skill_action or not skill_action.startswith("vehicle_"):
        return True
    for er in state.get("expert_results", []):
        if er.get("skill_status") == "error":
            return False
    return True


# 会话级别并发锁 — 防止同一 session 的并发请求交叉污染会话历史
# 当用户快速连续发送多条消息时，确保前一条处理完再处理下一条
# 增加上限防止内存泄漏，超过阈值时清理空闲锁
_session_locks: dict[str, asyncio.Lock] = {}
_config = get_config()
_SESSION_LOCKS_MAX = _config.server.session_locks_max


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
    """文本对话 (非流式)：作用：限流→缓存→Supervisor执行→指标→日志→缓存写入→返回；场景：非流式对话请求。

    Args:
        request: FastAPI 请求对象
        body: 包含 text、user_id、session_id 的请求体

    Returns:
        ChatResponse 包含回复文本和延迟信息
    """
    start = time.perf_counter()
    app = request.app
    cockpit_id = get_cockpit_id()

    # 存储客户端 IP 到 vehicle adapter，供 IP 定位使用
    _store_client_ip_in_adapter(request, cockpit_id)

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
    cached = await _check_semantic_cache(cache, body.user_id, body.text, is_vehicle_cmd)
    if cached:
        latency = round((time.perf_counter() - start) * 1000, 2)
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

    # 构建 SupervisorState 并执行
    agent_graph = app.state.agent_graph
    if agent_graph is None:
        # Agent 图未初始化（通常是 Milvus/Neo4j 等基础设施未启动）
        logger.error("Agent graph is None, cannot process chat request")
        return ChatResponse(
            response="服务初始化中，请稍后重试。如果问题持续，请检查后端基础设施（Milvus/Neo4j/Redis）是否已启动。",
            user_id=body.user_id,
            session_id=body.session_id,
            latency_ms=0,
            metadata={"error": "agent_not_initialized"},
        )
    # session_id 为空时生成唯一临时 ID，禁止回退到 user_id
    # 回退到 user_id 会导致同一用户的所有对话共享历史，破坏会话隔离
    session_key = body.session_id or f"temp_{uuid.uuid4().hex[:16]}"

    # 获取会话锁，防止同一 session 的并发请求交叉污染历史
    session_lock = _get_session_lock(session_key)

    async with session_lock:
        # 在锁内读取历史，确保不会读到并发请求的中间状态
        history, running_summary = await _async_load_session_history(app, session_key)

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

        # 更新会话历史 (优先使用 SessionStore 持久化)
        await _save_session_history(app, session_key, state)

    # 写入缓存 — 有副作用的响应（如车控指令）禁止缓存，避免命中缓存后车控不执行
    final_response = state.get("final_response", "")
    has_side_effect = state.get("has_side_effect", False)
    skill_action = state.get("skill_action", "")
    await _write_cache(cache, body.user_id, body.text, final_response, has_side_effect, session_id=body.session_id)

    latency = round((time.perf_counter() - start) * 1000, 2)
    REQUEST_COUNT.labels(endpoint="chat", method="POST", status="success").inc()
    REQUEST_LATENCY.labels(endpoint="chat").observe(latency / 1000)

    # 记录指标 + 持久化聊天日志
    # 从 expert_results 中提取车控指令的成功/失败状态
    skill_success = _extract_skill_success(state)
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

    # 存储客户端 IP 到 vehicle adapter，供 IP 定位使用
    _store_client_ip_in_adapter(request, cockpit_id)

    async def event_generator():
        """SSE 事件生成器 — 通过 GenerationTaskPool 托管 pipeline。

        底层修复: 原实现 SSE 连接直接绑定 pipeline 执行，
        客户端断连即中断 pipeline。
        现改为: pipeline 在后台 Task 中独立运行，SSE 仅从事件队列读取。
        客户端断连仅停止读取，pipeline 继续运行，结果由 finally 块持久化。
        """
        agent_graph = app.state.agent_graph
        if agent_graph is None:
            logger.error("Agent graph is None, cannot process stream request")
            err_payload = {
                'type': 'error',
                'data': {
                    'message': (
                        '服务初始化中，请稍后重试。'
                        '如果问题持续，请检查后端基础设施（Milvus/Neo4j/Redis）是否已启动。'
                    ),
                    'reason': 'agent_not_initialized',
                },
            }
            yield f"data: {json.dumps(err_payload, ensure_ascii=False)}\n\n"
            return
        # session_id 为空时生成唯一临时 ID，禁止回退到 user_id
        session_key = body.session_id or f"temp_{uuid.uuid4().hex[:16]}"
        start = time.perf_counter()

        # 心跳保活: 按配置间隔发送 SSE 注释行，防止连接超时断开
        _heartbeat_interval = get_config().server.sse_heartbeat_interval
        _last_heartbeat = time.monotonic()

        # 语义缓存检查 — 车控指令跳过缓存
        is_vehicle_cmd = _is_vehicle_command(body.text)
        cache = app.state.semantic_cache
        cached = await _check_semantic_cache(cache, body.user_id, body.text, is_vehicle_cmd)
        if cached:
            latency = round((time.perf_counter() - start) * 1000, 2)
            cached_response = cached.get("response", "")
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

        # 获取会话锁
        session_lock = _get_session_lock(session_key)

        async with session_lock:
            # 在锁内读取历史
            history, running_summary = await _async_load_session_history(app, session_key)

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

            # ---- 使用 GenerationTaskPool 托管 pipeline ----
            # pipeline 在后台 Task 中独立运行，脱离 SSE 连接生命周期
            task_pool = getattr(app.state, "task_pool", None)

            try:
                if task_pool is not None:
                    # ---- 新路径: 通过任务池托管 pipeline ----
                    task_id = await task_pool.submit(state)

                    # SSE 从任务池事件队列读取（客户端断连仅停止读取，不终止 pipeline）
                    async for event in task_pool.consume_events(task_id):
                        if event.get("type") == "done":
                            full_response = event.get("data", {}).get("response", "")
                            skill_action = event.get("data", {}).get("action", "")

                        # 心跳保活: 超过间隔时间时先发送 SSE 注释行
                        _now = time.monotonic()
                        if _now - _last_heartbeat >= _heartbeat_interval:
                            yield ": heartbeat\n\n"
                            _last_heartbeat = _now

                        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

                else:
                    # ---- 降级路径: 任务池不可用时回退到直接流式 ----
                    async for event in agent_graph.stream_with_events(state):
                        if event.get("type") == "done":
                            full_response = event.get("data", {}).get("response", "")
                            skill_action = event.get("data", {}).get("action", "")

                        _now = time.monotonic()
                        if _now - _last_heartbeat >= _heartbeat_interval:
                            yield ": heartbeat\n\n"
                            _last_heartbeat = _now

                        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

                # 更新会话历史
                await _save_session_history(app, session_key, state)

                # 写入缓存
                has_side_effect = state.get("has_side_effect", False)
                await _write_cache(
                    cache, body.user_id, body.text,
                    full_response, has_side_effect,
                    session_id=body.session_id,
                )

                # 流式完成后记录指标 + 持久化聊天日志
                latency = round((time.perf_counter() - start) * 1000, 2)
                REQUEST_COUNT.labels(endpoint="chat", method="POST", status="success").inc()
                REQUEST_LATENCY.labels(endpoint="chat").observe(latency / 1000)
                stream_skill_success = _extract_skill_success(state)
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
                if "history" in state:
                    await _save_session_history(app, session_key, state)

                # ---- 成对写入保障：AI 应答必须持久化到 chat_logs ----
                # 底层修复: 原实现在 SSE 流中断时 full_response 可能为空，
                # 导致 chat_logs 只写入 user_input 而 assistant_response 为空字符串。
                # 现在代码层面强制保障：即使回复为空也填充兜底话术，确保成对写入。
                if not full_response:
                    full_response = state.get("final_response", "")
                if not full_response:
                    # 流被中断且 pipeline 未完成 — 填充安全兜底话术
                    full_response = "（生成被中断，请重新发送消息）"
                    logger.warning(
                        f"Stream interrupted with empty response, applied fallback: "
                        f"session={body.session_id}"
                    )

                # 强制持久化 chat_logs（无论流是否正常完成）
                try:
                    latency = round((time.perf_counter() - start) * 1000, 2)
                    fallback_skill = state.get("skill_action", "") or skill_action
                    await _record_chat_metrics(
                        app, cockpit_id, body.user_id, latency, False,
                        fallback_skill, body.text, full_response,
                        session_id=body.session_id,
                        skill_success=_extract_skill_success(state),
                    )
                    logger.info(
                        f"Chat log persisted (finally block): "
                        f"session={body.session_id}, response_len={len(full_response)}"
                    )
                except Exception as e:
                    logger.error(f"Failed to persist chat log on stream interrupt: {e}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Heartbeat-Interval": "15",
        },
    )


@router.post("/cancel")
async def cancel_generation(request: Request, body: ChatRequest):
    """取消正在进行的 AI 生成任务。

    仅用户主动点击【暂停生成】按钮时调用此接口。
    页面切换/组件卸载不会调用此接口，pipeline 继续在后台运行。

    底层逻辑:
        - 通过 GenerationTaskPool.cancel_task() 终止后台 asyncio.Task
        - 前端 AbortController 仅断开 SSE 读取，不终止 pipeline
        - 必须调用此接口才能真正终止 pipeline
    """
    app = request.app
    task_pool = getattr(app.state, "task_pool", None)
    if task_pool is None:
        return {"success": False, "message": "任务池未初始化"}

    # 查找当前用户的运行中任务
    cancelled = False
    for task_id, gen_task in task_pool._tasks.items():
        if gen_task.user_id == body.user_id and gen_task.status == "running":
            cancelled = task_pool.cancel_task(task_id)
            if cancelled:
                logger.info(f"Generation cancelled by user: task_id={task_id}, user={body.user_id}")
                break

    if cancelled:
        return {"success": True, "message": "生成已取消"}
    else:
        return {"success": False, "message": "没有正在运行的生成任务"}
