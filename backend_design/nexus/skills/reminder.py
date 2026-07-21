# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
日程提醒技能组

3 个技能:
  1. set_reminder:    解析时间+内容，持久化存储提醒
  2. query_reminder:  查询用户全部待办提醒
  3. cancel_reminder: 删除指定提醒

存储: Redis Sorted Set（按时间戳排序），后台 Celery 定时扫描到期推送
依赖: Redis 连接（通过 redis_client 依赖注入）
"""

from __future__ import annotations

import json
import time
from typing import Any

from nexus.core.logger import get_logger
from nexus.skills.base import BaseSkill, SkillGroup, SkillResult, register_skill

logger = get_logger(__name__)

# Redis Sorted Set key 前缀
_REMINDER_KEY = "nexus:reminders:{user_id}"


def _get_redis():
    """延迟获取 Redis 连接。"""
    try:
        import redis

        from nexus.config import get_config
        config = get_config()
        return redis.Redis(
            host=config.redis.host,
            port=config.redis.port,
            db=config.redis.db,
            decode_responses=True,
        )
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}")
        return None


@register_skill(
    "set_reminder",
    SkillGroup.LIFESTYLE,
    description="当用户要求设置提醒、定时、备忘时调用此技能。",
    cache_ttl=0,
)
class SetReminderSkill(BaseSkill):
    """设置提醒技能：解析时间+内容，存入 Redis Sorted Set。"""

    name = "set_reminder"
    required_parameters = ["content"]
    optional_parameters = ["remind_at", "user_id"]
    examples = [
        {"input": "明天早上8点提醒我开会", "arguments": {"content": "开会", "remind_at": "2024-01-15T08:00:00"}},
        {"input": "30分钟后提醒我取快递", "arguments": {"content": "取快递", "remind_at": "relative:1800"}},
    ]
    parameters = {
        "content": {"type": "string", "description": "提醒内容"},
        "remind_at": {"type": "string", "description": "提醒时间（ISO格式或 relative:秒数）"},
    }

    async def execute(self, content: str = "", remind_at: str = "", **kwargs: Any) -> SkillResult:
        logger.info(f"SetReminder: content={content}, remind_at={remind_at}")
        user_id = kwargs.get("user_id", "default")

        if not content:
            return SkillResult(
                status="error",
                message="请告诉我提醒什么内容。",
                action="set_reminder",
                handled=True,
            )

        # 解析提醒时间
        timestamp = self._parse_time(remind_at)
        if not timestamp:
            return SkillResult(
                status="error",
                message="无法解析提醒时间，请用'明天8点'或'30分钟后'的格式。",
                action="set_reminder",
                handled=True,
            )

        # 存入 Redis Sorted Set
        r = _get_redis()
        if r:
            try:
                key = _REMINDER_KEY.format(user_id=user_id)
                reminder_data = json.dumps({
                    "content": content,
                    "remind_at": timestamp,
                    "created_at": time.time(),
                }, ensure_ascii=False)
                r.zadd(key, {reminder_data: timestamp})
                return SkillResult(
                    status="ok",
                    message=f"好的，已设置提醒：{content}，将在指定时间通知您。",
                    action="set_reminder",
                    handled=True,
                    metadata={"timestamp": timestamp, "content": content},
                )
            except Exception as e:
                logger.error(f"Redis set failed: {e}")

        # Redis 不可用时降级
        return SkillResult(
            status="ok",
            message=f"好的，我记下了：{content}。但提醒服务暂不可用。",
            action="set_reminder",
            handled=True,
        )

    def _parse_time(self, time_str: str) -> float:
        """解析时间字符串为 Unix 时间戳。"""
        if not time_str:
            return time.time() + 3600  # 默认1小时后

        # relative:秒数
        if time_str.startswith("relative:"):
            try:
                seconds = int(time_str.split(":")[1])
                return time.time() + seconds
            except (ValueError, IndexError):
                return 0

        # ISO 格式
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(time_str)
            return dt.timestamp()
        except (ValueError, TypeError):
            pass

        return 0


@register_skill(
    "query_reminder",
    SkillGroup.LIFESTYLE,
    description="当用户查询提醒、待办、日程时调用此技能。",
    cache_ttl=60,
)
class QueryReminderSkill(BaseSkill):
    """查询提醒技能：从 Redis Sorted Set 读取待办。"""

    name = "query_reminder"
    required_parameters: list[str] = []
    optional_parameters = ["user_id"]
    examples = [
        {"input": "我有什么提醒", "arguments": {}},
        {"input": "查看我的待办", "arguments": {}},
    ]
    parameters = {}

    async def execute(self, **kwargs: Any) -> SkillResult:
        logger.info("QueryReminder")
        user_id = kwargs.get("user_id", "default")

        r = _get_redis()
        if not r:
            return SkillResult(
                status="ok",
                message="提醒服务暂不可用。",
                action="query_reminder",
                handled=True,
            )

        try:
            key = _REMINDER_KEY.format(user_id=user_id)
            now = time.time()
            # 获取所有未过期的提醒
            items = r.zrangebyscore(key, now, "+inf")
            if not items:
                return SkillResult(
                    status="ok",
                    message="您当前没有待办提醒。",
                    action="query_reminder",
                    handled=True,
                )

            # 格式化提醒列表
            from datetime import datetime
            reminders: list[str] = []
            for item in items:
                try:
                    data = json.loads(item)
                    dt = datetime.fromtimestamp(data["remind_at"])
                    reminders.append(f"• {dt.strftime('%m月%d日 %H:%M')} - {data['content']}")
                except (json.JSONDecodeError, KeyError):
                    continue

            message = f"您有 {len(reminders)} 条提醒：\n" + "\n".join(reminders)
            return SkillResult(
                status="ok",
                message=message,
                action="query_reminder",
                handled=True,
                metadata={"count": len(reminders)},
            )
        except Exception as e:
            logger.error(f"Redis query failed: {e}")
            return SkillResult(
                status="error",
                message="查询提醒失败。",
                action="query_reminder",
                handled=True,
            )


@register_skill(
    "cancel_reminder",
    SkillGroup.LIFESTYLE,
    description="当用户要求取消、删除提醒时调用此技能。",
    has_side_effect=True,
    cache_ttl=0,
)
class CancelReminderSkill(BaseSkill):
    """取消提醒技能：从 Redis Sorted Set 删除。"""

    name = "cancel_reminder"
    required_parameters = ["content"]
    optional_parameters = ["user_id"]
    examples = [
        {"input": "取消开会的提醒", "arguments": {"content": "开会"}},
    ]
    parameters = {
        "content": {"type": "string", "description": "要取消的提醒内容关键词"},
    }

    async def execute(self, content: str = "", **kwargs: Any) -> SkillResult:
        logger.info(f"CancelReminder: content={content}")
        user_id = kwargs.get("user_id", "default")

        if not content:
            return SkillResult(
                status="error",
                message="请告诉我要取消哪条提醒。",
                action="cancel_reminder",
                handled=True,
            )

        r = _get_redis()
        if not r:
            return SkillResult(
                status="ok",
                message="提醒服务暂不可用。",
                action="cancel_reminder",
                handled=True,
            )

        try:
            key = _REMINDER_KEY.format(user_id=user_id)
            items = r.zrange(key, 0, -1)
            removed = 0
            for item in items:
                try:
                    data = json.loads(item)
                    if content in data.get("content", ""):
                        r.zrem(key, item)
                        removed += 1
                except json.JSONDecodeError:
                    continue

            if removed > 0:
                return SkillResult(
                    status="ok",
                    message=f"已取消 {removed} 条包含「{content}」的提醒。",
                    action="cancel_reminder",
                    handled=True,
                    metadata={"removed": removed},
                )
            return SkillResult(
                status="ok",
                message=f"未找到包含「{content}」的提醒。",
                action="cancel_reminder",
                handled=True,
            )
        except Exception as e:
            logger.error(f"Redis cancel failed: {e}")
            return SkillResult(
                status="error",
                message="取消提醒失败。",
                action="cancel_reminder",
                handled=True,
            )
