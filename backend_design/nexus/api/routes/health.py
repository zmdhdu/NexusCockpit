"""
Health Routes — 健康检查与系统状态

提供两个端点:
  GET /       — 根路径，返回项目基本信息
  GET /health — 健康检查，检查各组件连接状态
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from nexus.models.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request):
    """健康检查: 检查 Milvus、Neo4j、Redis、Agent 的连接状态。

    Returns:
        HealthResponse 包含 status 和各组件状态
    """
    app = request.app
    services = {}

    # 检查各组件状态
    if hasattr(app.state, "vector_store"):
        services["milvus"] = "connected" if app.state.vector_store and app.state.vector_store.is_connected else "disconnected"
    else:
        services["milvus"] = "not_configured"

    if hasattr(app.state, "graph_store"):
        services["neo4j"] = "connected" if app.state.graph_store and app.state.graph_store.driver else "disconnected"
    else:
        services["neo4j"] = "not_configured"

    if hasattr(app.state, "semantic_cache"):
        services["redis"] = "connected" if app.state.semantic_cache and app.state.semantic_cache.is_enabled else "disconnected"
    else:
        services["redis"] = "not_configured"

    services["agent"] = "ready" if hasattr(app.state, "agent_graph") and app.state.agent_graph else "not_ready"

    all_healthy = all(v in ("connected", "ready") for v in services.values())
    status = "healthy" if all_healthy else "degraded"

    return HealthResponse(status=status, version="1.0.0", services=services)


@router.get("/")
async def root():
    """根路径"""
    return {
        "name": "NexusCockpit",
        "version": "1.0.0",
        "description": "Enterprise Vehicle Voice Agent",
        "docs": "/docs",
        "health": "/health",
    }
