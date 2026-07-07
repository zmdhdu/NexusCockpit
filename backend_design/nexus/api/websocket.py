"""
WebSocket Handler — 实时语音/文本 WebSocket 接口
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from nexus.core.logger import get_logger, bind_context, clear_context
from nexus.observability.metrics import ACTIVE_CONNECTIONS

logger = get_logger(__name__)
router = APIRouter()


@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    """WebSocket 文本对话接口"""
    await websocket.accept()
    ACTIVE_CONNECTIONS.inc()

    app = websocket.app
    client_id = f"ws_{id(websocket)}"
    bind_context(client_id=client_id)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"error": "Invalid JSON"})
                continue

            text = data.get("text", "").strip()
            user_id = data.get("user_id", "default")
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

            # 构建 Agent 状态
            from nexus.models.state import AgentState

            state = AgentState(
                user_input=text,
                user_id=user_id,
                session_id=session_id,
                history=app.state.session_histories.get(session_id or user_id, []),
            )

            start = time.perf_counter()

            # 流式执行
            try:
                async for chunk in app.state.agent_graph.stream(state):
                    await websocket.send_json({"type": "chunk", "content": chunk})

                latency = round((time.perf_counter() - start) * 1000, 2)
                await websocket.send_json({
                    "type": "done",
                    "latency_ms": latency,
                    "response": state.final_response,
                })

                # 更新会话历史
                session_key = session_id or user_id
                app.state.session_histories[session_key] = state.history[-20:]

            except Exception as e:
                logger.error(f"WS agent error: {e}")
                await websocket.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {client_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        ACTIVE_CONNECTIONS.dec()
        clear_context()
