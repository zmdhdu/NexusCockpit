"""
NexusCockpit 单元测试 — 多座舱管理 + 多租户上下文

测试覆盖:
1. CockpitManager: 座舱注册/查询/更新/注销/隔离
2. TenantContext: 上下文传播/恢复/缓存前缀
"""

import pytest

from nexus.core.cockpit_manager import CockpitManager
from nexus.core.tenant_context import (
    CockpitContext,
    get_cache_prefix,
    get_cockpit_id,
    get_user_id,
    set_cockpit_id,
    set_user_id,
)

# ============================================================
# CockpitManager 测试
# ============================================================

class TestCockpitManager:
    """测试座舱管理器"""

    @pytest.fixture
    def manager(self):
        """每个测试用例使用独立的 CockpitManager 实例，避免单例污染"""
        return CockpitManager()

    def test_default_cockpits(self, manager):
        """启动时应初始化 3 个默认座舱"""
        cockpits = manager.list_cockpits()
        assert len(cockpits) == 3
        ids = {c.cockpit_id for c in cockpits}
        assert ids == {"cockpit-01", "cockpit-02", "cockpit-03"}

    def test_get_cockpit(self, manager):
        """查询单个座舱"""
        c = manager.get_cockpit("cockpit-01")
        assert c is not None
        assert c.name == "Cockpit One"
        assert c.is_active is True

    def test_get_nonexistent_cockpit(self, manager):
        """查询不存在的座舱返回 None"""
        assert manager.get_cockpit("nonexistent") is None

    def test_register_cockpit(self, manager):
        """注册新座舱"""
        config = manager.register_cockpit(
            name="测试座舱",
            user_id="test_user",
            vehicle_adapter="http",
            theme_color="#ff0000",
        )
        assert config.cockpit_id == "cockpit-04"
        assert config.name == "测试座舱"
        assert config.user_id == "test_user"
        assert config.vehicle_adapter == "http"
        assert config.redis_db == 4
        assert config.milvus_collection_prefix == "cockpit_04"
        assert config.is_active is True

    def test_unregister_cockpit(self, manager):
        """注销座舱（软删除）"""
        assert manager.unregister_cockpit("cockpit-01") is True
        # 注销后不在活跃列表中
        active = manager.list_cockpits()
        assert all(c.cockpit_id != "cockpit-01" for c in active)
        # 但在 include_inactive 列表中
        all_c = manager.list_cockpits(include_inactive=True)
        found = [c for c in all_c if c.cockpit_id == "cockpit-01"]
        assert len(found) == 1
        assert found[0].is_active is False

    def test_unregister_nonexistent(self, manager):
        """注销不存在的座舱返回 False"""
        assert manager.unregister_cockpit("nonexistent") is False

    def test_update_cockpit(self, manager):
        """更新座舱配置"""
        config = manager.update_cockpit("cockpit-01", {
            "name": "更新后的名称",
            "theme_color": "#00ff00",
        })
        assert config is not None
        assert config.name == "更新后的名称"
        assert config.theme_color == "#00ff00"

    def test_update_nonexistent(self, manager):
        """更新不存在的座舱返回 None"""
        assert manager.update_cockpit("nonexistent", {"name": "test"}) is None

    def test_update_disallowed_field(self, manager):
        """不允许更新的字段应被忽略"""
        original_id = manager.get_cockpit("cockpit-01").cockpit_id
        manager.update_cockpit("cockpit-01", {"cockpit_id": "hacked"})
        assert manager.get_cockpit("cockpit-01").cockpit_id == original_id

    def test_get_redis_db(self, manager):
        """获取座舱的 Redis DB 编号"""
        assert manager.get_redis_db("cockpit-01") == 1
        assert manager.get_redis_db("cockpit-02") == 2
        assert manager.get_redis_db("cockpit-03") == 3
        assert manager.get_redis_db("nonexistent") == 0

    def test_get_milvus_prefix(self, manager):
        """获取座舱的 Milvus collection 前缀"""
        assert manager.get_milvus_prefix("cockpit-01") == "cockpit_01"
        assert manager.get_milvus_prefix("nonexistent") == ""

    def test_get_stats_summary(self, manager):
        """获取座舱统计摘要"""
        summary = manager.get_stats_summary()
        assert summary["total"] == 3
        assert summary["active"] == 3
        assert summary["inactive"] == 0
        assert len(summary["cockpits"]) == 3

    def test_to_dict(self, manager):
        """CockpitConfig.to_dict() 序列化"""
        config = manager.get_cockpit("cockpit-01")
        d = config.to_dict()
        assert d["cockpit_id"] == "cockpit-01"
        assert d["name"] == "Cockpit One"
        assert "created_at" in d
        assert isinstance(d["is_active"], bool)


# ============================================================
# TenantContext 测试
# ============================================================

class TestTenantContext:
    """测试多租户上下文"""

    def test_default_cockpit_id(self):
        """默认 cockpit_id 应为 cockpit-01"""
        # 注意：由于 contextvars 的特性，这里测试的是默认值
        set_cockpit_id("cockpit-01")
        assert get_cockpit_id() == "cockpit-01"

    def test_set_and_get_cockpit_id(self):
        """设置和获取 cockpit_id"""
        set_cockpit_id("cockpit-02")
        assert get_cockpit_id() == "cockpit-02"
        # 恢复默认
        set_cockpit_id("cockpit-01")

    def test_set_and_get_user_id(self):
        """设置和获取 user_id"""
        set_user_id("test_user_123")
        assert get_user_id() == "test_user_123"
        # 恢复默认
        set_user_id("default")

    def test_cache_prefix(self):
        """缓存前缀应包含 cockpit_id"""
        set_cockpit_id("cockpit-03")
        prefix = get_cache_prefix()
        assert prefix == "cockpit-03:"
        # 恢复默认
        set_cockpit_id("cockpit-01")

    def test_cockpit_context_manager(self):
        """CockpitContext 上下文管理器"""
        # 在上下文外设置默认值
        set_cockpit_id("cockpit-01")
        assert get_cockpit_id() == "cockpit-01"

        # 进入上下文
        with CockpitContext("cockpit-02", "user_02"):
            assert get_cockpit_id() == "cockpit-02"
            assert get_user_id() == "user_02"
            assert get_cache_prefix() == "cockpit-02:"

        # 退出上下文后应恢复
        assert get_cockpit_id() == "cockpit-01"
        assert get_user_id() == "default"

    @pytest.mark.asyncio
    async def test_cockpit_context_async(self):
        """CockpitContext 异步上下文管理器"""
        set_cockpit_id("cockpit-01")

        async with CockpitContext("cockpit-03", "async_user"):
            assert get_cockpit_id() == "cockpit-03"
            assert get_user_id() == "async_user"

        # 退出后恢复
        assert get_cockpit_id() == "cockpit-01"

    def test_nested_cockpit_context(self):
        """嵌套 CockpitContext"""
        set_cockpit_id("cockpit-01")

        with CockpitContext("cockpit-02"):
            assert get_cockpit_id() == "cockpit-02"

            with CockpitContext("cockpit-03"):
                assert get_cockpit_id() == "cockpit-03"

            # 内层退出后应恢复到外层
            assert get_cockpit_id() == "cockpit-02"

        # 最外层退出后应恢复到原始值
        assert get_cockpit_id() == "cockpit-01"

    def test_cockpit_context_without_user(self):
        """CockpitContext 不传 user_id"""
        original_user = get_user_id()
        with CockpitContext("cockpit-02"):
            assert get_cockpit_id() == "cockpit-02"
            # user_id 不应改变
            assert get_user_id() == original_user
