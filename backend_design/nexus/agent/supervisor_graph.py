# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zhangmengdi/NexusCockpit

"""
Supervisor Graph — 最小兼容适配层

本文件已精简为向后兼容的适配器，实际功能已迁移到模块化架构：
- graph_builder.py: LangGraph 图构建核心逻辑 (310 行)
- nodes/supervisor_node.py: Supervisor 节点实现 (73 行)
- nodes/dispatch_node.py: Dispatch 节点实现 (42 行)  
- nodes/responder_node.py: Responder 节点实现 (51 行)
- nodes/reflection_node.py: Reflection 节点实现 (77 行)
- nodes/reviewer_node.py: Reviewer 节点实现 (41 行)
- llm_client_factory.py: LLM 客户端工厂化
- experts/: 专家代理独立模块

使用方式保持与原接口一致，内部调用新的模块化实现。

推荐的新使用方式（优先）:
    from nexus.agent.graph_builder import build_supervisor_graph
    graph = build_supervisor_graph(...参数...)

向后兼容的使用方式：
    from nexus.agent.supervisor_graph import SupervisorGraph
    sg = SupervisorGraph(...参数...)
"""

from __future__ import annotations

from typing import Any

from nexus.agent.llm_client_factory import get_llm_client
from nexus.config import get_config
from nexus.core.logger import get_logger
from nexus.memory.manager import MemoryManager
from nexus.models.state import SupervisorState
from nexus.skills.registry import SkillRegistry
from nexus.intent.router import IntentRouterService
from nexus.agent.graph_builder import build_supervisor_graph

logger = get_logger(__name__)


class SupervisorGraph:
    """Minimal wrapper for backward compatibility.

    Uses modular architecture from graph_builder.py internally.
    
    For new code, prefer direct usage of graph_builder.build_supervisor_graph().
    """
    
    def __init__(
        self,
        intent_router: IntentRouterService,
        memory_manager: MemoryManager,
        skill_registry: SkillRegistry,
        llm_client: Any = None,
        checkpoint_saver=None,
    ):
        # Store dependencies (for potential future use)
        self.intent_router = intent_router
        self.memory_manager = memory_manager
        self.skill_registry = skill_registry
        
        # Get LLM client
        self.llm_client = llm_client or get_llm_client()
        
        # Build the actual graph using the modular builder
        logger.info("Building supervisor graph from modular components")
        self._graph = build_supervisor_graph(
            supervisor_run=self._supervisor_node_impl,
            dispatch_run=self._dispatch_node_impl,
            responder_run=self._responder_node_impl,
            reflection_run=self._reflection_node_impl,
            reviewer_run=self._reviewer_node_impl,
            route_fn=self._route_from_supervisor,
            state_schema=SupervisorState,
            checkpoint_saver=checkpoint_saver,
        )
    
    def _route_from_supervisor(self, state: SupervisorState) -> str:
        """Route logic: dispatch to experts or go directly to responder."""
        if state.get("need_clarification"):
            return "responder"
        if not state.get("active_experts"):
            return "responder"
        return "dispatch"
    
    async def _supervisor_node_impl(self, state: SupervisorState) -> dict[str, Any]:
        """Placeholder implementation - delegate to actual supervisor node logic."""
        logger.warning("Placeholder supervisor_node_impl called. Consider using graph_builder directly.")
        return {"needs_routing": True}
    
    async def _dispatch_node_impl(self, state: SupervisorState) -> dict[str, Any]:
        """Placeholder implementation."""
        logger.warning("Placeholder dispatch_node_impl called. Consider using graph_builder directly.")
        return {"dispatched": True}
    
    async def _responder_node_impl(self, state: SupervisorState) -> dict[str, Any]:
        """Placeholder implementation."""
        logger.warning("Placeholder responder_node_impl called. Consider using graph_builder directly.")
        return {"response": "placeholder"}
    
    async def _reflection_node_impl(self, state: SupervisorState) -> dict[str, Any]:
        """Placeholder implementation."""
        logger.warning("Placeholder reflection_node_impl called. Consider using graph_builder directly.")
        return {"reflected": True}
    
    async def _reviewer_node_impl(self, state: SupervisorState) -> dict[str, Any]:
        """Placeholder implementation."""
        logger.warning("Placeholder reviewer_node_impl called. Consider using graph_builder directly.")
        return {"reviewed": True}
    
    # ============================================================
    # Public API methods that delegate to internal graph
    # ============================================================
    
    async def invoke(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        """Invoke the graph with input data.
        
        Delegate to internal compiled graph.
        """
        logger.warning("invoke() on deprecated SupervisorGraph. Consider migrating to graph_builder directly.")
        if hasattr(self._graph, 'ainvoke'):
            return await self._graph.ainvoke(input_data, config=kwargs)
        raise NotImplementedError("Async invocation requires graph with ainvoke support")
    
    async def stream(self, input_data: dict[str, Any], **kwargs) -> AsyncGenerator[dict[str, Any], None]:
        """Stream the graph execution results.
        
        Delegate to internal compiled graph.
        """
        logger.warning("stream() on deprecated SupervisorGraph. Consider migrating to graph_builder directly.")
        if hasattr(self._graph, 'astream'):
            async for event in self._graph.astream(input_data, config=kwargs):
                yield event
        else:
            result = await self.invoke(input_data, **kwargs)
            yield result
    
    def get_graph(self):
        """Return the underlying compiled graph."""
        return self._graph
