"""
Admin Routes — 管理接口: 技能列表、记忆查询、缓存管理
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from nexus.core.logger import get_logger
from nexus.models.schemas import MemoryResponse, SkillListResponse

logger = get_logger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/skills", response_model=SkillListResponse)
async def list_skills(request: Request):
    """列出所有可用技能"""
    app = request.app
    if not hasattr(app.state, "skill_registry") or not app.state.skill_registry:
        return SkillListResponse(skills=[], count=0)

    tools = app.state.skill_registry.get_all_tools()
    return SkillListResponse(skills=tools, count=len(tools))


@router.get("/memory/{user_id}", response_model=MemoryResponse)
async def get_user_memory(request: Request, user_id: str):
    """查询用户记忆"""
    app = request.app
    if not hasattr(app.state, "memory_manager") or not app.state.memory_manager:
        return MemoryResponse(user_id=user_id, memories=[], profile={})

    manager = app.state.memory_manager
    profile = manager.get_user_profile(user_id)

    # 获取图谱记忆
    memories = []
    if manager.graph_store and manager.graph_store.driver:
        memories = manager.graph_store.search_user_graph(user_id, depth=1)

    return MemoryResponse(user_id=user_id, memories=memories, profile=profile)


@router.get("/cache/stats")
async def cache_stats(request: Request):
    """获取语义缓存统计信息（命中/未命中/命中率/大小）。"""
    app = request.app
    if not hasattr(app.state, "semantic_cache") or not app.state.semantic_cache:
        return {"hits": 0, "misses": 0, "hit_rate": 0, "size": 0}

    cache = app.state.semantic_cache

    # 优先调用 cache.stats() 方法
    stats_fn = getattr(cache, "stats", None)
    if stats_fn and callable(stats_fn):
        result = stats_fn()
        if hasattr(result, "__await__"):
            result = await result
        if isinstance(result, dict):
            return result

    # 手动计算统计（兼容无 stats 方法的缓存实现）
    hits = getattr(cache, "hit_count", 0) or 0
    misses = getattr(cache, "miss_count", 0) or 0
    total = hits + misses
    hit_rate = round(hits / total * 100, 1) if total > 0 else 0
    size = getattr(cache, "size", 0) or 0
    return {"hits": hits, "misses": misses, "hit_rate": hit_rate, "size": size}


@router.post("/cache/clear")
async def clear_cache(request: Request):
    """清空语义缓存"""
    app = request.app
    if not hasattr(app.state, "semantic_cache") or not app.state.semantic_cache:
        return {"cleared": 0, "message": "cache not available"}

    count = await app.state.semantic_cache.clear()
    return {"cleared": count, "message": "cache cleared"}


@router.get("/sessions")
async def list_sessions(request: Request):
    """列出活跃会话"""
    app = request.app
    sessions = {}
    if hasattr(app.state, "session_histories"):
        for key, history in app.state.session_histories.items():
            sessions[key] = {
                "message_count": len(history),
                "last_message": history[-1].get("content", "")[:50] if history else "",
            }
    return {"sessions": sessions, "count": len(sessions)}
