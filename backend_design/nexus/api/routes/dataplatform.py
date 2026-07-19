# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
数据中台 API 路由 — v2.1 全局统计/座舱对比/告警/Agent 活动

所有数据中台 API 由 Python 提供（Demo 阶段）。
生产环境由 Go 网关直接查 MySQL/Prometheus 返回。
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Query

from nexus.core.cockpit_manager import get_cockpit_manager
from nexus.core.db_manager import get_db_manager
from nexus.core.logger import get_logger
from nexus.observability.cockpit_metrics import get_cockpit_metrics

logger = get_logger(__name__)

router = APIRouter(prefix="/dataplatform", tags=["dataplatform"])


@router.get("/overview")
async def get_overview() -> Dict[str, Any]:
    """数据中台全局概览。"""
    manager = get_cockpit_manager()
    cockpits = manager.list_cockpits()

    total_chats = 0
    total_vehicle_cmds = 0
    total_cache_hits = 0
    total_cache_misses = 0
    total_latency = 0.0
    latency_count = 0

    for c in cockpits:
        stats = await get_cockpit_metrics().get_cockpit_stats(c.cockpit_id)
        total_chats += int(stats.get("chat_count", 0))
        total_vehicle_cmds += int(stats.get("vehicle_cmd_count", 0))
        total_cache_hits += int(stats.get("cache_hits", 0))
        total_cache_misses += int(stats.get("cache_misses", 0))
        lat = stats.get("last_latency_ms", 0)
        if lat:
            total_latency += lat
            latency_count += 1

    cache_total = total_cache_hits + total_cache_misses
    cache_hit_rate = (total_cache_hits / cache_total * 100) if cache_total > 0 else 0.0
    avg_latency = (total_latency / latency_count) if latency_count > 0 else 0.0

    return {
        "total_chats": total_chats,
        "total_vehicle_cmds": total_vehicle_cmds,
        "cache_hit_rate": round(cache_hit_rate, 1),
        "avg_latency_ms": round(avg_latency, 2),
        "cockpit_count": len(cockpits),
        "alert_count_24h": await _get_alert_count_24h(),
        "current_concurrency": await _get_current_concurrency(),
        "peak_concurrency": 0,
        "llm_cost_24h": await _get_llm_cost_summary(),
    }


@router.get("/cockpit/{cockpit_id}")
async def get_cockpit_detail(cockpit_id: str) -> Dict[str, Any]:
    """单座舱详情。"""
    manager = get_cockpit_manager()
    config = manager.get_cockpit(cockpit_id)
    if not config:
        return {"error": "Cockpit not found", "cockpit_id": cockpit_id}

    stats = await get_cockpit_metrics().get_cockpit_stats(cockpit_id)
    return {
        "cockpit_id": cockpit_id,
        "name": config.name,
        "is_active": config.is_active,
        "stats": stats,
    }


@router.get("/concurrency")
async def get_concurrency() -> Dict[str, Any]:
    """并发能力统计。"""
    return {
        "current_concurrency": await _get_current_concurrency(),
        "peak_concurrency_24h": 0,
        "qps": 0.0,
        "agent_parallelism": 5,  # 专家并行数
        "resource_usage": await _get_resource_usage(),
    }


@router.get("/alerts")
async def get_alerts(
    hours: int = Query(default=24, description="查询最近 N 小时的告警"),
    cockpit_id: str = Query(default="", description="过滤座舱 ID"),
) -> List[Dict[str, Any]]:
    """告警历史（从 MySQL mainagent_logs 查询）。"""
    import json

    db = get_db_manager()
    if not db.is_connected:
        return []

    if cockpit_id:
        rows = await db.execute_query(
            "SELECT * FROM mainagent_logs "
            "WHERE cockpit_id = %s AND alert_time >= DATE_SUB(NOW(), INTERVAL %s HOUR) "
            "ORDER BY alert_time DESC LIMIT 100",
            (cockpit_id, hours),
        )
    else:
        rows = await db.execute_query(
            "SELECT * FROM mainagent_logs "
            "WHERE alert_time >= DATE_SUB(NOW(), INTERVAL %s HOUR) "
            "ORDER BY alert_time DESC LIMIT 100",
            (hours,),
        )

    # 后处理：格式化时间和 JSON 字段
    result: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        # 格式化 alert_time
        at = item.get("alert_time")
        if hasattr(at, "strftime"):
            item["alert_time"] = at.strftime("%Y-%m-%d %H:%M:%S")
        elif at:
            item["alert_time"] = str(at)

        # 解析 JSON 字段
        for field in ("llm_judgment", "decision_trace"):
            val = item.get(field)
            if isinstance(val, str) and val.strip():
                try:
                    item[field] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    pass

        result.append(item)
    return result


@router.get("/agent/activity")
async def get_agent_activity(
    hours: int = Query(default=24, description="查询最近 N 小时的活动"),
    cockpit_id: str = Query(default="", description="过滤座舱 ID"),
) -> List[Dict[str, Any]]:
    """Agent 活动时间线（从 MySQL subagent_logs 查询）。

    返回的 check_items / llm_judgment / decision_trace 字段已从 JSON 字符串解析为 dict。
    """
    import json

    db = get_db_manager()
    if not db.is_connected:
        return []

    if cockpit_id:
        rows = await db.execute_query(
            "SELECT * FROM subagent_logs "
            "WHERE cockpit_id = %s AND check_time >= DATE_SUB(NOW(), INTERVAL %s HOUR) "
            "ORDER BY check_time DESC LIMIT 100",
            (cockpit_id, hours),
        )
    else:
        rows = await db.execute_query(
            "SELECT * FROM subagent_logs "
            "WHERE check_time >= DATE_SUB(NOW(), INTERVAL %s HOUR) "
            "ORDER BY check_time DESC LIMIT 100",
            (hours,),
        )

    # 后处理：解析 JSON 字段、格式化时间
    result: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        # 格式化 check_time (datetime → ISO 字符串)
        ct = item.get("check_time")
        if hasattr(ct, "isoformat"):
            item["check_time"] = ct.strftime("%Y-%m-%d %H:%M:%S")
        elif ct:
            item["check_time"] = str(ct)

        # 解析 JSON 字段
        for field in ("check_items", "llm_judgment", "decision_trace"):
            val = item.get(field)
            if isinstance(val, str) and val.strip():
                try:
                    item[field] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    pass

        # 生成可读摘要
        check_items = item.get("check_items")
        if isinstance(check_items, dict):
            parts = []
            for k in ("cache_hit_rate", "error_rate", "p95_latency_ms", "chat_count", "vehicle_status"):
                if k in check_items:
                    parts.append(f"{k}={check_items[k]}")
            item["check_summary"] = ", ".join(parts) if parts else ""
        else:
            item["check_summary"] = str(check_items) if check_items else ""

        llm_j = item.get("llm_judgment")
        if isinstance(llm_j, dict):
            item["llm_summary"] = llm_j.get("description") or llm_j.get("anomaly_type") or ""
        else:
            item["llm_summary"] = ""

        result.append(item)
    return result


@router.get("/comparison")
async def get_cockpit_comparison() -> List[Dict[str, Any]]:
    """座舱对比数据。"""
    manager = get_cockpit_manager()
    cockpits = manager.list_cockpits()

    result = []
    for c in cockpits:
        stats = await get_cockpit_metrics().get_cockpit_stats(c.cockpit_id)
        result.append({
            "cockpit_id": c.cockpit_id,
            "name": c.name,
            "chat_count": int(stats.get("chat_count", 0)),
            "vehicle_cmd_count": int(stats.get("vehicle_cmd_count", 0)),
            "cache_hit_rate": round(stats.get("cache_hit_rate", 0) * 100, 1),
            "avg_latency_ms": round(stats.get("last_latency_ms", 0), 2),
            "health_score": _calculate_health_score(stats),
        })

    return result


# ============================================================
# 内部辅助函数
# ============================================================

async def _get_alert_count_24h() -> int:
    """从 MySQL 查询最近 24 小时告警数。"""
    db = get_db_manager()
    if not db.is_connected:
        return 0
    try:
        rows = await db.execute_query(
            "SELECT COUNT(*) as cnt FROM mainagent_logs "
            "WHERE alert_time >= DATE_SUB(NOW(), INTERVAL 24 HOUR)"
        )
        return int(rows[0]["cnt"]) if rows else 0
    except Exception:
        return 0


async def _get_current_concurrency() -> int:
    """从 Redis 查询当前并发连接数。"""
    try:
        import redis.asyncio as aioredis
        from nexus.config import get_config
        config = get_config().redis
        client = aioredis.Redis(
            host=config.host, port=config.port, password=config.password,
            decode_responses=True,
        )
        info = await client.info("clients")
        await client.close()
        return int(info.get("connected_clients", 0))
    except Exception:
        return 0


async def _get_llm_cost_summary() -> Dict[str, Any]:
    """从 MySQL 查询 LLM 成本汇总。"""
    db = get_db_manager()
    if not db.is_connected:
        return {"total_cost": 0, "total_tokens": 0}
    return await db.get_llm_cost_summary(hours=24)


async def _get_resource_usage() -> Dict[str, Any]:
    """获取系统资源使用情况。"""
    try:
        import psutil
        return {
            "cpu_percent": round(psutil.cpu_percent(interval=0.1), 1),
            "memory_mb": round(psutil.virtual_memory().used / 1024 / 1024, 1),
            "memory_percent": round(psutil.virtual_memory().percent, 1),
            "disk_percent": round(psutil.disk_usage('/').percent, 1),
        }
    except ImportError:
        return {"cpu_percent": 0, "memory_mb": 0, "disk_percent": 0}
    except Exception:
        return {"cpu_percent": 0, "memory_mb": 0, "disk_percent": 0}


def _calculate_health_score(stats: Dict[str, Any]) -> int:
    """根据座舱指标计算健康评分（0-100）。"""
    score = 100
    # 缓存命中率低扣分
    cache_rate = stats.get("cache_hit_rate", 1.0)
    if cache_rate < 0.8:
        score -= 20
    # 错误率高扣分
    error_rate = stats.get("error_rate", 0.0)
    if error_rate > 0.05:
        score -= 30
    # 延迟高扣分
    latency = stats.get("last_latency_ms", 0)
    if latency > 500:
        score -= 20
    elif latency > 1000:
        score -= 40
    return max(score, 0)
