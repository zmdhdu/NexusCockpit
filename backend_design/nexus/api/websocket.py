"""
WebSocket Handler — 实时语音/文本 WebSocket 接口

提供双向实时通信通道，支持流式输出 Agent 回复。
与 SSE (/chat/stream) 的区别:
  - WebSocket 适用于需要双向交互的场景 (如语音对话)
  - SSE 适用于单向流式输出的场景 (如文本对话)

事件格式 (统一 JSON):
  {"type": "intent",  "data": {"intent": "..."}}
  {"type": "action",  "data": {"action": "..."}}
  {"type": "chunk",   "data": {"chunk": "..."}}
  {"type": "done",    "data": {"response": "...", "latency_ms": ...}}
  {"type": "error",   "data": {"message": "..."}}
"""

from __future__ import annotations

import json
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from nexus.core.logger import get_logger, bind_context, clear_context
from nexus.observability.metrics import ACTIVE_CONNECTIONS

logger = get_logger(__name__)
router = APIRouter()


@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    """WebSocket 文本对话接口。

    接收 JSON 格式的消息 {"text": "...", "user_id": "...", "session_id": "..."}，
    通过 Agent 工作流处理后，逐块返回流式响应。

    生命周期:
        1. 接受连接，增加活跃连接计数
        2. 循环接收消息，执行 Agent 管道 (规划 → 执行 → 响应 → 审查)
        3. 客户端断开时清理资源
    """
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
                # Phase 1: 规划
                state = await app.state.agent_graph.planner.plan(state)

                # 发送意图事件
                if state.intent:
                    await websocket.send_json({
                        "type": "intent",
                        "data": {"intent": state.intent.get("Route_Source", "")},
                    })

                # Phase 2: 澄清分支
                if state.need_clarification and state.clarification_prompt:
                    await websocket.send_json({
                        "type": "chunk",
                        "data": {"chunk": state.clarification_prompt},
                    })
                    state.final_response = state.clarification_prompt
                    await app.state.agent_graph.reviewer.review(state)

                # Phase 3: 执行技能 + 流式响应
                else:
                    state = await app.state.agent_graph.executor.execute(state)

                    # 发送技能动作事件
                    if state.skill_action:
                        await websocket.send_json({
                            "type": "action",
                            "data": {"action": state.skill_action},
                        })

                    # 流式输出
                    async for chunk in app.state.agent_graph.responder.stream_respond(state):
                        await websocket.send_json({
                            "type": "chunk",
                            "data": {"chunk": chunk},
                        })

                    # 审查后处理
                    await app.state.agent_graph.reviewer.review(state)

                latency = round((time.perf_counter() - start) * 1000, 2)

                # 确保 final_response 不为空
                final_response = state.final_response or "抱歉，处理超时，请重试。"
                await websocket.send_json({
                    "type": "done",
                    "data": {
                        "response": final_response,
                        "latency_ms": latency,
                        "intent": state.intent.get("Route_Source", "") if state.intent else "",
                        "action": state.skill_action or "",
                    },
                })

                # 更新会话历史
                session_key = session_id or user_id
                app.state.session_histories[session_key] = state.history[-20:]

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
        ACTIVE_CONNECTIONS.dec()
        clear_context()
