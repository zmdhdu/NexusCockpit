# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Health Routes — 健康检查与系统状态

提供两个端点:
  GET /       — 根路径，返回项目基本信息
  GET /health — 健康检查，检查各组件连接状态
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from nexus import __version__
from nexus.core.logger import get_logger
from nexus.models.schemas import HealthResponse

logger = get_logger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request):
    """健康检查: 检查所有组件连接状态。

    Returns:
        HealthResponse 包含 status 和各组件状态
    """
    app = request.app
    services = {}

    # --- Milvus 向量数据库 ---
    if hasattr(app.state, "vector_store"):
        milvus = app.state.vector_store
        services["milvus"] = "connected" if milvus and milvus.is_connected else "disconnected"
    else:
        services["milvus"] = "not_configured"

    # --- Neo4j 知识图谱 ---
    if hasattr(app.state, "graph_store"):
        services["neo4j"] = "connected" if app.state.graph_store and app.state.graph_store.driver else "disconnected"
    else:
        services["neo4j"] = "not_configured"

    # --- Redis 缓存 ---
    if hasattr(app.state, "semantic_cache"):
        redis = app.state.semantic_cache
        services["redis"] = "connected" if redis and redis.is_enabled else "disconnected"
    else:
        services["redis"] = "not_configured"

    # RabbitMQ 已完全移除（Celery/RabbitMQ 未落地），不再返回该字段

    # --- MySQL 数据库 ---
    try:
        import socket as _sock

        from nexus.config import get_config as _gc
        _mcfg = _gc().mysql
        _s = _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM)
        _s.settimeout(2)
        _r = _s.connect_ex((_mcfg.host, _mcfg.port))
        _s.close()
        services["mysql"] = "connected" if _r == 0 else "disconnected"
    except Exception as e:
        logger.warning(f"MySQL health check failed: {e}")
        services["mysql"] = "disconnected"

    # --- OSS 对象存储 ---
    if hasattr(app.state, "oss_storage"):
        oss = app.state.oss_storage
        if oss and oss.is_available:
            services["oss"] = "connected"
        elif oss and getattr(oss.config, "enabled", False):
            services["oss"] = "configured"
        else:
            services["oss"] = "disabled"
    else:
        services["oss"] = "not_configured"

    # --- Agent 工作流 ---
    services["agent"] = "ready" if hasattr(app.state, "agent_graph") and app.state.agent_graph else "not_ready"

    all_healthy = all(
        v in ("connected", "ready")
        for k, v in services.items()
        if k in ("milvus", "neo4j", "redis", "agent", "mysql")  # mysql 加入核心组件检查
    )
    status = "healthy" if all_healthy else "degraded"

    return HealthResponse(status=status, version=__version__, services=services)


@router.get("/")
async def root():
    """根路径"""
    return {
        "name": "NexusCockpit",
        "version": __version__,
        "description": "Enterprise Vehicle Voice Agent",
        "docs": "/docs",
        "health": "/health",
    }
