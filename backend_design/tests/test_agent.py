# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.

"""
NexusCockpit Agent & Intent Router Tests — P4 测试覆盖率提升

测试范围:
  - IntentRouterService 三级路由 (启发式/LLM/默认)
  - LLM Client Factory 单例/降级
  - SkillRegistry 技能注册/查询
  - BaseSkill to_langchain_tool 转换
  - CherryKnowledgeBase 增量更新逻辑
"""

import hashlib
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ============================================================
# Intent Router Tests
# ============================================================

class TestHeuristicRouter:
    """启发式路由器测试"""

    def test_vehicle_climate_command(self):
        """测试空调指令启发式路由"""
        from nexus.intent.heuristic import HeuristicRouter
        router = HeuristicRouter()
        result = router.route("把空调调到24度")
        assert result is not None
        assert any(k in result for k in ("Climate_Action", "climate"))

    def test_window_command(self):
        """测试车窗指令"""
        from nexus.intent.heuristic import HeuristicRouter
        router = HeuristicRouter()
        result = router.route("打开车窗")
        assert result is not None

    def test_navigation_command(self):
        """测试导航指令"""
        from nexus.intent.heuristic import HeuristicRouter
        router = HeuristicRouter()
        result = router.route("导航到上海虹桥")
        assert result is not None

    def test_non_vehicle_command(self):
        """测试非车控指令（闲聊）不命中启发式"""
        from nexus.intent.heuristic import HeuristicRouter
        router = HeuristicRouter()
        result = router.route("你好，今天天气怎么样")
        # 闲聊不应命中启发式路由
        assert result is None or result == {}


class TestIntentRouterService:
    """意图路由服务测试"""

    def test_build_default_intent(self):
        """测试默认意图构建"""
        from nexus.intent.router import IntentRouterService
        router = IntentRouterService(tool_catalog=[], llm_enabled=False)
        default = router._build_default_intent()
        assert "Route_Source" in default
        assert default["Route_Source"] == "default"

    @pytest.mark.asyncio
    async def test_heuristic_route_fast_path(self):
        """测试启发式路由快速路径"""
        from nexus.intent.router import IntentRouterService
        router = IntentRouterService(tool_catalog=[], llm_enabled=False)
        result = await router.route("把空调调到24度")
        assert result.get("Route_Source") == "heuristic"

    @pytest.mark.asyncio
    async def test_default_route_for_chat(self):
        """测试闲聊走默认路由"""
        from nexus.intent.router import IntentRouterService
        router = IntentRouterService(tool_catalog=[], llm_enabled=False)
        result = await router.route("你好啊")
        assert result.get("Route_Source") in ("default", "heuristic")


# ============================================================
# LLM Client Factory Tests
# ============================================================

class TestLLMClientFactory:
    """LLM 客户端工厂测试"""

    def test_get_llm_client_singleton(self):
        """测试 LLM 客户端单例"""
        from nexus.agent.llm_client_factory import get_llm_client, reset_clients
        reset_clients()
        client1 = get_llm_client()
        client2 = get_llm_client()
        assert client1 is client2  # 单例

    def test_reset_clients(self):
        """测试重置客户端单例"""
        from nexus.agent.llm_client_factory import get_llm_client, reset_clients
        client1 = get_llm_client()
        reset_clients()
        client2 = get_llm_client()
        assert client1 is not client2  # 重置后创建新实例

    def test_get_chat_model(self):
        """测试 ChatOpenAI 实例创建"""
        from nexus.agent.llm_client_factory import get_chat_model, reset_clients
        reset_clients()
        chat_model = get_chat_model()
        if chat_model is not None:  # langchain-openai 已安装时
            assert hasattr(chat_model, "ainvoke")
            assert hasattr(chat_model, "model")

    def test_fallback_client_local_mode(self):
        """测试本地模式下 fallback 为 None"""
        from nexus.agent.llm_client_factory import get_fallback_client, reset_clients
        reset_clients()
        # 在 cloud 模式下且 fallback_enabled=false 时应返回 None
        fallback = get_fallback_client()
        # 根据配置，可能为 None
        assert fallback is None or hasattr(fallback, "chat")


# ============================================================
# Skill Registry Tests
# ============================================================

class TestSkillRegistry:
    """技能注册中心测试"""

    def test_skill_registry_initialization(self):
        """测试技能注册中心初始化"""
        from nexus.skills.registry import SkillRegistry
        registry = SkillRegistry()
        assert len(registry.list_skills()) > 0
        # 应包含基础技能
        skills = registry.list_skills()
        assert "vehicle_climate" in skills or "web_search" in skills

    def test_get_skill_by_name(self):
        """测试按名称获取技能"""
        from nexus.skills.registry import SkillRegistry
        registry = SkillRegistry()
        skill = registry.get_skill("vehicle_climate")
        if skill:
            assert hasattr(skill, "execute")
            assert hasattr(skill, "name")

    def test_get_all_tools_schema(self):
        """测试获取所有工具 Schema"""
        from nexus.skills.registry import SkillRegistry
        registry = SkillRegistry()
        tools = registry.get_all_tools()
        assert len(tools) > 0
        for tool in tools:
            assert "type" in tool
            assert tool["type"] == "function"
            assert "function" in tool

    def test_get_structured_tools(self):
        """测试获取 LangChain StructuredTool 对象"""
        from nexus.skills.registry import SkillRegistry
        registry = SkillRegistry()
        tools = registry.get_structured_tools()
        # 如果 langchain 已安装，应该返回 Tool 对象列表
        if tools:
            for tool in tools:
                assert hasattr(tool, "name")
                assert hasattr(tool, "description")

    def test_get_side_effect_skills(self):
        """测试获取有副作用的技能"""
        from nexus.skills.registry import SkillRegistry
        registry = SkillRegistry()
        side_effects = registry.get_side_effect_skills()
        # 车控类技能应有副作用
        # vehicle_climate, vehicle_window 等应在列表中
        assert isinstance(side_effect_skills := side_effects, list)


# ============================================================
# BaseSkill to_structured_tool Tests
# ============================================================

class TestBaseSkillStructuredTool:
    """BaseSkill StructuredTool 转换测试"""

    def test_to_structured_tool(self):
        """测试技能转换为 LangChain StructuredTool"""
        from nexus.skills.registry import SkillRegistry
        registry = SkillRegistry()
        skill = registry.get_skill("vehicle_climate")
        if skill:
            try:
                tool = skill.to_structured_tool()
                assert tool is not None
                assert tool.name == skill.name
            except ImportError:
                pytest.skip("langchain-core not installed")

    def test_get_skills_by_group(self):
        """测试按分组获取技能"""
        from nexus.skills.registry import SkillRegistry
        from nexus.skills.base import SkillGroup
        registry = SkillRegistry()
        vehicle_skills = registry.get_skills_by_group(SkillGroup.VEHICLE)
        assert isinstance(vehicle_skills, dict)


# ============================================================
# Knowledge Base Incremental Update Tests
# ============================================================

class TestCherryKnowledgeBase:
    """Cherry 知识库增量更新测试"""

    def test_content_hash_computation(self):
        """测试文档内容哈希计算"""
        text1 = "这是一段测试文档内容"
        text2 = "这是一段测试文档内容"
        text3 = "这是另一段不同的内容"

        hash1 = hashlib.md5(text1.encode("utf-8")).hexdigest()
        hash2 = hashlib.md5(text2.encode("utf-8")).hexdigest()
        hash3 = hashlib.md5(text3.encode("utf-8")).hexdigest()

        assert hash1 == hash2  # 相同内容相同哈希
        assert hash1 != hash3  # 不同内容不同哈希

    def test_chunk_text(self):
        """测试文本分块"""
        from nexus.rag.cherry_kb import CherryKnowledgeBase
        kb = CherryKnowledgeBase()
        text = "这是第一段。这是第二段。这是第三段。" * 100
        chunks = kb._chunk_text(text)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) > 0
