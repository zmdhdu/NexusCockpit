# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
座舱管理器 — 管理所有座舱的注册、查询、状态

核心职责:
1. 座舱注册（设置界面创建新座舱）
2. 座舱查询（路由层根据 cockpit_id 查询座舱配置）
3. 座舱状态（SubAgent 监控层查询座舱健康状态）
4. 座舱隔离（为每个座舱分配 Redis DB / Milvus collection 等）

v2.1 新增模块。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from nexus.core.logger import get_logger

logger = get_logger(__name__)

# 座舱注册时需要初始化的 Redis 默认 key
_COCKPIT_INIT_KEYS = {
    "stats",          # 座舱统计 hash
    "latencies",      # 延迟列表
    "session:active", # 活跃会话
}


@dataclass
class CockpitConfig:
    """单个座舱的配置。

    Attributes:
        cockpit_id: 唯一标识，如 "cockpit-01"
        name: 显示名称，如 "座舱1"
        user_id: 绑定用户 ID
        vehicle_adapter: 车控适配器类型 mock/http/mcp
        redis_db: Redis DB 编号（隔离）
        milvus_collection_prefix: Milvus collection 前缀
        created_at: 创建时间
        is_active: 是否启用
        theme_color: 主题色（前端个性化）
    """
    cockpit_id: str
    name: str
    user_id: str
    vehicle_adapter: str = "mock"
    redis_db: int = 0
    milvus_collection_prefix: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    is_active: bool = True
    theme_color: str = "#4fc3f7"
    # v2.2 简化: subagent_status 字段已移除（SubAgent 监控已删除）

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于 API 响应）。"""
        return {
            "cockpit_id": self.cockpit_id,
            "name": self.name,
            "user_id": self.user_id,
            "vehicle_adapter": self.vehicle_adapter,
            "redis_db": self.redis_db,
            "milvus_collection_prefix": self.milvus_collection_prefix,
            "created_at": self.created_at.isoformat(),
            "is_active": self.is_active,
            "theme_color": self.theme_color,
            # v2.2 简化: subagent_status 已移除
        }


class CockpitManager:
    """座舱管理器单例。

    管理所有座舱的生命周期，包括注册、查询、注销。
    启动时初始化 3 个默认座舱。

    用法:
        manager = CockpitManager()
        cockpit = manager.get_cockpit("cockpit-01")
        all_cockpits = manager.list_cockpits()
    """

    def __init__(self) -> None:
        self._cockpits: Dict[str, CockpitConfig] = {}
        self._next_seq: int = 0
        self._init_default_cockpits()

    def _init_default_cockpits(self) -> None:
        """初始化 3 个默认座舱。

        座舱名使用英文，避免中文编码在 MySQL/前端传输中出现乱码。
        """
        default_names = ["Cockpit One", "Cockpit Two", "Cockpit Three"]
        default_themes = ["#4fc3f7", "#66bb6a", "#ab47bc"]
        for i in range(1, 4):
            cid = f"cockpit-0{i}"
            self._cockpits[cid] = CockpitConfig(
                cockpit_id=cid,
                name=default_names[i - 1],
                user_id=f"user_0{i}",
                redis_db=i,
                milvus_collection_prefix=f"cockpit_0{i}",
                theme_color=default_themes[i - 1],
            )
        self._next_seq = 4  # 下一个注册的序号从 4 开始
        logger.info(f"CockpitManager initialized with {len(self._cockpits)} default cockpits")

    def get_cockpit(self, cockpit_id: str) -> Optional[CockpitConfig]:
        """查询单个座舱配置。

        Args:
            cockpit_id: 座舱唯一标识

        Returns:
            座舱配置，不存在返回 None
        """
        return self._cockpits.get(cockpit_id)

    def list_cockpits(self, include_inactive: bool = False) -> List[CockpitConfig]:
        """列出所有座舱。

        Args:
            include_inactive: 是否包含已注销的座舱

        Returns:
            座舱配置列表
        """
        if include_inactive:
            return list(self._cockpits.values())
        return [c for c in self._cockpits.values() if c.is_active]

    def register_cockpit(
        self,
        name: str,
        user_id: str,
        vehicle_adapter: str = "mock",
        theme_color: str = "#4fc3f7",
    ) -> CockpitConfig:
        """注册新座舱。

        使用 _next_seq 自增序号生成 ID，避免删除后 len() 导致 ID 冲突。
        注册后自动初始化中间件资源（W7）。

        Args:
            name: 座舱显示名称
            user_id: 绑定用户 ID
            vehicle_adapter: 车控适配器类型
            theme_color: 主题色

        Returns:
            新创建的座舱配置
        """
        idx = self._next_seq
        cid = f"cockpit-{idx:02d}"

        # 确保不与已存在的 cockpit_id 冲突
        while cid in self._cockpits:
            self._next_seq += 1
            idx = self._next_seq
            cid = f"cockpit-{idx:02d}"

        config = CockpitConfig(
            cockpit_id=cid,
            name=name,
            user_id=user_id,
            vehicle_adapter=vehicle_adapter,
            redis_db=idx,
            milvus_collection_prefix=f"cockpit_{idx:02d}",
            theme_color=theme_color,
        )
        self._cockpits[cid] = config
        self._next_seq += 1  # 序号递增，不随删除回退
        logger.info(f"Registered new cockpit: {cid} ({name})")

        # W7: 初始化中间件资源（非阻塞，失败不阻止注册）
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.initialize_middleware(cid))
            else:
                asyncio.run(self.initialize_middleware(cid))
        except RuntimeError:
            # No event loop in current thread, skip async init
            logger.debug(f"Skipping async middleware init for {cid} (no event loop)")

        return config

    async def initialize_middleware(self, cockpit_id: str) -> Dict[str, Any]:
        """初始化座舱的中间件资源（W7）。

        为新注册的座舱初始化:
        1. Redis: 设置座舱专属 DB 的初始 key、统计 hash
        2. Milvus: 确保座舱前缀的 collection 存在（Demo 共享模式跳过）
        3. MySQL: 创建座舱用户记录（如果不存在）
        4. 审计日志: 记录座舱初始化事件

        Args:
            cockpit_id: 座舱唯一标识

        Returns:
            各中间件初始化结果
        """
        config = self.get_cockpit(cockpit_id)
        if not config:
            return {"error": f"Cockpit {cockpit_id} not found"}

        results: Dict[str, Any] = {"cockpit_id": cockpit_id}

        # 1. 初始化 Redis（设置座舱统计 hash 初始值）
        try:
            import redis.asyncio as aioredis
            from nexus.config import get_config
            redis_config = get_config().redis
            client = aioredis.Redis(
                host=redis_config.host, port=redis_config.port,
                password=redis_config.password, db=redis_config.db,
                decode_responses=True,
            )

            # 初始化座舱统计 hash
            stats_key = f"{cockpit_id}:stats"
            await client.hset(stats_key, mapping={
                "chat_count": 0,
                "vehicle_cmd_count": 0,
                "cache_hits": 0,
                "cache_misses": 0,
                "error_count": 0,
                "created_at": datetime.now().isoformat(),
            })

            # 设置座舱配置缓存
            await client.hset(f"cockpit:{cockpit_id}:config", mapping={
                "name": config.name,
                "user_id": config.user_id,
                "redis_db": config.redis_db,
                "theme_color": config.theme_color,
                "is_active": "true",
            })

            await client.close()
            results["redis"] = "initialized"
            logger.info(f"Cockpit {cockpit_id}: Redis initialized (stats + config keys)")
        except Exception as e:
            results["redis"] = f"failed: {e}"
            logger.warning(f"Cockpit {cockpit_id}: Redis init failed: {e}")

        # 2. 初始化 Milvus（确保 collection 存在）
        try:
            # v2.2 简化: isolation_mode 已移除，单座舱使用共享 collection
            results["milvus"] = "skipped (shared mode, uses cockpit_id filter)"
            logger.info(f"Cockpit {cockpit_id}: Milvus uses shared collection")
        except Exception as e:
            results["milvus"] = f"failed: {e}"
            logger.warning(f"Cockpit {cockpit_id}: Milvus init check failed: {e}")

        # 3. 初始化 MySQL（创建座舱用户记录）
        try:
            from nexus.core.db_manager import get_db_manager
            db = get_db_manager()
            if db.is_connected:
                existing = await db.get_user(config.user_id)
                if not existing:
                    # 使用 user_id 作为 username（纯 ASCII，避免中文乱码）
                    await db.create_user(
                        user_id=config.user_id,
                        username=config.user_id,
                        cockpit_id=cockpit_id,
                        role="cockpit_user",
                        password_hash=None,
                    )
                    results["mysql"] = "user_created"
                    logger.info(f"Cockpit {cockpit_id}: MySQL user created ({config.user_id})")
                else:
                    results["mysql"] = "user_exists"
                    logger.debug(f"Cockpit {cockpit_id}: MySQL user already exists")

                # 写入审计日志
                await db.insert_audit_log(
                    cockpit_id=cockpit_id,
                    user_id=config.user_id,
                    action="cockpit_register",
                    detail={"name": config.name, "vehicle_adapter": config.vehicle_adapter},
                )
            else:
                results["mysql"] = "skipped (not connected)"
        except Exception as e:
            results["mysql"] = f"failed: {e}"
            logger.warning(f"Cockpit {cockpit_id}: MySQL init failed: {e}")

        logger.info(f"Cockpit {cockpit_id} middleware initialization complete: {results}")
        return results

    def unregister_cockpit(self, cockpit_id: str) -> bool:
        """注销座舱（软删除，标记 is_active=False）。序号不回退。

        Args:
            cockpit_id: 座舱唯一标识

        Returns:
            是否成功注销
        """
        config = self._cockpits.get(cockpit_id)
        if config:
            config.is_active = False
            logger.info(f"Unregistered cockpit: {cockpit_id} (soft delete)")
            return True
        return False

    def update_cockpit(
        self, cockpit_id: str, updates: Dict[str, Any]
    ) -> Optional[CockpitConfig]:
        """更新座舱配置。

        Args:
            cockpit_id: 座舱唯一标识
            updates: 要更新的字段字典

        Returns:
            更新后的座舱配置，不存在返回 None
        """
        config = self._cockpits.get(cockpit_id)
        if not config:
            return None

        # 仅允许更新合法字段
        allowed_fields = {
            "name", "user_id", "vehicle_adapter", "theme_color", "is_active",
            # v2.2 简化: subagent_status 已移除
        }
        for key, value in updates.items():
            if key in allowed_fields:
                setattr(config, key, value)

        logger.info(f"Updated cockpit: {cockpit_id} fields={list(updates.keys())}")
        return config

    def get_redis_db(self, cockpit_id: str) -> int:
        """获取座舱对应的 Redis DB 编号。

        Args:
            cockpit_id: 座舱唯一标识

        Returns:
            Redis DB 编号，不存在返回 0
        """
        config = self._cockpits.get(cockpit_id)
        return config.redis_db if config else 0

    def get_milvus_prefix(self, cockpit_id: str) -> str:
        """获取座舱对应的 Milvus collection 前缀。

        Args:
            cockpit_id: 座舱唯一标识

        Returns:
            Milvus collection 前缀，不存在返回空字符串
        """
        config = self._cockpits.get(cockpit_id)
        return config.milvus_collection_prefix if config else ""

    def get_stats_summary(self) -> Dict[str, Any]:
        """获取座舱统计摘要（用于数据中台）。

        Returns:
            包含总数、活跃数、各座舱状态的字典
        """
        all_cockpits = list(self._cockpits.values())
        active = [c for c in all_cockpits if c.is_active]
        return {
            "total": len(all_cockpits),
            "active": len(active),
            "inactive": len(all_cockpits) - len(active),
            "cockpits": [c.to_dict() for c in active],
        }


# 全局单例
_cockpit_manager: Optional[CockpitManager] = None


def get_cockpit_manager() -> CockpitManager:
    """获取座舱管理器全局单例。

    Returns:
        CockpitManager 实例
    """
    global _cockpit_manager
    if _cockpit_manager is None:
        _cockpit_manager = CockpitManager()
    return _cockpit_manager
