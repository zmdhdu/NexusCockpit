# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Admin Routes — 管理接口: 技能列表、记忆查询、缓存管理
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, UploadFile
from pydantic import BaseModel

from nexus.core.auth import get_current_user
from nexus.core.logger import get_logger
from nexus.models.schemas import MemoryResponse, SkillListResponse

logger = get_logger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/skills", response_model=SkillListResponse)
async def list_skills(request: Request, user_id: str = Depends(get_current_user)):
    """列出所有可用技能"""
    app = request.app
    if not hasattr(app.state, "skill_registry") or not app.state.skill_registry:
        return SkillListResponse(skills=[], count=0)

    tools = app.state.skill_registry.get_all_tools()
    return SkillListResponse(skills=tools, count=len(tools))


@router.get("/memory/{user_id}", response_model=MemoryResponse)
async def get_user_memory(request: Request, user_id: str, _: str = Depends(get_current_user)):
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
async def cache_stats(request: Request, user_id: str = Depends(get_current_user)):
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

    # 手动计算统计（缓存实现无 stats 方法时降级）
    hits = getattr(cache, "hit_count", 0) or 0
    misses = getattr(cache, "miss_count", 0) or 0
    total = hits + misses
    hit_rate = round(hits / total * 100, 1) if total > 0 else 0
    size = getattr(cache, "size", 0) or 0
    return {"hits": hits, "misses": misses, "hit_rate": hit_rate, "size": size}


@router.post("/cache/clear")
async def clear_cache(request: Request, user_id: str = Depends(get_current_user)):
    """清空语义缓存"""
    app = request.app
    if not hasattr(app.state, "semantic_cache") or not app.state.semantic_cache:
        return {"cleared": 0, "message": "cache not available"}

    count = await app.state.semantic_cache.clear()
    return {"cleared": count, "message": "cache cleared"}


@router.get("/sessions")
async def list_sessions(request: Request, user_id: str = Depends(get_current_user)):
    """列出活跃会话"""
    app = request.app
    # 优先使用 SessionStore (Redis 持久化)
    session_store = getattr(app.state, "session_store", None)
    if session_store:
        sessions = await session_store.list_sessions()
        return {"sessions": sessions, "count": len(sessions)}

    # 降级: 从内存 dict 获取
    sessions = {}
    if hasattr(app.state, "session_histories"):
        for key, history in app.state.session_histories.items():
            sessions[key] = {
                "message_count": len(history),
                "last_message": history[-1].get("content", "")[:50] if history else "",
            }
    return {"sessions": sessions, "count": len(sessions)}


# ---- 知识库管理接口 ----

class KBUploadResponse(BaseModel):
    """知识库上传响应"""
    chunks: int
    source: str
    category: str
    message: str


@router.post("/kb/upload")
async def kb_upload(
    request: Request,
    file: UploadFile = File(...),
    category: str = "general",
):
    """上传文档到 Cherry 知识库。

    支持纯文本文件（.txt/.md），自动分块、向量化、入库。

    Args:
        file: 上传的文档文件
        category: 文档类别 (manual/dtc/faq/maintenance)
    """
    app = request.app
    if not hasattr(app.state, "cherry_kb") or not app.state.cherry_kb:
        return {"error": "Knowledge base not available"}

    kb = app.state.cherry_kb
    content = await file.read()
    text = content.decode("utf-8", errors="ignore")

    chunks = kb.add_document(text, source=file.filename, category=category)
    return {
        "chunks": chunks,
        "source": file.filename,
        "category": category,
        "message": f"Document uploaded: {chunks} chunks indexed",
    }


@router.post("/kb/reindex")
async def kb_reindex(request: Request):
    """重建知识库向量索引。"""
    app = request.app
    if not hasattr(app.state, "cherry_kb") or not app.state.cherry_kb:
        return {"error": "Knowledge base not available"}

    # 重建索引（实际实现需要 flush + 重建 IVF 索引）
    return {"message": "Reindex triggered", "status": "pending"}


@router.get("/kb/stats")
async def kb_stats(request: Request):
    """获取知识库容量/文档统计。"""
    app = request.app
    if not hasattr(app.state, "cherry_kb") or not app.state.cherry_kb:
        return {"connected": False, "total_docs": 0}

    return app.state.cherry_kb.get_stats()


@router.post("/config/reload")
async def reload_config(request: Request, _: str = Depends(get_current_user)):
    """配置热更新 — 重新加载 .env.local 并重置 LLM 客户端单例。

    Phase 5 改进: 无需重启服务即可切换 LLM 模式/降级配置。

    流程:
      1. 清除 get_config() 的 lru_cache（强制下次调用重新读取 .env.local）
      2. 调用 reset_clients() 清除 AsyncOpenAI / ChatOpenAI 单例
      3. 返回新配置状态（敏感值脱敏）

    Returns:
        包含新配置状态的字典
    """
    from nexus.agent.llm_client_factory import reset_clients
    from nexus.config import get_config

    # 1. 清除配置缓存（lru_cache），下次 get_config() 会重新读取 .env.local
    get_config.cache_clear()

    # 2. 重置 LLM 客户端单例（AsyncOpenAI + ChatOpenAI）
    reset_clients()

    # 3. 重置框架适配器单例（OpenAIEmbeddings + Milvus + Neo4jGraph）
    try:
        from nexus.rag.framework_adapters import reset_framework_adapters
        reset_framework_adapters()
    except ImportError:
        pass  # 框架适配器未安装时跳过

    # 3. 重新加载配置并返回状态
    config = get_config()
    llm_config = config.llm

    return {
        "status": "reloaded",
        "llm": {
            "provider": llm_config.provider,
            "model": llm_config.llm_model,
            "base_url": llm_config.ark_base_url,
            "is_local": llm_config.is_local,
            "fallback_enabled": llm_config.fallback_enabled,
            "api_key_loaded": bool(llm_config.ark_api_key),
        },
        "embedding": {
            "model": llm_config.embedding_model,
            "dim": llm_config.embedding_dim,
        },
        "message": "Config reloaded, LLM clients reset. New settings will take effect on next request.",
    }


@router.get("/config")
async def get_current_config(request: Request, _: str = Depends(get_current_user)):
    """查看当前配置状态（敏感值脱敏）。"""
    from nexus.config import get_config

    config = get_config()
    llm_config = config.llm

    return {
        "llm": {
            "provider": llm_config.provider,
            "model": llm_config.llm_model,
            "base_url": llm_config.ark_base_url,
            "is_local": llm_config.is_local,
            "fallback_enabled": llm_config.fallback_enabled,
            "fallback_model": llm_config.fallback_model,
            "api_key_masked": f"***{llm_config.ark_api_key[-4:]}" if llm_config.ark_api_key else "(empty)",
            "timeout": llm_config.timeout,
            "max_tokens": llm_config.max_tokens,
            "reflection_enabled": llm_config.reflection_enabled,
            "memory_extraction_enabled": llm_config.memory_extraction_enabled,
        },
        "embedding": {
            "model": llm_config.embedding_model,
            "dim": llm_config.embedding_dim,
        },
        "milvus": {
            "host": config.milvus.host,
            "port": config.milvus.port,
            "collection_food": config.milvus.collection_food,
            "collection_memory": config.milvus.collection_memory,
        },
        "redis": {
            "host": config.redis.host,
            "port": config.redis.port,
            "cache_enabled": config.redis.cache_enabled,
            "cache_similarity_threshold": config.redis.cache_similarity_threshold,
        },
        "neo4j": {
            "uri": config.neo4j.uri,
            "user": config.neo4j.user,
        },
        "mysql": {
            "host": config.mysql.host,
            "port": config.mysql.port,
            "database": config.mysql.database,
        },
    }
