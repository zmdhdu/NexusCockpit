"""
NexusCockpit FastAPI 应用入口

本文件是后端服务的启动入口，负责:
1. 创建 FastAPI 应用实例
2. 在应用启动时初始化所有组件 (数据库、缓存、Agent 等)
3. 注册 API 路由和中间件
4. 在应用关闭时清理资源

启动方式:
    cd backend_design
    python -m nexus.main
    或
    make dev
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

# 导入 API 路由
from nexus.api.routes.admin import router as admin_router
from nexus.api.routes.auth import router as auth_router
from nexus.api.routes.chat import router as chat_router
from nexus.api.routes.health import router as health_router
from nexus.api.routes.vehicle import router as vehicle_router
from nexus.api.websocket import router as ws_router
from nexus.config import get_config
from nexus.core.exceptions import AuthError, NexusError, RateLimitError
from nexus.core.logger import get_logger, setup_logging
from nexus.middleware.rate_limiter import RateLimiter
from nexus.middleware.redis_cache import SemanticCache
from nexus.middleware.session_store import SessionStore
from nexus.observability.langfuse import LangfuseMonitor
from nexus.observability.metrics import init_metrics
from nexus.rag.embedding import EmbeddingService
from nexus.rag.graph_factory import build_graph_store
from nexus.rag.vector_factory import build_vector_store
from nexus.vehicle.factory import build_vehicle_adapter

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理: 启动时初始化所有组件，关闭时清理资源。

    FastAPI 的 lifespan 机制会在应用启动前执行 yield 之前的代码，
    在应用关闭后执行 yield 之后的代码。

    Args:
        app: FastAPI 应用实例
    """
    config = get_config()
    setup_logging()       # 初始化结构化日志
    init_metrics()       # 初始化 Prometheus 指标
    logger.info("NexusCockpit starting up...")

    # --- 0. 启动诊断: 打印 API Key 加载状态 (排查 401 问题) ---
    api_key = config.llm.ark_api_key
    if api_key:
        logger.info(f"LLM API Key loaded: {api_key[:12]}...{api_key[-4:]} (len={len(api_key)})")
        logger.info(f"LLM Base URL: {config.llm.ark_base_url}")
        logger.info(f"LLM Model: {config.llm.llm_model}")
    else:
        logger.error("LLM API Key is EMPTY! Please check .env.local -> ARK_API_KEY")

    # --- 1. 初始化 Embedding 服务 (将文本转为向量) ---
    embedding_service = EmbeddingService()
    app.state.embedding_service = embedding_service

    # --- 2. 初始化向量存储 (本地 Milvus / 云端 Zilliz, 由 VECTOR_STORE_PROVIDER 决定) ---
    vector_store = build_vector_store(embedding_service)
    try:
        vector_store.connect()
    except Exception as e:
        # Milvus 连接失败不阻止启动，后续可重试
        logger.error(f"Milvus connection failed (will continue): {e}")
    app.state.vector_store = vector_store

    # --- 3. 初始化图谱存储 (本地 Neo4j / 云端 AuraDB, 由 GRAPH_STORE_PROVIDER 决定) ---
    graph_store = build_graph_store()
    try:
        graph_store.connect()
    except Exception as e:
        logger.error(f"Neo4j connection failed (will continue): {e}")
    app.state.graph_store = graph_store

    # --- 4. 初始化车控适配器 (mock/http/mcp) ---
    vehicle_adapter = build_vehicle_adapter()
    app.state.vehicle_adapter = vehicle_adapter

    # --- 5. 初始化 OSS 对象存储 ---
    from nexus.core.oss import OSSStorage
    oss_storage = OSSStorage()
    oss_storage.connect()
    app.state.oss_storage = oss_storage

    # --- 6. 初始化 Redis 语义缓存 ---
    semantic_cache = SemanticCache(embedding_service)
    await semantic_cache.connect()
    app.state.semantic_cache = semantic_cache

    # --- 7. 初始化限流器 ---
    rate_limiter = RateLimiter()
    await rate_limiter.connect()
    app.state.rate_limiter = rate_limiter

    # --- 7.5. 初始化会话历史存储 (Redis 持久化，降级内存) ---
    session_store = SessionStore()
    await session_store.connect()
    app.state.session_store = session_store
    # 保留内存 dict 作为兼容 (部分代码仍直接引用)
    app.state.session_histories: dict[str, list] = {}

    # --- 7.6. 初始化 Langfuse 追踪监控器 ---
    langfuse_monitor = LangfuseMonitor()
    app.state.langfuse = langfuse_monitor

    # --- 8. 初始化 Agent 工作流 (核心!) ---
    # v2.0: Supervisor + 5 专家 Agent 多智能体架构
    try:
        from nexus.agent.supervisor_graph import SupervisorGraph
        from nexus.intent.router import IntentRouterService
        from nexus.memory.manager import MemoryManager
        from nexus.skills.registry import SkillRegistry

        # 技能注册中心: 管理所有车载/非车载技能（v2.0 装饰器自动发现）
        skill_registry = SkillRegistry(graph_store=graph_store, vehicle_adapter=vehicle_adapter)
        # 记忆管理器: 管理用户短期/长期记忆
        memory_manager = MemoryManager(vector_store, graph_store)
        memory_manager.connect()
        # 意图路由: 判断用户输入该交给哪个技能处理
        intent_router = IntentRouterService(
            tool_catalog=skill_registry.get_all_tools(),
        )

        # v2.0: SqliteSaver checkpoint 持久化
        checkpoint_saver = None
        try:
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
            import aiosqlite
            import os
            db_path = os.path.join(os.getcwd(), "data", "checkpoints", "nexus_checkpoints.db")
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            # 使用 aiosqlite 异步连接
            async with aiosqlite.connect(db_path) as conn:
                checkpoint_saver = AsyncSqliteSaver(conn)
                await checkpoint_saver.setup()
            # 重新打开连接用于运行时
            conn = aiosqlite.connect(db_path)
            checkpoint_saver = AsyncSqliteSaver(conn)
            logger.info(f"AsyncSqliteSaver checkpoint initialized at {db_path}")
        except ImportError:
            logger.warning("langgraph-checkpoint-sqlite or aiosqlite not installed, checkpoint disabled")
        except Exception as e:
            logger.warning(f"Checkpoint initialization failed (non-fatal): {e}")
            checkpoint_saver = None

        # v2.0: Supervisor 多智能体工作流
        agent_graph = SupervisorGraph(
            intent_router=intent_router,
            memory_manager=memory_manager,
            skill_registry=skill_registry,
            checkpoint_saver=checkpoint_saver,
        )

        # v2.0: Cherry 知识库 + 统一检索器
        try:
            from nexus.rag.cherry_kb import CherryKnowledgeBase
            from nexus.rag.unified_retriever import UnifiedRetriever
            cherry_kb = CherryKnowledgeBase(embedding_service)
            cherry_kb.connect(getattr(vector_store, "_connected", False) or vector_store)
            app.state.cherry_kb = cherry_kb
            logger.info("Cherry KnowledgeBase initialized")
        except Exception as e:
            logger.warning(f"Cherry KB init failed (non-fatal): {e}")
            app.state.cherry_kb = None

        app.state.skill_registry = skill_registry
        app.state.memory_manager = memory_manager
        app.state.agent_graph = agent_graph
        app.state.checkpoint_saver = checkpoint_saver
        logger.info("Supervisor graph initialized (v2.0)")
    except Exception as e:
        # Agent 初始化失败不阻止服务启动，但聊天功能不可用
        logger.error(f"Agent graph initialization failed: {e}")
        app.state.agent_graph = None

    # --- 会话历史存储 (内存兼容层，实际数据走 SessionStore) ---
    # 已在上方初始化 session_store 和 session_histories

    logger.info("NexusCockpit ready!")
    yield  # ← 应用运行期间在此暂停

    # ==================== 以下为关闭清理逻辑 ====================

    logger.info("NexusCockpit shutting down...")
    if hasattr(app.state, "vector_store") and app.state.vector_store:
        app.state.vector_store.disconnect()
    if hasattr(app.state, "graph_store") and app.state.graph_store:
        app.state.graph_store.close()
    if hasattr(app.state, "semantic_cache") and app.state.semantic_cache:
        await app.state.semantic_cache.close()
    if hasattr(app.state, "session_store") and app.state.session_store:
        await app.state.session_store.close()
    if hasattr(app.state, "embedding_service") and app.state.embedding_service:
        await app.state.embedding_service.close()
    if hasattr(app.state, "langfuse") and app.state.langfuse:
        app.state.langfuse.flush()
    if hasattr(app.state, "checkpoint_saver") and app.state.checkpoint_saver:
        try:
            # SqliteSaver 连接通过 conn 属性关闭
            if hasattr(app.state.checkpoint_saver, "conn"):
                app.state.checkpoint_saver.conn.close()
        except Exception:
            pass
    logger.info("NexusCockpit stopped")


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例。

    Returns:
        配置完成的 FastAPI 应用
    """
    config = get_config()

    app = FastAPI(
        title="NexusCockpit",
        description="Enterprise Vehicle Voice Agent with Multi-Agent, GraphRAG & MCP",
        version="2.0.0",
        lifespan=lifespan,
    )

    # CORS 跨域配置 — 允许前端 (localhost:3000) 访问后端 (localhost:8000)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.server.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册 API 路由
    app.include_router(health_router)     # /health 健康检查
    app.include_router(auth_router)       # /auth 认证接口
    app.include_router(chat_router)       # /chat 对话接口
    app.include_router(vehicle_router)    # /vehicle 车控接口
    app.include_router(admin_router)      # /admin 管理接口
    app.include_router(ws_router)         # /ws WebSocket 接口

    # 挂载 Prometheus 指标端点 (/metrics)
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    # 全局异常处理器 — 按异常类型返回不同 HTTP 状态码

    @app.exception_handler(RateLimitError)
    async def rate_limit_error_handler(request: Request, exc: RateLimitError):
        """限流异常返回 429 Too Many Requests。"""
        logger.warning(f"RateLimitError: {exc.message}")
        return JSONResponse(
            status_code=429,
            content={
                "error": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
            headers={"Retry-After": "60"},
        )

    @app.exception_handler(AuthError)
    async def auth_error_handler(request: Request, exc: AuthError):
        """认证异常返回 401 Unauthorized。"""
        logger.warning(f"AuthError: {exc.message}")
        return JSONResponse(
            status_code=401,
            content={
                "error": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(NexusError)
    async def nexus_error_handler(request: Request, exc: NexusError):
        """处理其他自定义异常，返回 500 内部服务器错误。"""
        logger.error(f"NexusError: {exc.code} - {exc.message}")
        return JSONResponse(
            status_code=500,
            content={
                "error": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        )

    # 请求计时中间件 — 记录每个请求的响应时间
    @app.middleware("http")
    async def add_timing(request: Request, call_next):
        """在响应头中添加 X-Response-Time-ms，便于性能监控。"""
        start = time.perf_counter()
        response = await call_next(request)
        duration = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Response-Time-ms"] = str(duration)
        return response

    return app


# 全局应用实例 (uvicorn 通过 nexus.main:app 引用)
app = create_app()


if __name__ == "__main__":
    # 直接运行: python -m nexus.main
    import uvicorn

    config = get_config()
    uvicorn.run(
        "nexus.main:app",
        host=config.server.host,
        port=config.server.port,
        reload=config.server.debug,
        log_level=config.server.log_level.lower(),
    )
