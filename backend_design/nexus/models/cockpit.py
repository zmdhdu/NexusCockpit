"""
座舱数据模型 — v2.1 Pydantic Schema 定义

定义座舱 API 的请求/响应模型。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ============================================================
# 座舱 CRUD 模型
# ============================================================

class CockpitCreateRequest(BaseModel):
    """注册新座舱请求。"""
    name: str = Field(..., description="座舱显示名称", examples=["座舱4"])
    user_id: str = Field(..., description="绑定用户 ID", examples=["user_04"])
    vehicle_adapter: str = Field(default="mock", description="车控适配器: mock/http/mcp")
    theme_color: str = Field(default="#4fc3f7", description="主题色 hex")


class CockpitUpdateRequest(BaseModel):
    """更新座舱配置请求。"""
    name: Optional[str] = None
    user_id: Optional[str] = None
    vehicle_adapter: Optional[str] = None
    theme_color: Optional[str] = None
    is_active: Optional[bool] = None


class CockpitResponse(BaseModel):
    """座舱信息响应。"""
    cockpit_id: str
    name: str
    user_id: str
    vehicle_adapter: str
    redis_db: int
    milvus_collection_prefix: str
    created_at: str
    is_active: bool
    theme_color: str
    subagent_status: str


class CockpitListResponse(BaseModel):
    """座舱列表响应。"""
    total: int
    active: int
    cockpits: List[CockpitResponse]


# ============================================================
# 座舱状态模型
# ============================================================

class CockpitStatusResponse(BaseModel):
    """座舱状态响应（含车辆状态和指标）。"""
    cockpit_id: str
    name: str
    is_active: bool
    subagent_status: str
    vehicle_status: Optional[Dict[str, Any]] = None
    metrics: Optional[Dict[str, Any]] = None  # 对话数/车控数/缓存命中/延迟


# ============================================================
# 数据中台模型
# ============================================================

class DataPlatformOverview(BaseModel):
    """数据中台全局概览。"""
    total_chats: int = 0
    total_vehicle_cmds: int = 0
    cache_hit_rate: float = 0.0
    avg_latency_ms: float = 0.0
    current_concurrency: int = 0
    peak_concurrency: int = 0
    cockpit_count: int = 0
    alert_count_24h: int = 0


class CockpitComparison(BaseModel):
    """座舱对比数据。"""
    cockpit_id: str
    name: str
    chat_count: int = 0
    vehicle_cmd_count: int = 0
    cache_hit_rate: float = 0.0
    avg_latency_ms: float = 0.0
    health_score: float = 0.0  # 0-100


class AlertRecord(BaseModel):
    """告警记录。"""
    id: int
    cockpit_id: str
    alert_time: str
    alert_type: str
    severity: str
    subagent_judgment: Optional[str] = None
    mainagent_judgment: Optional[str] = None
    action_taken: str


class AgentActivityRecord(BaseModel):
    """Agent 活动记录。"""
    id: int
    cockpit_id: str
    check_time: str
    is_anomaly: bool
    check_items: Optional[str] = None
    llm_judgment: Optional[str] = None


# ============================================================
# 中间件状态模型
# ============================================================

class MiddlewareStatus(BaseModel):
    """中间件状态响应。"""
    name: str
    status: str  # connected / disconnected / not_configured
    version: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


# ============================================================
# 设置中心模型
# ============================================================

class UserCreateRequest(BaseModel):
    """注册新用户请求。"""
    user_id: str = Field(..., description="用户 ID")
    username: str = Field(..., description="用户名")
    password: str = Field(default="", description="密码（Demo 可为空）")
    cockpit_id: str = Field(..., description="绑定的座舱 ID")
    role: str = Field(default="cockpit_user", description="角色")


class UserResponse(BaseModel):
    """用户信息响应。"""
    user_id: str
    username: str
    cockpit_id: str = ""
    role: str = "cockpit_user"
    created_at: str = ""


class MiddlewareConfigUpdate(BaseModel):
    """中间件配置更新请求。"""
    isolation_mode: Optional[str] = None  # strict / shared
    subagent_check_min: Optional[int] = None
    subagent_check_max: Optional[int] = None
    mainagent_confirm_enabled: Optional[bool] = None
    cache_similarity_threshold: Optional[float] = None
    rate_limit_qps: Optional[int] = None


# ============================================================
# RBAC 模型
# ============================================================

class RBACRole(BaseModel):
    """RBAC 角色定义。"""
    name: str
    display_name: str
    permissions: List[str]


# 角色 → 权限映射
ROLE_PERMISSIONS: Dict[str, List[str]] = {
    "super_admin": [
        "cockpit:register", "cockpit:delete", "cockpit:update",
        "cockpit:chat", "cockpit:vehicle",
        "dataplatform:view", "middleware:view",
        "settings:manage", "user:manage",
    ],
    "cockpit_admin": [
        "cockpit:update", "cockpit:chat", "cockpit:vehicle",
        "dataplatform:view:own", "user:manage:own",
    ],
    "cockpit_user": [
        "cockpit:chat", "cockpit:vehicle",
    ],
    "cockpit_viewer": [
        "cockpit:view",
    ],
}


def check_permission(role: str, permission: str, cockpit_id: str = "") -> bool:
    """检查角色是否拥有指定权限。

    Args:
        role: 角色名称
        permission: 权限标识（如 "cockpit:chat"）
        cockpit_id: 座舱 ID（用于 :own 后缀的权限检查）

    Returns:
        是否有权限
    """
    perms = ROLE_PERMISSIONS.get(role, [])
    if permission in perms:
        return True
    # 检查 :own 变体
    if permission.endswith(":own"):
        base_perm = permission[:-4]
        return base_perm in perms or permission in perms
    return False
