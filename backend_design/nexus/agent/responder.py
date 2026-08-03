# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Responder Agent — 上下文压缩器持有者

SupervisorGraph 通过 self.responder.compressor 访问上下文压缩器。
回复生成的实际逻辑已迁移到 nexus.agent.nodes.responder_node.ResponderNode.run() 中。
"""

from __future__ import annotations

from typing import Any

from nexus.agent.llm_client_factory import get_llm_client
from nexus.core.logger import get_logger
from nexus.memory.compressor import ContextCompressor

logger = get_logger(__name__)


class ResponderAgent:
    """响应 Agent — 持有上下文压缩器供 SupervisorGraph 使用。

    Args:
        llm_client: OpenAI 兼容的异步 LLM 客户端 (可选)
        compressor: 上下文压缩器（可选，不传则自动创建）
    """

    def __init__(
        self,
        llm_client: Any = None,
        compressor: ContextCompressor | None = None,
    ):
        self.compressor = compressor or ContextCompressor(
            llm_client if hasattr(llm_client, "chat") else get_llm_client()
        )
