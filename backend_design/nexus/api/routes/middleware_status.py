"""
中间件状态 API 路由 — v2.1 中间件看板后端

查询各中间件（Redis/Milvus/Neo4j/RabbitMQ/MySQL）的运行状态和隔离信息。
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
        "redis": await _get_redis_status(),
        "milvus": await _get_milvus_status(),
        "neo4j": await _get_neo4j_status(),
        "rabbitmq": await _get_rabbitmq_status(),
        "mysql": await _get_mysql_status(),
        "llm": _get_llm_config(),
        "tts": _get_tts_config(),
        "asr": _get_asr_config(),
        "app": _get_app_config(),
        "oss": _get_oss_config(),
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


@router.get("/rabbitmq")
async def get_rabbitmq_status() -> Dict[str, Any]:
    """RabbitMQ 状态。"""
    return await _get_rabbitmq_status()


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


async def _get_rabbitmq_status() -> Dict[str, Any]:
    """获取 RabbitMQ 状态。"""
    config = get_config().rabbitmq
    try:
        import aiohttp
        # 使用 RabbitMQ Management HTTP API
        mgmt_url = f"http://{config.host}:{config.port + 10000}/api/overview"
        auth = aiohttp.BasicAuth(config.user, config.password)
        async with aiohttp.ClientSession() as session:
            async with session.get(mgmt_url, auth=auth, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "name": "RabbitMQ",
                        "status": "connected",
                        "host": config.host,
                        "port": config.port,
                        "version": data.get("rabbitmq_version", "unknown"),
                        "message_stats": data.get("message_stats", {}),
                        "object_totals": data.get("object_totals", {}),
                    }
                else:
                    return {
                        "name": "RabbitMQ",
                        "status": "disconnected",
                        "host": config.host,
                        "error": f"HTTP {resp.status}",
                    }
    except ImportError:
        return {
            "name": "RabbitMQ",
            "status": "not_installed",
            "host": config.host,
            "message": "aiohttp not installed for RabbitMQ management API check",
        }
    except Exception as e:
        return {
            "name": "RabbitMQ",
            "status": "disconnected",
            "host": config.host,
            "port": config.port,
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
        "mainagent_confirm_enabled": config.cockpit.mainagent_confirm_enabled,
        "cockpit_count": config.cockpit.default_cockpit_count if hasattr(config, 'cockpit') else 3,
    }


def _get_oss_config() -> Dict[str, Any]:
    """获取 OSS 对象存储配置信息。"""
    config = get_config()
    try:
        oss = config.oss
        # oss.enabled 为 True 时表示 AccessKey + SecretKey 都已配置
        if oss.enabled:
            status = "available"
        elif oss.endpoint:
            status = "configured"
        else:
            status = "not_configured"
        return {
            "name": "OSS 对象存储",
            "status": status,
            "provider": "aliyun",
            "endpoint": oss.endpoint or "",
            "bucket": oss.bucket_name or "",
            "public_url": oss.public_base_url or "",
        }
    except Exception:
        return {"name": "OSS 对象存储", "status": "not_configured"}
