# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Chat Session Routes — 多会话管理 REST 接口

v2.2.2 新增:
  - GET    /chat/sessions           — 获取当前座舱的会话列表
  - POST   /chat/sessions           — 创建新会话
  - DELETE /chat/sessions/{id}      — 删除会话
  - GET    /chat/sessions/{id}/messages — 获取会话消息记录

参考豆包/ChatGPT 的多会话交互模式:
  - 用户可以新建对话，每段对话独立保存
  - 侧边栏显示历史会话列表，点击切换
  - 删除会话后不可恢复
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from nexus.core.logger import get_logger
from nexus.core.tenant_context import get_cockpit_id

logger = get_logger(__name__)
router = APIRouter(prefix="/chat/sessions", tags=["chat-sessions"])


class CreateSessionRequest(BaseModel):
    """创建会话请求。"""
    title: str = Field(default="新对话", description="会话标题")
    user_id: str = Field(default="default", description="用户 ID")


class SessionResponse(BaseModel):
    """会话信息响应。"""
    session_id: str
    cockpit_id: str
    user_id: str
    title: str
    message_count: int
    created_at: str
    last_message_at: str


class SessionListResponse(BaseModel):
    """会话列表响应。"""
    total: int
    sessions: List[SessionResponse]


@router.get("", response_model=SessionListResponse)
async def list_sessions(request: Request):
    """获取当前座舱的会话列表。

    按最后消息时间倒序排列，最多返回 50 条。
    """
    cockpit_id = get_cockpit_id()
    db = getattr(request.app.state, "db_manager", None)

    if not db or not db.is_connected:
        return SessionListResponse(total=0, sessions=[])

    try:
        rows = await db.execute_query(
            "SELECT session_id, cockpit_id, user_id, title, message_count, "
            "created_at, last_message_at "
            "FROM chat_sessions "
            "WHERE cockpit_id = %s "
            "ORDER BY last_message_at DESC "
            "LIMIT 50",
            (cockpit_id,),
        )

        sessions = []
        for r in rows:
            sessions.append(SessionResponse(
                session_id=r.get("session_id", ""),
                cockpit_id=r.get("cockpit_id", ""),
                user_id=r.get("user_id", ""),
                title=r.get("title", "新对话"),
                message_count=r.get("message_count", 0),
                created_at=r["created_at"].isoformat() if isinstance(r.get("created_at"), datetime) else str(r.get("created_at", "")),
                last_message_at=r["last_message_at"].isoformat() if isinstance(r.get("last_message_at"), datetime) else str(r.get("last_message_at", "")),
            ))

        return SessionListResponse(total=len(sessions), sessions=sessions)
    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        return SessionListResponse(total=0, sessions=[])


@router.post("", response_model=SessionResponse)
async def create_session(request: Request, body: CreateSessionRequest):
    """创建新会话。

    返回新会话的 session_id，前端用此 ID 发送消息。
    """
    cockpit_id = get_cockpit_id()
    session_id = f"sess_{uuid.uuid4().hex[:16]}"

    db = getattr(request.app.state, "db_manager", None)
    if db and db.is_connected:
        try:
            await db.execute_update(
                "INSERT INTO chat_sessions (session_id, cockpit_id, user_id, title, message_count, last_message_at) "
                "VALUES (%s, %s, %s, %s, 0, NOW())",
                (session_id, cockpit_id, body.user_id, body.title),
            )
        except Exception as e:
            logger.error(f"Failed to create session: {e}")

    return SessionResponse(
        session_id=session_id,
        cockpit_id=cockpit_id,
        user_id=body.user_id,
        title=body.title,
        message_count=0,
        created_at=datetime.now().isoformat(),
        last_message_at=datetime.now().isoformat(),
    )


@router.delete("/{session_id}")
async def delete_session(request: Request, session_id: str):
    """删除会话及其所有消息记录。"""
    cockpit_id = get_cockpit_id()
    db = getattr(request.app.state, "db_manager", None)

    if not db or not db.is_connected:
        return {"success": False, "message": "数据库未连接"}

    try:
        # 删除会话记录
        await db.execute_update(
            "DELETE FROM chat_sessions WHERE session_id = %s AND cockpit_id = %s",
            (session_id, cockpit_id),
        )
        # 删除该会话的所有聊天日志
        await db.execute_update(
            "DELETE FROM chat_logs WHERE session_id = %s AND cockpit_id = %s",
            (session_id, cockpit_id),
        )
        return {"success": True, "message": "会话已删除"}
    except Exception as e:
        logger.error(f"Failed to delete session: {e}")
        return {"success": False, "message": str(e)}


@router.get("/{session_id}/messages")
async def get_session_messages(request: Request, session_id: str):
    """获取指定会话的所有消息记录。

    返回按时间正序排列的消息列表。
    """
    cockpit_id = get_cockpit_id()
    db = getattr(request.app.state, "db_manager", None)

    if not db or not db.is_connected:
        return {"messages": []}

    try:
        rows = await db.execute_query(
            "SELECT user_input, assistant_response, intent, action, "
            "latency_ms, cache_hit, created_at "
            "FROM chat_logs "
            "WHERE session_id = %s AND cockpit_id = %s "
            "ORDER BY created_at ASC",
            (session_id, cockpit_id),
        )

        messages = []
        for r in rows:
            created_at = r.get("created_at")
            ts = created_at.isoformat() if isinstance(created_at, datetime) else str(created_at or "")
            # 用户消息
            messages.append({
                "role": "user",
                "content": r.get("user_input", ""),
                "timestamp": ts,
                "intent": r.get("intent", ""),
                "action": r.get("action", ""),
            })
            # 助手回复
            messages.append({
                "role": "assistant",
                "content": r.get("assistant_response", ""),
                "timestamp": ts,
                "intent": r.get("intent", ""),
                "action": r.get("action", ""),
            })

        return {"messages": messages}
    except Exception as e:
        logger.error(f"Failed to get session messages: {e}")
        return {"messages": []}
