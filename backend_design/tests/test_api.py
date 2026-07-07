"""
NexusCockpit API Integration Tests
"""

import pytest
from httpx import AsyncClient, ASGITransport


@pytest.fixture
async def client():
    """创建测试客户端"""
    from nexus.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_root(client):
    """测试根路径"""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "NexusCockpit"


@pytest.mark.asyncio
async def test_health(client):
    """测试健康检查"""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "components" in data


@pytest.mark.asyncio
async def test_admin_skills(client):
    """测试技能列表"""
    response = await client.get("/admin/skills")
    assert response.status_code == 200
    data = response.json()
    assert "skills" in data
    assert data["count"] >= 0


@pytest.mark.asyncio
async def test_vehicle_status(client):
    """测试车辆状态"""
    response = await client.get("/vehicle/status")
    assert response.status_code == 200
    data = response.json()
    assert "success" in data


@pytest.mark.asyncio
async def test_vehicle_command(client):
    """测试车控命令"""
    response = await client.post(
        "/vehicle/command",
        json={
            "command": "vehicle_climate",
            "arguments": {"op": "set_temp", "target_temp": 24},
            "user_id": "test",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
