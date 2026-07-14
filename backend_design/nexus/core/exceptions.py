# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
NexusCockpit 自定义异常体系

本模块定义了项目所有自定义异常的基类和子类。
设计思路:
  1. 所有异常都继承自 NexusError，便于全局统一捕获
  2. 每个异常都有 error_code (如 "LLM_ERROR")，前端可根据 code 做不同处理
  3. 异常携带 details 字典，提供额外上下文信息

异常处理流程:
    异常抛出 → FastAPI 全局异常处理器 → 返回 JSON {error, message, details}
"""


class NexusError(Exception):
    """所有 NexusCockpit 异常的基类。

    Attributes:
        message: 人类可读的错误描述
        code: 错误码 (如 "NEXUS_ERROR")，用于程序判断
        details: 额外详情字典，可包含调试信息
    """

    def __init__(self, message: str = "", code: str = "NEXUS_ERROR", details: dict | None = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(message)


class ConfigError(NexusError):
    """配置错误 — .env 文件缺失或格式不正确时抛出。"""

    def __init__(self, message: str = "Configuration error"):
        super().__init__(message, code="CONFIG_ERROR")


class LLMError(NexusError):
    """LLM 推理错误 — 调用大模型 API 失败时抛出。"""

    def __init__(self, message: str = "LLM inference error", details: dict | None = None):
        super().__init__(message, code="LLM_ERROR", details=details)


class RAGError(NexusError):
    """RAG 检索错误 — 向量检索或图谱查询失败时抛出。"""

    def __init__(self, message: str = "RAG retrieval error", details: dict | None = None):
        super().__init__(message, code="RAG_ERROR", details=details)


class VectorStoreError(NexusError):
    """向量存储错误 — Milvus 操作失败时抛出。"""

    def __init__(self, message: str = "Vector store error", details: dict | None = None):
        super().__init__(message, code="VECTOR_STORE_ERROR", details=details)


class GraphStoreError(NexusError):
    """图谱存储错误 — Neo4j 操作失败时抛出。"""

    def __init__(self, message: str = "Graph store error", details: dict | None = None):
        super().__init__(message, code="GRAPH_STORE_ERROR", details=details)


class MemoryError(NexusError):
    """记忆操作错误 — 记忆存储/检索/冲突检测失败时抛出。"""

    def __init__(self, message: str = "Memory operation error", details: dict | None = None):
        super().__init__(message, code="MEMORY_ERROR", details=details)


class SkillError(NexusError):
    """技能执行错误 — 技能调用过程中出现异常时抛出。"""

    def __init__(self, message: str = "Skill execution error", details: dict | None = None):
        super().__init__(message, code="SKILL_ERROR", details=details)


class IntentError(NexusError):
    """意图路由错误 — 无法识别用户意图时抛出。"""

    def __init__(self, message: str = "Intent routing error", details: dict | None = None):
        super().__init__(message, code="INTENT_ERROR", details=details)


class VehicleError(NexusError):
    """车控错误 — 车控指令发送失败时抛出。"""

    def __init__(self, message: str = "Vehicle control error", details: dict | None = None):
        super().__init__(message, code="VEHICLE_ERROR", details=details)


class CacheError(NexusError):
    """缓存错误 — Redis 读写失败时抛出。"""

    def __init__(self, message: str = "Cache operation error"):
        super().__init__(message, code="CACHE_ERROR")


class AuthError(NexusError):
    """认证错误 — JWT Token 无效或过期时抛出。"""

    def __init__(self, message: str = "Authentication error"):
        super().__init__(message, code="AUTH_ERROR")


class RateLimitError(NexusError):
    """限流错误 — 请求频率超过限制时抛出。"""

    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(message, code="RATE_LIMIT_ERROR")


class CircuitBreakerError(NexusError):
    """熔断器错误 — 熔断器处于开启状态时抛出。"""

    def __init__(self, message: str = "Circuit breaker is open"):
        super().__init__(message, code="CIRCUIT_BREAKER_OPEN")
