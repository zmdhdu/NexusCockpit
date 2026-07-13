# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""Memory module — 统一记忆管理 v2.1。

架构:
    短期记忆 (Redis SessionStore) → 原始对话历史，即时上下文
    长期记忆 (Milvus + Neo4j)     → 语义向量召回 + 关系图谱
    习惯记忆 (MySQL user_habits)  → 用户偏好统计，频次加权
    检索管道: 三路召回 → RRF 融合 → Rerank 重排 → 渐进式披露

Modules:
    manager:    MemoryManager — 统一记忆管理器
    compressor: ContextCompressor — 上下文动态压缩引擎
    conflict:   ConflictDetector — 记忆冲突检测与一致性维护
"""

from nexus.memory.compressor import ContextCompressor
from nexus.memory.conflict import ConflictDetector, MemoryExtractor
from nexus.memory.manager import MemoryManager

__all__ = ["MemoryManager", "ContextCompressor", "ConflictDetector", "MemoryExtractor"]
