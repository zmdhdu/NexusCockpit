# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Chat Session Routes — 多会话管理 REST 接口

接口列表:
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
    sessions: list[SessionResponse]


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
                created_at=(
                    r["created_at"].isoformat()
                    if isinstance(r.get("created_at"), datetime)
                    else str(r.get("created_at", ""))
                ),
                last_message_at=(
                    r["last_message_at"].isoformat()
                    if isinstance(r.get("last_message_at"), datetime)
                    else str(r.get("last_message_at", ""))
                ),
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
    """删除会话及其所有关联数据（会话级资源完整清理）。

    精确清理会话级资源，保留跨会话共享资源:
      1. MySQL chat_sessions 表 — 会话元数据
      2. MySQL chat_logs 表 — 聊天日志记录
      3. Redis SessionStore — 短期对话历史 + 滚动摘要（nexus:session:{session_id}）
      4. 内存 session_histories — 内存中的会话历史 dict（降级模式残留）
      5. LangGraph checkpoint — SQLite 中的 Agent 状态快照（thread_id = session_id）
      6. 会话并发锁 — chat.py 中 _session_locks 的会话级锁
      7. 语义缓存 — Redis 中该会话产生的缓存条目（按 session_id 精确清理）
      8. 会话级记忆 — Milvus 中该会话的对话向量（按 session_id 精确清理）

    跨会话共享资源（按 user_id 隔离，不随单个会话删除）:
      - 用户级记忆（Milvus 提取的事实/偏好）— session_id 为空的记忆条目
      - Neo4j 图谱关系 — 用户级知识图谱
      - 用户习惯（MySQL user_habits）— 使用频次统计

    Args:
        session_id: 会话 ID
    """
    cockpit_id = get_cockpit_id()
    app = request.app
    db = getattr(app.state, "db_manager", None)

    if not db or not db.is_connected:
        return {"success": False, "message": "数据库未连接"}

    cleanup_details = {}

    try:
        # 0. 先查询会话对应的 user_id（删除前获取，用于后续语义缓存精确清理）
        session_rows = await db.execute_query(
            "SELECT user_id FROM chat_sessions WHERE session_id = %s AND cockpit_id = %s",
            (session_id, cockpit_id),
        )
        mysql_already_absent = not session_rows
        if mysql_already_absent:
            # 会话在 MySQL 中不存在（可能是创建时 INSERT 失败但已返回 session_id，
            # 或已被其他途径删除）。DELETE 是幂等操作，仍需清理 Redis/checkpoint/
            # 内存等残留资源，然后返回成功，避免前端"幽灵会话"无法删除。
            logger.warning(
                f"Session {session_id} not found in MySQL (cockpit={cockpit_id}), "
                f"proceeding with best-effort cleanup of remaining resources"
            )
            user_id = ""
            cleanup_details["mysql"] = "already_absent"
        else:
            user_id = session_rows[0].get("user_id", "")

            # 1. 事务删除 MySQL 会话记录 + 聊天日志（原子性保障，防部分删除）
            try:
                async with db._get_conn() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(
                            "DELETE FROM chat_sessions WHERE session_id = %s AND cockpit_id = %s",
                            (session_id, cockpit_id),
                        )
                        sessions_deleted = cur.rowcount
                        await cur.execute(
                            "DELETE FROM chat_logs WHERE session_id = %s AND cockpit_id = %s",
                            (session_id, cockpit_id),
                        )
                        logs_deleted = cur.rowcount
                        await conn.commit()
                    cleanup_details["mysql"] = (
                        f"deleted ({sessions_deleted} sessions, {logs_deleted} logs)"
                    )
            except Exception as e:
                logger.error(f"MySQL transaction delete failed for session {session_id}: {e}")
                cleanup_details["mysql"] = f"error: {e}"
                # MySQL 删除失败则中止，避免缓存/记忆层先删导致数据不一致
                return {"success": False, "message": f"数据库删除失败: {e}"}

        # 3. 删除 Redis 短期对话历史 + 滚动摘要（SessionStore）
        session_store = getattr(app.state, "session_store", None)
        if session_store:
            try:
                deleted = await session_store.async_delete(session_id)
                cleanup_details["session_store"] = "deleted" if deleted else "not_found"
            except Exception as e:
                logger.warning(f"Failed to delete SessionStore for session {session_id}: {e}")
                cleanup_details["session_store"] = f"error: {e}"

        # 4. 删除内存会话历史（session_histories dict，降级模式残留）
        session_histories = getattr(app.state, "session_histories", None)
        if session_histories is not None and session_id in session_histories:
            del session_histories[session_id]
            cleanup_details["session_histories"] = "deleted"
        else:
            cleanup_details["session_histories"] = "not_found"

        # 5. 删除 LangGraph checkpoint（SQLite 中的 Agent 状态快照）
        # AsyncSqliteSaver 不支持 adelete 方法，需直接通过 SQL 删除
        checkpoint_conn = getattr(app.state, "_checkpoint_conn", None)
        if checkpoint_conn:
            try:
                # langgraph checkpoint 表结构:
                #   checkpoints(thread_id, checkpoint_ns, checkpoint_id, ...)
                #   writes(thread_id, checkpoint_ns, checkpoint_id, ...)
                # thread_id = session_id
                cursor = await checkpoint_conn.execute(
                    "DELETE FROM writes WHERE thread_id = ?", (session_id,)
                )
                writes_deleted = cursor.rowcount
                cursor = await checkpoint_conn.execute(
                    "DELETE FROM checkpoints WHERE thread_id = ?", (session_id,)
                )
                checkpoints_deleted = cursor.rowcount
                await checkpoint_conn.commit()
                cleanup_details["checkpoint"] = (
                    f"deleted ({checkpoints_deleted} checkpoints, {writes_deleted} writes)"
                    if checkpoints_deleted or writes_deleted
                    else "not_found"
                )
                logger.info(
                    f"Checkpoint deleted for session {session_id}: "
                    f"{checkpoints_deleted} checkpoints, {writes_deleted} writes"
                )
            except Exception as e:
                logger.warning(f"Failed to delete checkpoint for session {session_id}: {e}")
                cleanup_details["checkpoint"] = f"error: {e}"
        else:
            cleanup_details["checkpoint"] = "disabled"

        # 6. 清理会话并发锁（chat.py 中的 _session_locks）
        # 会话锁按 session_key 存储在全局 dict 中，删除会话后锁应释放
        try:
            from nexus.api.routes.chat import _session_locks
            if session_id in _session_locks:
                lock = _session_locks[session_id]
                if not lock.locked():
                    del _session_locks[session_id]
                    cleanup_details["session_lock"] = "deleted"
                else:
                    # 锁正在使用中（可能有正在处理的请求），不强制删除
                    cleanup_details["session_lock"] = "in_use (will be cleaned by GC)"
            else:
                cleanup_details["session_lock"] = "not_found"
        except Exception as e:
            logger.warning(f"Failed to clean session lock for {session_id}: {e}")
            cleanup_details["session_lock"] = f"error: {e}"

        # 7. 清理语义缓存（Redis 中该会话产生的缓存条目）
        # 按 session_id 精确清理，不影响同一用户其他会话的缓存
        semantic_cache = getattr(app.state, "semantic_cache", None)
        if semantic_cache:
            try:
                cache_deleted = await semantic_cache.delete_by_session(session_id, user_id)
                cleanup_details["semantic_cache"] = (
                    f"deleted ({cache_deleted} entries)" if cache_deleted else "not_found"
                )
            except Exception as e:
                logger.warning(f"Failed to delete semantic cache for session {session_id}: {e}")
                cleanup_details["semantic_cache"] = f"error: {e}"
        else:
            cleanup_details["semantic_cache"] = "disabled"

        # 8. 清理会话级记忆（Milvus 中该会话的对话向量）
        # 仅删除 session_id 匹配的对话向量，保留用户级记忆（提取的事实/偏好）
        memory_manager = getattr(app.state, "memory_manager", None)
        if memory_manager:
            try:
                memories_deleted = memory_manager.delete_session_memories(session_id, user_id)
                cleanup_details["session_memories"] = (
                    f"deleted ({memories_deleted} vectors)" if memories_deleted else "not_found"
                )
            except Exception as e:
                logger.warning(f"Failed to delete session memories for session {session_id}: {e}")
                cleanup_details["session_memories"] = f"error: {e}"
        else:
            cleanup_details["session_memories"] = "disabled"

        logger.info(
            f"Session deleted: session_id={session_id}, cockpit_id={cockpit_id}, "
            f"cleanup={cleanup_details}"
        )

        return {
            "success": True,
            "message": "会话已删除，所有会话级资源已清理",
            "cleanup_details": cleanup_details,
        }
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


class UpdateTitleRequest(BaseModel):
    """更新会话标题请求。"""
    title: str = Field(..., max_length=100, description="新的会话标题")


@router.patch("/{session_id}/title")
async def update_session_title(request: Request, session_id: str, body: UpdateTitleRequest):
    """更新会话标题。

    用于前端在首次消息后将会话标题从"新对话"更新为用户问题摘要（豆包风格）。
    """
    cockpit_id = get_cockpit_id()
    db = getattr(request.app.state, "db_manager", None)

    if not db or not db.is_connected:
        return {"success": False, "message": "数据库未连接"}

    try:
        await db.execute_update(
            "UPDATE chat_sessions SET title = %s WHERE session_id = %s AND cockpit_id = %s",
            (body.title[:100], session_id, cockpit_id),
        )
        return {"success": True, "title": body.title[:100]}
    except Exception as e:
        logger.error(f"Failed to update session title: {e}")
        return {"success": False, "message": str(e)}


@router.get("/consistency-check")
async def storage_consistency_check(request: Request):
    """存储一致性自检接口 — 主动扫描孤立数据、僵尸缓存、残留文件。

    检查项目:
      1. MySQL chat_logs 中存在但 chat_sessions 中已删除的孤立日志（session_id 不匹配）
      2. Redis 语义缓存中 session_id 不存在于 MySQL chat_sessions 的僵尸缓存
      3. LangGraph checkpoint 中 thread_id 不存在于 MySQL chat_sessions 的僵尸快照
      4. Milvus 会话级记忆中 session_id 不存在于 MySQL chat_sessions 的孤儿向量

    Returns:
        各存储层的一致性状态报告
    """
    cockpit_id = get_cockpit_id()
    app = request.app
    db = getattr(app.state, "db_manager", None)

    if not db or not db.is_connected:
        return {"success": False, "message": "数据库未连接"}

    report = {"cockpit_id": cockpit_id, "issues": [], "summary": {}}

    try:
        # 获取当前座舱所有有效 session_id
        valid_sessions = await db.execute_query(
            "SELECT session_id FROM chat_sessions WHERE cockpit_id = %s",
            (cockpit_id,),
        )
        valid_session_ids = {r["session_id"] for r in valid_sessions}
        report["summary"]["valid_sessions"] = len(valid_session_ids)

        # 1. 检查 MySQL chat_logs 中的孤立日志
        orphan_logs = await db.execute_query(
            "SELECT DISTINCT session_id FROM chat_logs WHERE cockpit_id = %s",
            (cockpit_id,),
        )
        orphan_log_sessions = {
            r["session_id"] for r in orphan_logs if r["session_id"]
        } - valid_session_ids
        if orphan_log_sessions:
            report["issues"].append({
                "type": "orphan_chat_logs",
                "severity": "medium",
                "description": f"chat_logs 中有 {len(orphan_log_sessions)} 个 session_id 不存在于 chat_sessions",
                "orphan_session_ids": list(orphan_log_sessions)[:20],
                "suggested_action": (
                    "执行 DELETE FROM chat_logs "
                    "WHERE session_id NOT IN (SELECT session_id FROM chat_sessions)"
                ),
            })
        report["summary"]["orphan_chat_logs"] = len(orphan_log_sessions)

        # 2. 检查 Redis 语义缓存中的僵尸缓存
        semantic_cache = getattr(app.state, "semantic_cache", None)
        zombie_cache_count = 0
        if semantic_cache and semantic_cache.is_enabled:
            try:
                redis_client = semantic_cache._redis
                if redis_client:
                    async for key in redis_client.scan_iter(match="nexus:cache:entry:*", count=100):
                        cached_session = await redis_client.hget(key, "session_id")
                        if cached_session and cached_session not in valid_session_ids:
                            zombie_cache_count += 1
            except Exception as e:
                logger.warning(f"Semantic cache scan failed: {e}")
        if zombie_cache_count > 0:
            report["issues"].append({
                "type": "zombie_semantic_cache",
                "severity": "low",
                "description": f"Redis 语义缓存中有 {zombie_cache_count} 个条目的 session_id 不存在于 chat_sessions",
                "suggested_action": "这些缓存有 TTL 会自动过期，或调用 delete_by_session 手动清理",
            })
        report["summary"]["zombie_cache_entries"] = zombie_cache_count

        # 3. 检查 LangGraph checkpoint 中的僵尸快照
        checkpoint_conn = getattr(app.state, "_checkpoint_conn", None)
        zombie_checkpoint_count = 0
        if checkpoint_conn:
            try:
                cursor = await checkpoint_conn.execute(
                    "SELECT DISTINCT thread_id FROM checkpoints"
                )
                rows = await cursor.fetchall()
                checkpoint_thread_ids = {row[0] for row in rows}
                zombie_checkpoint_count = len(checkpoint_thread_ids - valid_session_ids)
            except Exception as e:
                logger.warning(f"Checkpoint scan failed: {e}")
        if zombie_checkpoint_count > 0:
            report["issues"].append({
                "type": "zombie_checkpoints",
                "severity": "medium",
                "description": (
                    f"LangGraph checkpoint 中有 {zombie_checkpoint_count} 个 "
                    f"thread_id 不存在于 chat_sessions"
                ),
                "suggested_action": "执行 DELETE FROM checkpoints WHERE thread_id NOT IN (valid session_ids)",
            })
        report["summary"]["zombie_checkpoints"] = zombie_checkpoint_count

        # 4. 检查 Milvus 会话级记忆中的孤儿向量
        memory_manager = getattr(app.state, "memory_manager", None)
        orphan_milvus_count = 0
        if memory_manager and memory_manager.vector_store._client:
            try:
                result = memory_manager.vector_store._client.query(
                    collection_name=memory_manager.vector_store.config.collection_memory,
                    filter='session_id != ""',
                    output_fields=["session_id"],
                    limit=16384,
                )
                milvus_session_ids = {r.get("session_id", "") for r in (result or [])}
                orphan_milvus_count = len(milvus_session_ids - valid_session_ids)
            except Exception as e:
                logger.warning(f"Milvus scan failed: {e}")
        if orphan_milvus_count > 0:
            report["issues"].append({
                "type": "orphan_milvus_memories",
                "severity": "low",
                "description": f"Milvus 中有 {orphan_milvus_count} 个会话级向量的 session_id 不存在于 chat_sessions",
                "suggested_action": "调用 delete_memory_by_session 逐个清理，或批量清理孤立 session_id 的向量",
            })
        report["summary"]["orphan_milvus_memories"] = orphan_milvus_count

        report["success"] = True
        report["healthy"] = len(report["issues"]) == 0
        return report

    except Exception as e:
        logger.error(f"Consistency check failed: {e}")
        return {"success": False, "message": str(e)}
