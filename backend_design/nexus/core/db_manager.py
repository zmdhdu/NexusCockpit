# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
MySQL 数据库管理器 — 统一数据库访问层

提供连接池管理和所有 MySQL 表的 CRUD 操作：
- SubAgent/MainAgent 巡检日志
- 审计日志
- LLM 成本追踪
- 用户管理（RBAC）
- 对话历史

使用 aiomysql 异步驱动，支持连接池。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import aiomysql

from nexus.config import get_config
from nexus.core.logger import get_logger

logger = get_logger(__name__)


class DatabaseManager:
    """MySQL 数据库管理器单例。

    使用 aiomysql.create_pool 创建连接池，
    所有查询通过池化连接执行，避免频繁创建/销毁连接。

    Usage:
        db = DatabaseManager()
        await db.connect()
        await db.insert_subagent_log(...)
    """

    def __init__(self) -> None:
        self._pool: aiomysql.Pool | None = None
        self._connected = False

    async def connect(self) -> None:
        """初始化连接池。"""
        if self._connected:
            return

        config = get_config().mysql
        try:
            self._pool = await aiomysql.create_pool(
                host=config.host,
                port=config.port,
                user=config.user,
                password=config.password,
                db=config.database,
                charset="utf8mb4",
                autocommit=True,
                minsize=2,
                maxsize=10,
            )
            self._connected = True
            logger.info(f"MySQL pool connected: {config.host}:{config.port}/{config.database}")

            # 自动迁移：确保多会话表和列存在
            await self._auto_migrate_tables()

            # 自动修复已有中文用户名 → 英文（避免编码乱码）
            await self._auto_fix_chinese_usernames()
        except Exception as e:
            logger.error(f"MySQL connection failed: {e}")
            self._connected = False

    async def _auto_migrate_tables(self) -> None:
        """启动时自动迁移 — 确保多会话相关表和列存在。

        检查并创建:
        1. chat_sessions 表（多会话管理）
        2. chat_logs 表的 session_id 列（会话消息关联）
        3. user_habits 表（用户习惯记录）
        """
        if not self.is_connected:
            return
        try:
            async with self._get_conn() as conn:
                async with conn.cursor() as cur:
                    # 1. 创建 chat_sessions 表
                    await cur.execute(
                        "CREATE TABLE IF NOT EXISTS chat_sessions ("
                        "  id BIGINT AUTO_INCREMENT PRIMARY KEY,"
                        "  session_id VARCHAR(128) NOT NULL UNIQUE,"
                        "  cockpit_id VARCHAR(32) NOT NULL,"
                        "  user_id VARCHAR(64) NOT NULL,"
                        "  title VARCHAR(128) DEFAULT '新对话',"
                        "  message_count INT DEFAULT 0,"
                        "  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
                        "  last_message_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,"
                        "  INDEX idx_cockpit_time (cockpit_id, last_message_at),"
                        "  INDEX idx_user (user_id)"
                        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
                    )

                    # 2. 创建 user_habits 表
                    await cur.execute(
                        "CREATE TABLE IF NOT EXISTS user_habits ("
                        "  id BIGINT AUTO_INCREMENT PRIMARY KEY,"
                        "  user_id VARCHAR(64) NOT NULL,"
                        "  cockpit_id VARCHAR(32) NOT NULL,"
                        "  habit_key VARCHAR(128) NOT NULL,"
                        "  habit_value TEXT,"
                        "  hit_count INT DEFAULT 1,"
                        "  last_used_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
                        "  UNIQUE KEY uk_user_cockpit_habit (user_id, cockpit_id, habit_key),"
                        "  INDEX idx_user (user_id),"
                        "  INDEX idx_cockpit (cockpit_id)"
                        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
                    )

                    # 3. 为 chat_logs 表添加 session_id 列（如果不存在）
                    await cur.execute(
                        "SELECT COUNT(*) FROM information_schema.columns "
                        "WHERE table_schema = DATABASE() AND table_name = 'chat_logs' "
                        "AND column_name = 'session_id'"
                    )
                    row = await cur.fetchone()
                    if row and row[0] == 0:
                        await cur.execute(
                            "ALTER TABLE chat_logs ADD COLUMN session_id VARCHAR(128) DEFAULT ''"
                        )
                        await cur.execute(
                            "ALTER TABLE chat_logs ADD INDEX idx_session (session_id)"
                        )
                        logger.info("Auto-migrate: added session_id column to chat_logs")

                    logger.info("Auto-migrate: chat_sessions, user_habits, chat_logs.session_id verified")
        except Exception as e:
            logger.warning(f"Auto-migrate tables failed (non-fatal): {e}")

    async def _auto_fix_chinese_usernames(self) -> None:
        """启动时自动修复中文用户名 → 英文（避免编码乱码）。

        将数据库中已有的中文用户名（张三/李四/王五/超级管理员等）
        更新为纯 ASCII 英文名，同时修复中文座舱名。
        """
        if not self.is_connected:
            return
        try:
            async with self._get_conn() as conn:
                async with conn.cursor() as cur:
                    # 修复中文用户名
                    fixes = [
                        ("user_01", "zhang_san"),
                        ("user_02", "li_si"),
                        ("user_03", "wang_wu"),
                        ("admin", "admin"),
                    ]
                    for user_id, new_name in fixes:
                        await cur.execute(
                            "UPDATE users SET username = %s WHERE user_id = %s AND username != %s",
                            (new_name, user_id, new_name),
                        )
                    # 修复中文座舱名
                    cockpit_fixes = [
                        ("cockpit-01", "Cockpit One"),
                        ("cockpit-02", "Cockpit Two"),
                        ("cockpit-03", "Cockpit Three"),
                    ]
                    for cockpit_id, new_name in cockpit_fixes:
                        await cur.execute(
                            "UPDATE cockpits SET name = %s WHERE cockpit_id = %s",
                            (new_name, cockpit_id),
                        )
                    logger.info("Auto-fix: Chinese usernames/cockpit names updated to English")
        except Exception as e:
            logger.warning(f"Auto-fix Chinese usernames failed (non-fatal): {e}")

    async def close(self) -> None:
        """关闭连接池。"""
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None
        self._connected = False
        logger.info("MySQL pool closed")

    @property
    def is_connected(self) -> bool:
        """是否已连接。"""
        return self._connected and self._pool is not None

    def _get_conn(self):
        """从连接池获取连接上下文管理器。"""
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        return self._pool.acquire()

    # ============================================================
    # SubAgent 日志
    # ============================================================

    async def insert_subagent_log(
        self,
        cockpit_id: str,
        check_items: dict[str, Any],
        llm_judgment: dict[str, Any] | None = None,
        decision_trace: dict[str, Any] | None = None,
        is_anomaly: bool = False,
    ) -> int | None:
        """写入 SubAgent 巡检日志。

        Args:
            cockpit_id: 座舱 ID
            check_items: 采集的状态指标
            llm_judgment: LLM 判断结果
            decision_trace: 决策链路追踪
            is_anomaly: 是否异常

        Returns:
            插入的行 ID，失败返回 None
        """
        if not self.is_connected:
            return None

        sql = (
            "INSERT INTO subagent_logs "
            "(cockpit_id, check_time, check_items, llm_judgment, decision_trace, is_anomaly) "
            "VALUES (%s, %s, %s, %s, %s, %s)"
        )
        try:
            # 使用东八区时间，避免 Docker 容器 UTC 时区导致时间偏差
            from datetime import timedelta, timezone
            cn_tz = timezone(timedelta(hours=8))
            async with self._get_conn() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(sql, (
                        cockpit_id,
                        datetime.now(cn_tz),
                        json.dumps(check_items, ensure_ascii=False, default=str),
                        json.dumps(llm_judgment, ensure_ascii=False, default=str) if llm_judgment else None,
                        json.dumps(decision_trace, ensure_ascii=False, default=str) if decision_trace else None,
                        is_anomaly,
                    ))
                    return cur.lastrowid
        except Exception as e:
            logger.error(f"Failed to insert subagent log: {e}")
            return None

    # ============================================================
    # MainAgent 日志
    # ============================================================

    async def insert_mainagent_log(
        self,
        cockpit_id: str,
        alert_type: str,
        severity: str,
        subagent_judgment: dict[str, Any],
        mainagent_judgment: dict[str, Any],
        action_taken: str,
        alert_time: float | None = None,
        confirm_time: float | None = None,
    ) -> int | None:
        """写入 MainAgent 确认日志。

        Args:
            cockpit_id: 座舱 ID
            alert_type: 告警类型
            severity: 严重程度
            subagent_judgment: SubAgent 判断结果
            mainagent_judgment: MainAgent 确认结果
            action_taken: 执行的动作
            alert_time: 告警时间戳
            confirm_time: 确认时间戳

        Returns:
            插入的行 ID，失败返回 None
        """
        if not self.is_connected:
            return None

        sql = (
            "INSERT INTO mainagent_logs "
            "(cockpit_id, alert_time, alert_type, severity, "
            "subagent_judgment, mainagent_judgment, action_taken, confirm_time) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
        )
        try:
            async with self._get_conn() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(sql, (
                        cockpit_id,
                        datetime.fromtimestamp(alert_time) if alert_time else datetime.now(),
                        alert_type,
                        severity,
                        json.dumps(subagent_judgment, ensure_ascii=False, default=str),
                        json.dumps(mainagent_judgment, ensure_ascii=False, default=str),
                        action_taken,
                        datetime.fromtimestamp(confirm_time) if confirm_time else None,
                    ))
                    return cur.lastrowid
        except Exception as e:
            logger.error(f"Failed to insert mainagent log: {e}")
            return None

    # ============================================================
    # 审计日志
    # ============================================================

    async def insert_audit_log(
        self,
        cockpit_id: str,
        user_id: str,
        action: str,
        detail: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> int | None:
        """写入审计日志。

        Args:
            cockpit_id: 座舱 ID
            user_id: 用户 ID
            action: 操作类型
            detail: 操作详情
            ip_address: 请求 IP

        Returns:
            插入的行 ID，失败返回 None
        """
        if not self.is_connected:
            return None

        sql = (
            "INSERT INTO audit_logs "
            "(cockpit_id, user_id, action, detail, ip_address) "
            "VALUES (%s, %s, %s, %s, %s)"
        )
        try:
            async with self._get_conn() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(sql, (
                        cockpit_id,
                        user_id,
                        action,
                        json.dumps(detail, ensure_ascii=False, default=str) if detail else None,
                        ip_address,
                    ))
                    return cur.lastrowid
        except Exception as e:
            logger.error(f"Failed to insert audit log: {e}")
            return None

    # ============================================================
    # LLM 成本追踪
    # ============================================================

    async def insert_llm_cost(
        self,
        cockpit_id: str,
        request_type: str,
        model_name: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_yuan: float = 0.0,
    ) -> int | None:
        """记录 LLM 调用成本。

        Args:
            cockpit_id: 座舱 ID
            request_type: 请求类型（chat/reflection/tool_synthesis）
            model_name: 模型名称
            prompt_tokens: 输入 token 数
            completion_tokens: 输出 token 数
            cost_yuan: 成本（元）

        Returns:
            插入的行 ID，失败返回 None
        """
        if not self.is_connected:
            return None

        sql = (
            "INSERT INTO llm_cost_tracking "
            "(cockpit_id, request_type, model_name, prompt_tokens, completion_tokens, cost_yuan) "
            "VALUES (%s, %s, %s, %s, %s, %s)"
        )
        try:
            async with self._get_conn() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(sql, (
                        cockpit_id,
                        request_type,
                        model_name,
                        prompt_tokens,
                        completion_tokens,
                        cost_yuan,
                    ))
                    return cur.lastrowid
        except Exception as e:
            logger.error(f"Failed to insert LLM cost: {e}")
            return None

    async def get_llm_cost_summary(
        self, cockpit_id: str | None = None, hours: int = 24
    ) -> dict[str, Any]:
        """获取 LLM 成本汇总。

        Args:
            cockpit_id: 座舱 ID（为空则查询所有）
            hours: 查询最近多少小时

        Returns:
            成本汇总字典
        """
        if not self.is_connected:
            return {"total_cost": 0, "total_tokens": 0, "by_cockpit": {}}

        try:
            async with self._get_conn() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    if cockpit_id:
                        await cur.execute(
                            "SELECT SUM(cost_yuan) as total_cost, "
                            "SUM(prompt_tokens + completion_tokens) as total_tokens, "
                            "COUNT(*) as call_count "
                            "FROM llm_cost_tracking "
                            "WHERE cockpit_id = %s AND created_at >= DATE_SUB(NOW(), INTERVAL %s HOUR)",
                            (cockpit_id, hours),
                        )
                    else:
                        await cur.execute(
                            "SELECT SUM(cost_yuan) as total_cost, "
                            "SUM(prompt_tokens + completion_tokens) as total_tokens, "
                            "COUNT(*) as call_count "
                            "FROM llm_cost_tracking "
                            "WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s HOUR)",
                            (hours,),
                        )
                    summary = await cur.fetchone()

                    # 按座舱分组
                    await cur.execute(
                        "SELECT cockpit_id, SUM(cost_yuan) as cost, "
                        "SUM(prompt_tokens + completion_tokens) as tokens "
                        "FROM llm_cost_tracking "
                        "WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s HOUR) "
                        "GROUP BY cockpit_id",
                        (hours,),
                    )
                    by_cockpit = {row["cockpit_id"]: {
                        "cost": float(row["cost"] or 0),
                        "tokens": int(row["tokens"] or 0),
                    } for row in await cur.fetchall()}

                    return {
                        "total_cost": float(summary["total_cost"] or 0) if summary else 0,
                        "total_tokens": int(summary["total_tokens"] or 0) if summary else 0,
                        "call_count": int(summary["call_count"] or 0) if summary else 0,
                        "by_cockpit": by_cockpit,
                    }
        except Exception as e:
            logger.error(f"Failed to get LLM cost summary: {e}")
            return {"total_cost": 0, "total_tokens": 0, "by_cockpit": {}}

    # ============================================================
    # 用户管理（RBAC）
    # ============================================================

    async def list_users(self) -> list[dict[str, Any]]:
        """列出所有用户。"""
        if not self.is_connected:
            return []

        try:
            async with self._get_conn() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(
                        "SELECT user_id, username, cockpit_id, role, created_at "
                        "FROM users ORDER BY created_at"
                    )
                    rows = await cur.fetchall()
                    return [
                        {
                            "user_id": r["user_id"],
                            "username": r["username"],
                            "cockpit_id": r["cockpit_id"] or "",
                            "role": r["role"] or "cockpit_user",
                            "created_at": r["created_at"].isoformat() if r["created_at"] else "",
                        }
                        for r in rows
                    ]
        except Exception as e:
            logger.error(f"Failed to list users: {e}")
            return []

    async def get_user(self, user_id: str) -> dict[str, Any] | None:
        """查询单个用户。"""
        if not self.is_connected:
            return None

        try:
            async with self._get_conn() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(
                        "SELECT user_id, username, cockpit_id, role, password_hash, created_at "
                        "FROM users WHERE user_id = %s",
                        (user_id,),
                    )
                    r = await cur.fetchone()
                    if not r:
                        return None
                    return {
                        "user_id": r["user_id"],
                        "username": r["username"],
                        "cockpit_id": r["cockpit_id"],
                        "role": r["role"],
                        "password_hash": r.get("password_hash"),
                        "created_at": r["created_at"].isoformat() if r["created_at"] else "",
                    }
        except Exception as e:
            logger.error(f"Failed to get user: {e}")
            return None

    async def create_user(
        self,
        user_id: str,
        username: str,
        cockpit_id: str | None = None,
        role: str = "cockpit_user",
        password_hash: str | None = None,
    ) -> dict[str, Any] | None:
        """创建用户。

        Returns:
            创建的用户字典，失败返回 None
        """
        if not self.is_connected:
            return None

        try:
            async with self._get_conn() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "INSERT INTO users (user_id, username, cockpit_id, role, password_hash) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (user_id, username, cockpit_id, role, password_hash),
                    )
            return {
                "user_id": user_id,
                "username": username,
                "cockpit_id": cockpit_id,
                "role": role,
                "created_at": datetime.now().isoformat(),
            }
        except aiomysql.IntegrityError as e:
            if e.args[0] == 1062:  # Duplicate entry
                return None
            logger.error(f"Failed to create user: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to create user: {e}")
            return None

    async def delete_user(self, user_id: str) -> bool:
        """删除用户。"""
        if not self.is_connected:
            return False

        try:
            async with self._get_conn() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
                    return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to delete user: {e}")
            return False

    async def update_user_password(self, user_id: str, password_hash: str) -> bool:
        """更新用户密码哈希。"""
        if not self.is_connected:
            return False

        try:
            async with self._get_conn() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "UPDATE users SET password_hash = %s WHERE user_id = %s",
                        (password_hash, user_id),
                    )
                    return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to update user password: {e}")
            return False

    # ============================================================
    # 对话历史
    # ============================================================

    async def insert_chat_history(
        self,
        cockpit_id: str,
        user_id: str,
        user_input: str,
        assistant_reply: str,
        session_id: str | None = None,
        intent: str | None = None,
        experts_involved: list[str] | None = None,
        latency_ms: float = 0,
        cache_hit: bool = False,
    ) -> int | None:
        """写入对话历史。"""
        if not self.is_connected:
            return None

        sql = (
            "INSERT INTO chat_history "
            "(cockpit_id, user_id, session_id, user_input, assistant_reply, "
            "intent, experts_involved, latency_ms, cache_hit) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
        )
        try:
            async with self._get_conn() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(sql, (
                        cockpit_id,
                        user_id,
                        session_id,
                        user_input,
                        assistant_reply,
                        intent,
                        json.dumps(experts_involved) if experts_involved else None,
                        latency_ms,
                        cache_hit,
                    ))
                    return cur.lastrowid
        except Exception as e:
            logger.error(f"Failed to insert chat history: {e}")
            return None

    async def get_chat_history(
        self,
        cockpit_id: str,
        user_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """获取对话历史。"""
        if not self.is_connected:
            return []

        try:
            async with self._get_conn() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    if user_id:
                        await cur.execute(
                            "SELECT * FROM chat_history "
                            "WHERE cockpit_id = %s AND user_id = %s "
                            "ORDER BY created_at DESC LIMIT %s",
                            (cockpit_id, user_id, limit),
                        )
                    else:
                        await cur.execute(
                            "SELECT * FROM chat_history "
                            "WHERE cockpit_id = %s "
                            "ORDER BY created_at DESC LIMIT %s",
                            (cockpit_id, limit),
                        )
                    return [dict(r) for r in await cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get chat history: {e}")
            return []

    # ============================================================
    # 通用查询
    # ============================================================

    async def execute_query(
        self, sql: str, params: tuple = ()
    ) -> list[dict[str, Any]]:
        """执行查询并返回结果。"""
        if not self.is_connected:
            return []

        try:
            async with self._get_conn() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(sql, params)
                    return [dict(r) for r in await cur.fetchall()]
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return []

    async def execute_update(
        self, sql: str, params: tuple = ()
    ) -> int:
        """执行 INSERT/UPDATE/DELETE 并返回受影响行数。"""
        if not self.is_connected:
            return 0

        try:
            async with self._get_conn() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(sql, params)
                    return cur.rowcount
        except Exception as e:
            logger.error(f"Update failed: {e}")
            return 0

    # ============================================================
    # 用户习惯
    # ============================================================

    async def record_user_habit(
        self, user_id: str, cockpit_id: str, habit_key: str, habit_value: str = ""
    ) -> None:
        """记录用户习惯（UPSERT，已存在则 hit_count+1）。

        Args:
            user_id: 用户 ID
            cockpit_id: 座舱 ID
            habit_key: 习惯键名（如 preferred_temp、favorite_music）
            habit_value: 习惯值
        """
        if not self.is_connected:
            return
        try:
            async with self._get_conn() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "INSERT INTO user_habits "
                        "(user_id, cockpit_id, habit_key, habit_value, hit_count, last_used_at) "
                        "VALUES (%s, %s, %s, %s, 1, NOW()) "
                        "ON DUPLICATE KEY UPDATE "
                        "habit_value=VALUES(habit_value), "
                        "hit_count=hit_count+1, last_used_at=NOW()",
                        (user_id, cockpit_id, habit_key, habit_value),
                    )
        except Exception as e:
            logger.error(f"Failed to record user habit: {e}")

    async def get_user_habits(
        self, user_id: str, cockpit_id: str = ""
    ) -> list[dict[str, Any]]:
        """获取用户习惯列表。"""
        if not self.is_connected:
            return []
        try:
            if cockpit_id:
                sql = "SELECT * FROM user_habits WHERE user_id=%s AND cockpit_id=%s ORDER BY hit_count DESC"
                params = (user_id, cockpit_id)
            else:
                sql = "SELECT * FROM user_habits WHERE user_id=%s ORDER BY hit_count DESC"
                params = (user_id,)
            return await self.execute_query(sql, params)
        except Exception as e:
            logger.error(f"Failed to get user habits: {e}")
            return []


# 全局单例
_db_manager: DatabaseManager | None = None


def get_db_manager() -> DatabaseManager:
    """获取数据库管理器全局单例。"""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager
