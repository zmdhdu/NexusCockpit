# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
中间件状态 API 路由 — 中间件看板后端

查询各中间件（Redis/Milvus/Neo4j/MySQL）的运行状态和隔离信息。

注: RabbitMQ 已移除（Celery/RabbitMQ 未落地）。
"""

from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import APIRouter

from nexus.config import get_config
from nexus.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/middleware", tags=["middleware"])


@router.get("/")
async def get_all_middleware_status() -> Dict[str, Any]:
    """获取所有中间件状态概览。"""
    return {
        "asr": _get_asr_config(),
        "tts": _get_tts_config(),
        "milvus": await _get_milvus_status(),
        "neo4j": await _get_neo4j_status(),
        "mysql": await _get_mysql_status(),
        "redis": await _get_redis_status(),
        "llm": _get_llm_config(),
        "app": _get_app_config(),
        # OSS 配置查询已移除（未集成）
    }


@router.get("/redis")
async def get_redis_status() -> Dict[str, Any]:
    """Redis 状态。"""
    return await _get_redis_status()


@router.get("/milvus")
async def get_milvus_status() -> Dict[str, Any]:
    """Milvus 状态。"""
    return await _get_milvus_status()


@router.get("/neo4j")
async def get_neo4j_status() -> Dict[str, Any]:
    """Neo4j 状态。"""
    return await _get_neo4j_status()




@router.get("/mysql")
async def get_mysql_status() -> Dict[str, Any]:
    """MySQL 状态。"""
    return await _get_mysql_status()


# ============================================================
# 内部实现
# ============================================================

async def _get_redis_status() -> Dict[str, Any]:
    """获取 Redis 状态。"""
    config = get_config().redis
    try:
        import redis.asyncio as aioredis
        client = aioredis.Redis(
            host=config.host, port=config.port, password=config.password,
            decode_responses=True,
        )
        info = await client.info()
        db_info = await client.info("keyspace")
        await client.close()

        return {
            "name": "Redis",
            "status": "connected",
            "version": info.get("redis_version", "unknown"),
            "memory_used_mb": round(info.get("used_memory", 0) / 1024 / 1024, 2),
            "memory_max_mb": round(info.get("maxmemory", 0) / 1024 / 1024, 2),
            "connected_clients": info.get("connected_clients", 0),
            "keyspace": db_info,
        }
    except Exception as e:
        return {"name": "Redis", "status": "disconnected", "error": str(e)}


async def _get_milvus_status() -> Dict[str, Any]:
    """获取 Milvus 状态。"""
    config = get_config().milvus
    try:
        from pymilvus import connections, utility
        connections.connect(alias=config.alias, uri=config.uri, token=config.token)
        collections = utility.list_collections(using=config.alias)
        return {
            "name": "Milvus",
            "status": "connected",
            "uri": config.uri,
            "collections": collections,
            "collection_count": len(collections),
        }
    except Exception as e:
        return {"name": "Milvus", "status": "disconnected", "error": str(e)}


async def _get_neo4j_status() -> Dict[str, Any]:
    """获取 Neo4j 状态。"""
    config = get_config().neo4j
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(
            config.uri,
            auth=(config.user, config.password),
        )
        # 验证连接
        driver.verify_connectivity()
        # 获取基本信息
        with driver.session() as session:
            result = session.run("RETURN 1 as test")
            result.single()
            # 获取节点数
            node_count = session.run("MATCH (n) RETURN count(n) as cnt").single()["cnt"]
            # 获取关系数
            rel_count = session.run("MATCH ()-[r]->() RETURN count(r) as cnt").single()["cnt"]
            # 获取标签列表
            labels = session.run("CALL db.labels() YIELD label RETURN collect(label) as labels").single()["labels"]
        driver.close()

        return {
            "name": "Neo4j",
            "status": "connected",
            "uri": config.uri,
            "node_count": node_count,
            "relationship_count": rel_count,
            "labels": labels,
        }
    except ImportError:
        return {
            "name": "Neo4j",
            "status": "not_installed",
            "uri": config.uri,
            "message": "neo4j driver not installed (pip install neo4j)",
        }
    except Exception as e:
        return {
            "name": "Neo4j",
            "status": "disconnected",
            "uri": config.uri,
            "error": str(e),
        }


async def _get_mysql_status() -> Dict[str, Any]:
    """获取 MySQL 状态。"""
    config = get_config().mysql
    try:
        import aiomysql
        conn = await aiomysql.connect(
            host=config.host, port=config.port,
            user=config.user, password=config.password,
            db=config.database,
        )
        async with conn.cursor() as cur:
            await cur.execute("SELECT VERSION()")
            version = await cur.fetchone()
            await cur.execute("SHOW STATUS LIKE 'Threads_connected'")
            threads = await cur.fetchone()
        conn.close()

        return {
            "name": "MySQL",
            "status": "connected",
            "version": version[0] if version else "unknown",
            "connections": int(threads[1]) if threads else 0,
            "host": config.host,
            "port": config.port,
            "database": config.database,
        }
    except Exception as e:
        return {"name": "MySQL", "status": "disconnected", "error": str(e)}


# ============================================================
# 应用级配置
# ============================================================

def _get_llm_config() -> Dict[str, Any]:
    """获取 LLM 模型配置信息。"""
    config = get_config().llm
    api_key = config.ark_api_key or ""
    masked_key = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "未配置"
    # 有 API Key 则视为可用（available），否则未配置
    status = "available" if api_key else "not_configured"
    return {
        "name": "LLM 大语言模型",
        "status": status,
        "provider": "SiliconFlow / 火山引擎",
        "model": config.llm_model,
        "api_key": masked_key,
        "base_url": config.ark_base_url,
        "max_tokens": config.max_tokens,
        "temperature": 0.7,
    }


def _get_tts_config() -> Dict[str, Any]:
    """获取 TTS 语音合成配置信息。"""
    config = get_config().asr
    model_path = config.resolved_cosyvoice_path()
    import os
    return {
        "name": "TTS 语音合成",
        "status": "available" if os.path.exists(model_path) else "model_not_found",
        "engine": "CosyVoice",
        "model_path": model_path,
        "sample_rate": 22050,
    }


def _get_asr_config() -> Dict[str, Any]:
    """获取 ASR 语音识别配置信息。"""
    config = get_config().asr
    model_path = config.resolved_funasr_path()
    import os
    return {
        "name": "ASR 语音识别",
        "status": "available" if os.path.exists(model_path) else "model_not_found",
        "engine": "SenseVoice",
        "model_path": model_path,
    }


def _get_app_config() -> Dict[str, Any]:
    """获取应用级运行配置。"""
    config = get_config()
    return {
        "name": "应用配置",
        "status": "running",
        "version": "2.1.0",
        "environment": os.getenv("APP_ENV", "development"),
        "debug": config.server.debug,
        "host": config.server.host,
        "port": config.server.port,
        "cors_origins": config.server.cors_origins,
        "rate_limit_enabled": True,
        "cache_enabled": True,
        # mainagent_confirm_enabled 已移除
        "cockpit_count": config.cockpit.default_cockpit_count if hasattr(config, 'cockpit') else 1,
    }


def _get_oss_config() -> Dict[str, Any]:
    """OSS 对象存储已移除（未集成，过度设计）。"""
    return {"name": "OSS 对象存储", "status": "removed", "reason": "已简化移除"}
