# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
WebSocket Handler — 实时语音/文本 WebSocket 接口

提供双向实时通信通道，支持流式输出 Agent 回复。
与 SSE (/chat/stream) 的区别:
  - WebSocket 适用于需要双向交互的场景 (如语音对话)
  - SSE 适用于单向流式输出的场景 (如文本对话)

安全特性:
  - 连接时通过 query 参数 token 进行 JWT 认证
  - 30 秒心跳检测，自动清理僵尸连接

事件格式 (统一 JSON):
  {"type": "intent",  "data": {"intent": "..."}}
  {"type": "action",  "data": {"action": "..."}}
  {"type": "chunk",   "data": {"chunk": "..."}}
  {"type": "done",    "data": {"response": "...", "latency_ms": ...}}
  {"type": "error",   "data": {"message": "..."}}
  {"type": "ping",    "data": {"timestamp": ...}}   # 心跳请求
  {"type": "pong",    "data": {"timestamp": ...}}   # 心跳响应
"""

from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from nexus.core.auth import decode_token
from nexus.core.exceptions import AuthError
from nexus.core.logger import get_logger, bind_context, clear_context
from nexus.observability.metrics import ACTIVE_CONNECTIONS

logger = get_logger(__name__)
router = APIRouter()

# 心跳间隔 (秒)
HEARTBEAT_INTERVAL = 30


async def authenticate_websocket(websocket: WebSocket) -> str | None:
    """从 WebSocket 连接的 query 参数中验证 JWT Token。

    WebSocket 无法使用标准 Authorization 头，因此通过 query 参数传递 token:
        ws://host/ws/chat?token=<jwt_token>

    Args:
        websocket: WebSocket 连接对象

    Returns:
        验证通过的用户 ID，验证失败返回 None
    """
    token = websocket.query_params.get("token")
    if not token:
        return None

    try:
        payload = decode_token(token)
        return payload.get("sub")
    except AuthError:
        return None


@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    """WebSocket 文本对话接口。

    认证: 通过 query 参数 token 传递 JWT Token
    心跳: 服务端每 30 秒发送 ping，客户端需回复 pong

    接收 JSON 格式的消息 {"text": "...", "user_id": "...", "session_id": "..."}，
    通过 Agent 工作流处理后，逐块返回流式响应。

    生命周期:
        1. JWT 认证 (失败则关闭连接)
        2. 接受连接，增加活跃连接计数
        3. 启动心跳任务
        4. 循环接收消息，执行 Agent 管道 (规划 → 执行 → 响应 → 审查)
        5. 客户端断开时清理资源
    """
    # --- 认证阶段 ---
    auth_user = await authenticate_websocket(websocket)
    if auth_user is None:
        await websocket.close(code=4001, reason="未认证或 Token 无效")
        return

    await websocket.accept()
    ACTIVE_CONNECTIONS.inc()

    app = websocket.app
    client_id = f"ws_{id(websocket)}"
    bind_context(client_id=client_id)

    # 心跳任务: 定期发送 ping，检测连接是否存活
    async def heartbeat_loop():
        """每 HEARTBEAT_INTERVAL 秒发送一次 ping，若发送失败则连接已断开"""
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                await websocket.send_json({
                    "type": "ping",
                    "data": {"timestamp": time.time()},
                })
        except Exception:
            # 连接已断开，心跳任务自动退出
            pass

    heartbeat_task = asyncio.create_task(heartbeat_loop())

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"error": "Invalid JSON"})
                continue

            # 处理心跳响应
            if data.get("type") == "pong":
                continue

            text = data.get("text", "").strip()
            user_id = data.get("user_id", auth_user)  # 优先使用认证用户 ID
            session_id = data.get("session_id", user_id)

            if not text:
                await websocket.send_json({"error": "Empty text"})
                continue

            logger.info(f"WS message: user={user_id}, text='{text[:50]}'")

            # 限流检查
            rate_limiter = app.state.rate_limiter
            if rate_limiter:
                try:
                    await rate_limiter.check_or_raise(user_id, "ws_chat")
                except Exception as e:
                    await websocket.send_json({"error": str(e)})
                    continue

            # 构建 v2.0 SupervisorState
            from nexus.models.state import create_initial_state

            # 优先从 SessionStore 加载历史 (from main L5 fix)
            session_key = session_id or user_id
            session_store = getattr(app.state, "session_store", None)
            if session_store:
                history = await session_store.async_get(session_key)
            else:
                history = app.state.session_histories.get(session_key, [])

            state = create_initial_state(
                user_input=text,
                user_id=user_id,
                session_id=session_id,
                history=history,
            )

            start = time.perf_counter()

            # v2.0 流式执行（使用 stream_with_events）
            try:
                async for event in app.state.agent_graph.stream_with_events(state):
                    await websocket.send_json(event)

                latency = round((time.perf_counter() - start) * 1000, 2)

                # 更新会话历史 (优先使用 SessionStore, from main L5 fix)
                state_history = state.get("history", [])
                if session_store:
                    await session_store.async_set(session_key, state_history)
                app.state.session_histories[session_key] = state_history[-20:]

            except Exception as e:
                logger.error(f"WS agent error: {e}")
                await websocket.send_json({
                    "type": "error",
                    "data": {"message": str(e)},
                })

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {client_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        heartbeat_task.cancel()
        ACTIVE_CONNECTIONS.dec()
        clear_context()
