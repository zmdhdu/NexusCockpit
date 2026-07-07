"""
API Schemas — Pydantic 请求/响应模型

本文件定义了所有 API 接口的请求和响应数据结构。
FastAPI 会根据这些模型自动生成 OpenAPI/Swagger 文档。
"""

from __future__ import annotations

from dataclasses import field
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """文本对话请求"""
    text: str = Field(..., description="用户输入文本", min_length=1, max_length=500)
    user_id: str = Field(default="default", description="用户 ID")
    session_id: str = Field(default="", description="会话 ID")
    stream: bool = Field(default=False, description="是否流式返回")


class ChatResponse(BaseModel):
    """文本对话响应"""
    response: str = Field(..., description="回复文本")
    user_id: str = Field(default="")
    session_id: str = Field(default="")
    latency_ms: float = Field(default=0.0, description="总延迟(毫秒)")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    cache_hit: bool = Field(default=False)


class VoiceRequest(BaseModel):
    """语音请求"""
    user_id: str = Field(default="default")
    session_id: str = Field(default="")
    audio_format: str = Field(default="wav", description="音频格式: wav, pcm")


class VoiceResponse(BaseModel):
    """语音响应"""
    text: str = Field(..., description="识别出的文本")
    response: str = Field(..., description="回复文本")
    user_id: str = Field(default="")
    latency_ms: float = Field(default=0.0)


class VehicleCommandRequest(BaseModel):
    """车控命令请求"""
    command: str = Field(..., description="命令名称")
    arguments: Dict[str, Any] = Field(default_factory=dict)
    user_id: str = Field(default="default")


class VehicleCommandResponse(BaseModel):
    """车控命令响应"""
    success: bool
    message: str
    data: Dict[str, Any] = Field(default_factory=dict)
    error: str = Field(default="")


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str = Field(default="healthy")
    version: str = Field(default="1.0.0")
    components: Dict[str, str] = Field(default_factory=dict)


class SkillListResponse(BaseModel):
    """技能列表响应"""
    skills: List[Dict[str, Any]] = Field(default_factory=list)
    count: int = Field(default=0)


class MemoryResponse(BaseModel):
    """记忆查询响应"""
    user_id: str
    memories: List[str] = Field(default_factory=list)
    profile: Dict[str, Any] = Field(default_factory=dict)
