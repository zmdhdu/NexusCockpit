# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

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
from nexus.api.routes.asr import router as asr_router  # v2.1 ASR
from nexus.api.routes.auth import router as auth_router
from nexus.api.routes.chat import router as chat_router
from nexus.api.routes.chat_sessions import router as chat_sessions_router  # v2.2.2
from nexus.api.routes.cockpit import router as cockpit_router  # v2.1
from nexus.api.routes.dataplatform import router as dataplatform_router  # v2.1
from nexus.api.routes.health import router as health_router
from nexus.api.routes.middleware_status import router as middleware_router  # v2.1
from nexus.api.routes.settings import router as settings_router  # v2.1
from nexus.api.routes.vehicle import router as vehicle_router
from nexus.api.websocket import router as ws_router
from nexus.config import get_config
from nexus.core.exceptions import AuthError, NexusError, RateLimitError
from nexus.core.logger import get_logger, setup_logging
from nexus.middleware.rate_limiter import RateLimiter
from nexus.middleware.redis_cache import SemanticCache
from nexus.middleware.session_store import SessionStore
from nexus.observability.cockpit_metrics import CockpitMetrics  # v2.1
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

    # --- 0. 启动诊断: 打印 API Key 加载状态 (脱敏，仅显示长度和末 4 位) ---
    api_key = config.llm.ark_api_key
    if api_key:
        logger.info(f"LLM API Key loaded: ***{api_key[-4:]} (len={len(api_key)})")
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

    # --- 7.7. 初始化 v2.1 指标 Redis（需要在 Agent 初始化前创建，供 MainAgent 确认层使用）---
    import redis.asyncio as aioredis
    redis_config = config.redis
    metrics_redis = aioredis.Redis(
        host=redis_config.host, port=redis_config.port,
        password=redis_config.password, db=redis_config.db,
        decode_responses=True,
    )
    app.state.cockpit_metrics_redis = metrics_redis

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
            # 使用 aiosqlite 异步连接执行 setup
            setup_conn = await aiosqlite.connect(db_path)
            try:
                checkpoint_saver = AsyncSqliteSaver(setup_conn)
                await checkpoint_saver.setup()
            finally:
                await setup_conn.close()
            # 创建运行时持久连接（保持打开直到应用关闭）
            runtime_conn = await aiosqlite.connect(db_path)
            checkpoint_saver = AsyncSqliteSaver(runtime_conn)
            app.state._checkpoint_conn = runtime_conn  # 保持强引用防止 GC
            logger.info(f"AsyncSqliteSaver checkpoint initialized at {db_path}")
        except ImportError:
            logger.warning("langgraph-checkpoint-sqlite or aiosqlite not installed, checkpoint disabled")
        except Exception as e:
            logger.warning(f"Checkpoint initialization failed (non-fatal): {e}")
            checkpoint_saver = None

        # v2.0: Supervisor 多智能体工作流（v2.1: 传入 redis_client 给 MainAgent 确认层）
        agent_graph = SupervisorGraph(
            intent_router=intent_router,
            memory_manager=memory_manager,
            skill_registry=skill_registry,
            checkpoint_saver=checkpoint_saver,
            redis_client=metrics_redis,
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

    # --- 8.5. 初始化 MySQL 数据库管理器（v2.1 日志持久化 + 用户管理）---
    try:
        from nexus.core.db_manager import get_db_manager
        db_manager = get_db_manager()
        await db_manager.connect()
        app.state.db_manager = db_manager
    except Exception as e:
        logger.warning(f"MySQL database manager init failed (non-fatal): {e}")

    # --- 9. v2.1: 初始化座舱管理器 + SubAgent 监控 + MainAgent 确认 ---
    try:
        from nexus.core.cockpit_manager import get_cockpit_manager
        from nexus.observability.cockpit_metrics import set_cockpit_metrics

        cockpit_manager = get_cockpit_manager()
        app.state.cockpit_manager = cockpit_manager

        # 初始化指标采集器（使用已在步骤 7.7 创建的 Redis 连接）
        cockpit_metrics = CockpitMetrics(redis_client=metrics_redis)
        set_cockpit_metrics(cockpit_metrics)

        logger.info(f"CockpitManager initialized with {len(cockpit_manager.list_cockpits())} cockpits")

        # 启动 SubAgent 监控（如果配置启用）
        if config.cockpit.mainagent_confirm_enabled:
            try:
                from nexus.agent.subagent_monitor import SubAgentManager

                # 创建 SubAgent 管理器（传入 embedding_service 用于 Layer 2 向量匹配）
                subagent_manager = SubAgentManager(
                    llm_client=app.state.agent_graph.llm_client if app.state.agent_graph else None,
                    redis_client=metrics_redis,
                    embedding_service=app.state.embedding_service,
                )
                # 启动所有座舱的 SubAgent 监控
                cockpit_ids = [c.cockpit_id for c in cockpit_manager.list_cockpits()]
                await subagent_manager.start_all(cockpit_ids)
                app.state.subagent_manager = subagent_manager

                # 启动 MainAgent 确认层监听（redis_client 已在 SupervisorGraph 初始化时传入）
                if app.state.agent_graph:
                    await app.state.agent_graph.mainagent_confirm.start_listening()

                logger.info(f"SubAgent monitors started for {len(cockpit_ids)} cockpits")
            except Exception as e:
                logger.warning(f"SubAgent monitor startup failed (non-fatal): {e}")
        else:
            logger.info("SubAgent monitoring disabled by config")

    except Exception as e:
        logger.error(f"v2.1 cockpit initialization failed: {e}")

    # --- 10. v2.1: 启动数据保留策略管理器（后台自动清理过期日志）---
    try:
        from nexus.observability.data_retention import get_retention_manager
        retention_manager = get_retention_manager()
        await retention_manager.start()
        app.state.retention_manager = retention_manager
        logger.info("DataRetentionManager started (cleanup interval: 24h)")
    except Exception as e:
        logger.warning(f"DataRetentionManager startup failed (non-fatal): {e}")

    logger.info("NexusCockpit ready!")
    yield  # ← 应用运行期间在此暂停

    # ==================== 以下为关闭清理逻辑 ====================

    logger.info("NexusCockpit shutting down...")

    # v2.1: 停止 SubAgent 监控
    if hasattr(app.state, "subagent_manager"):
        await app.state.subagent_manager.stop_all()
    # v2.1: 停止 MainAgent 监听
    if hasattr(app.state, "agent_graph") and app.state.agent_graph:
        try:
            await app.state.agent_graph.mainagent_confirm.stop_listening()
        except Exception:
            pass
    # v2.1: 停止数据保留管理器
    if hasattr(app.state, "retention_manager"):
        await app.state.retention_manager.stop()
    # v2.1: 关闭指标 Redis
    if hasattr(app.state, "cockpit_metrics_redis"):
        await app.state.cockpit_metrics_redis.close()
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
    if hasattr(app.state, "_checkpoint_conn"):
        try:
            await app.state._checkpoint_conn.close()
            logger.info("Checkpoint SQLite connection closed")
        except Exception as e:
            logger.warning(f"Checkpoint connection close failed (non-fatal): {e}")
    logger.info("NexusCockpit stopped")


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例。

    Returns:
        配置完成的 FastAPI 应用
    """
    config = get_config()

    app = FastAPI(
        title="NexusCockpit",
        description="Enterprise Vehicle Voice Agent with Multi-Agent, GraphRAG & MCP — v2.1 Multi-Cockpit CS Architecture",
        version="2.1.0",
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
    @app.get("/", tags=["root"])
    async def root():
        """根路径：返回项目基本信息。"""
        return {
            "name": "NexusCockpit",
            "version": "2.1.0",
            "description": "Enterprise Vehicle Voice Agent Platform",
        }

    app.include_router(health_router)       # /health 健康检查
    app.include_router(auth_router)         # /auth 认证接口
    app.include_router(chat_router)         # /chat 对话接口
    app.include_router(chat_sessions_router) # /chat/sessions 多会话管理
    app.include_router(vehicle_router)      # /vehicle 车控接口
    app.include_router(admin_router)        # /admin 管理接口
    app.include_router(cockpit_router)      # /cockpit v2.1 座舱接口
    app.include_router(dataplatform_router) # /dataplatform v2.1 数据中台
    app.include_router(middleware_router)   # /middleware v2.1 中间件状态
    app.include_router(settings_router)     # /settings v2.1 设置中心
    app.include_router(asr_router)          # /asr v2.1 语音识别
    app.include_router(ws_router)           # /ws WebSocket 接口

    # 挂载 Prometheus 指标端点 (/metrics)
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    # 挂载静态音频文件目录 (/audio/music/*.wav)
    # 用于车机媒体播放功能，前端通过 /audio/music/track_01.wav 访问
    from fastapi.staticfiles import StaticFiles
    import os as _os
    _audio_dir = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))), "assets", "audio")
    if _os.path.isdir(_audio_dir):
        app.mount("/audio", StaticFiles(directory=_audio_dir), name="audio")
        logger.info(f"Audio static files mounted at /audio from {_audio_dir}")

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

    # v2.1: 纯 ASGI 中间件 — 提取座舱 ID + 请求计时
    # 使用纯 ASGI 而非 @app.middleware("http")，因为 BaseHTTPMiddleware
    # 会在单独的 task 中运行端点，导致 contextvars 无法传播到端点。
    # 纯 ASGI 中间件在同一个上下文中运行，确保 set_cockpit_id() 生效。
    from nexus.core.tenant_context import set_cockpit_id

    class CockpitContextMiddleware:
        """纯 ASGI 中间件 — 提取 X-Cockpit-Id 并设置到 contextvars。"""

        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                # 从请求头提取 X-Cockpit-Id（ASGI headers 均为小写 bytes）
                for key, val in scope.get("headers", []):
                    if key == b"x-cockpit-id":
                        set_cockpit_id(val.decode("utf-8", errors="ignore"))
                        break

            # 计时
            start = time.perf_counter()

            # 包装 send 以注入 X-Response-Time-ms
            async def send_wrapper(message):
                if message["type"] == "http.response.start":
                    duration = round((time.perf_counter() - start) * 1000, 2)
                    raw_headers = message.get("headers", [])
                    raw_headers.append((b"x-response-time-ms", str(duration).encode()))
                    message["headers"] = raw_headers
                await send(message)

            await self.app(scope, receive, send_wrapper)

    app.add_middleware(CockpitContextMiddleware)

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
