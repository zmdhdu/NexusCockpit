"""
NexusCockpit Test Suite
"""

import pytest

from nexus.models.state import AgentState
from nexus.vehicle.mock import MockVehicleBus


class TestMockVehicleBus:
    """测试模拟车控总线"""

    @pytest.fixture
    def bus(self):
        return MockVehicleBus()

    def test_climate_set_temp(self, bus):
        result = bus.vehicle_climate(op="set_temp", target_temp=24)
        assert result.success
        assert bus.climate["temperature"] == 24
        assert "24" in result.message

    def test_climate_temp_up(self, bus):
        original = bus.climate["temperature"]
        result = bus.vehicle_climate(op="temp_up")
        assert result.success
        assert bus.climate["temperature"] == original + 1

    def test_window_open(self, bus):
        result = bus.vehicle_window(op="open", position="all")
        assert result.success
        assert bus.windows["all"] == 100

    def test_window_close(self, bus):
        result = bus.vehicle_window(op="close", position="front_left")
        assert result.success
        assert bus.windows["front_left"] == 0

    def test_seat_heat(self, bus):
        result = bus.vehicle_seat(op="heat_on", position="driver", level=2)
        assert result.success
        assert bus.seats["driver"]["heat"] == 2

    def test_navigation(self, bus):
        result = bus.vehicle_navigation(destination="上海虹桥")
        assert result.success
        assert bus.navigation["destination"] == "上海虹桥"

    def test_media_play(self, bus):
        result = bus.vehicle_media(op="play", source="local")
        assert result.success
        assert bus.media["playing"] is True

    def test_vehicle_status(self, bus):
        result = bus.vehicle_status()
        assert result.success
        assert "胎压" in result.message

    def test_invoke_command(self, bus):
        result = bus.invoke_command("vehicle_climate", {"op": "set_temp", "target_temp": 26})
        assert result.success
        assert bus.climate["temperature"] == 26

    def test_invoke_unknown_command(self, bus):
        result = bus.invoke_command("unknown_command", {})
        assert not result.success


class TestHeuristicRouter:
    """测试启发式路由"""

    @pytest.fixture
    def router(self):
        from nexus.intent.heuristic import HeuristicRouter
        return HeuristicRouter()

    def test_climate_route(self, router):
        result = router.route("把空调调到24度")
        assert "Climate_Action" in result
        assert result["Climate_Action"]["target_temp"] == 24

    def test_window_route(self, router):
        result = router.route("打开车窗")
        assert "Window_Action" in result
        assert result["Window_Action"]["op"] == "open"

    def test_navigation_route(self, router):
        result = router.route("导航到上海虹桥火车站")
        assert "Navigation_Action" in result
        assert "上海虹桥" in result["Navigation_Action"]["destination"]

    def test_media_route(self, router):
        result = router.route("播放音乐")
        assert "Media_Action" in result
        assert result["Media_Action"]["op"] == "play"

    def test_no_match(self, router):
        result = router.route("今天天气真好")
        assert result == {}


class TestSkillRegistry:
    """测试技能注册中心"""

    @pytest.fixture
    def registry(self):
        from nexus.skills.registry import SkillRegistry
        return SkillRegistry()

    def test_list_skills(self, registry):
        skills = registry.list_skills()
        assert "vehicle_climate" in skills
        assert "web_search" in skills
        assert "order_food" in skills

    def test_get_all_tools(self, registry):
        tools = registry.get_all_tools()
        assert len(tools) >= 9

    @pytest.mark.asyncio
    async def test_execute_climate(self, registry):
        result = await registry.execute("vehicle_climate", {"op": "set_temp", "target_temp": 25})
        assert result.status == "ok"
        assert result.action == "vehicle_climate"

    @pytest.mark.asyncio
    async def test_execute_unknown(self, registry):
        result = await registry.execute("nonexistent", {})
        assert result.status == "error"


class TestAgentState:
    """测试 Agent 状态"""

    def test_default_state(self):
        state = AgentState()
        assert state.user_input == ""
        assert state.user_id == "default"
        assert state.recalled_memories == []
        assert state.intent == {}
        assert state.skill_handled is False

    def test_custom_state(self):
        state = AgentState(
            user_input="把空调调到24度",
            user_id="test_user",
            session_id="session_001",
        )
        assert state.user_input == "把空调调到24度"
        assert state.user_id == "test_user"
