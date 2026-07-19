# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
数据中台 API 路由 — 全局统计/座舱对比/告警/Agent 活动

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
        # 使用各座舱的平均延迟来汇总全局平均延迟
        lat = stats.get("avg_latency_ms", 0)
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
            # 车控成功率（运营对比中的"命中率"）— 基于车控指令成功数/总数
            "vehicle_cmd_success_rate": round(stats.get("vehicle_cmd_success_rate", 1.0) * 100, 1),
            # 平均延迟使用累加值计算的真实平均，而非最后一次延迟
            "avg_latency_ms": round(stats.get("avg_latency_ms", stats.get("last_latency_ms", 0)), 2),
            "health_score": _calculate_health_score(stats),
        })

    return result


@router.get("/cache-trend")
async def get_cache_trend() -> List[Dict[str, Any]]:
    """缓存趋势数据 — 按小时聚合最近 24 小时的缓存命中/未命中数据。

    从 MySQL chat_logs 表查询真实数据，按小时分组统计 cache_hit=True/False 的数量。
    返回 24 个数据点（每小时一个），前端可按需合并为 2 小时间隔显示。

    Returns:
        [{"hour": "00:00", "hits": 5, "misses": 2}, ...]
    """
    db = get_db_manager()
    if not db.is_connected:
        # 后端未连接时返回空数据（24 个零点）
        return [{"hour": f"{h:02d}:00", "hits": 0, "misses": 0} for h in range(0, 25, 2)]

    try:
        rows = await db.execute_query(
            "SELECT "
            "  HOUR(created_at) as hr, "
            "  SUM(CASE WHEN cache_hit = 1 THEN 1 ELSE 0 END) as hits, "
            "  SUM(CASE WHEN cache_hit = 0 THEN 1 ELSE 0 END) as misses "
            "FROM chat_logs "
            "WHERE created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR) "
            "GROUP BY HOUR(created_at) "
            "ORDER BY hr"
        )

        # 构建完整的时间线（0-24 点，2 小时间隔）
        hour_map = {int(r["hr"]): {
            "hits": int(r.get("hits", 0) or 0),
            "misses": int(r.get("misses", 0) or 0),
        } for r in rows}

        # 按小时填充，然后合并为 2 小时间隔
        hourly = []
        for h in range(24):
            data = hour_map.get(h, {"hits": 0, "misses": 0})
            hourly.append({"hour": h, "hits": data["hits"], "misses": data["misses"]})

        # 合并为 2 小时间隔
        trend = []
        for h in range(0, 24, 2):
            combined_hits = hourly[h]["hits"] + (hourly[h + 1]["hits"] if h + 1 < 24 else 0)
            combined_misses = hourly[h]["misses"] + (hourly[h + 1]["misses"] if h + 1 < 24 else 0)
            label = f"{h:02d}:00"
            trend.append({"time": label, "hits": combined_hits, "misses": combined_misses})

        # 添加 24:00 点（用于显示完整时间线）
        trend.append({"time": "24:00", "hits": 0, "misses": 0})

        return trend
    except Exception as e:
        logger.error(f"Failed to get cache trend: {e}")
        return [{"time": f"{h:02d}:00", "hits": 0, "misses": 0} for h in range(0, 25, 2)]


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
    # 延迟高扣分 — 优先使用平均延迟，回退到最后一次延迟
    latency = stats.get("avg_latency_ms", stats.get("last_latency_ms", 0))
    # 修复：先判断 >1000（扣 40 分），再判断 >500（扣 20 分）
    # 此前 elif 顺序反了，导致 >1000 的请求也只扣 20 分，健康分无区分度
    if latency > 1000:
        score -= 40
    elif latency > 500:
        score -= 20
    return max(score, 0)
