# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
MCP Server — Model Context Protocol 服务端实现

提供标准化协同接口，支持跨进程、跨服务的任务分发和状态同步。

核心 API:
  - POST /mcp/task/dispatch: 标准化任务分发到指定 Agent/Skill
  - POST /mcp/state/sync: 多 Agent 间状态同步
  - POST /mcp/result/callback: 异步任务结果回调
  - POST /mcp/exception/report: 异常上报到监控中心
  - GET  /mcp/health/heartbeat: 服务心跳保活

Usage:
    from nexus.mcp.server import get_mcp_server

    mcp = get_mcp_server()
    await mcp.start()  # 在 lifespan 中启动
    # ...
    await mcp.stop()   # 在关闭时停止
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from nexus.core.logger import get_logger

logger = get_logger(__name__)


class MCPServer:
    """MCP 协同服务端。

    提供任务分发、状态同步、结果回调、异常上报、心跳保活五类标准接口。
    可作为 FastAPI 子路由挂载，或独立运行。

    Attributes:
        _tasks: 待处理的任务队列
        _results: 已完成的任务结果
        _agents: 注册的 Agent 列表
        _heartbeat: 心跳时间戳
    """

    def __init__(self) -> None:
        self._tasks: dict[str, dict[str, Any]] = {}
        self._results: dict[str, dict[str, Any]] = {}
        self._agents: dict[str, dict[str, Any]] = {}
        self._heartbeat: float = time.time()
        self._running = False

    async def start(self) -> None:
        """启动 MCP 服务端。"""
        self._running = True
        self._heartbeat = time.time()
        logger.info("MCP Server started")

    async def stop(self) -> None:
        """停止 MCP 服务端。"""
        self._running = False
        logger.info("MCP Server stopped")

    @property
    def is_running(self) -> bool:
        """服务是否运行中。"""
        return self._running

    # ============================================================
    # API: 任务分发
    # ============================================================

    async def dispatch_task(
        self,
        task_id: str,
        agent_name: str,
        skill_name: str,
        arguments: dict[str, Any],
        cockpit_id: str = "",
    ) -> dict[str, Any]:
        """标准化任务分发到指定 Agent/Skill。

        Args:
            task_id: 任务唯一 ID
            agent_name: 目标专家名称 (vehicle/navigation/lifestyle/health/chat)
            skill_name: 技能名称
            arguments: 技能参数
            cockpit_id: 座舱 ID

        Returns:
            分发结果，包含 task_id 和状态
        """
        task = {
            "task_id": task_id,
            "agent_name": agent_name,
            "skill_name": skill_name,
            "arguments": arguments,
            "cockpit_id": cockpit_id,
            "status": "dispatched",
            "created_at": time.time(),
        }
        self._tasks[task_id] = task
        logger.info(
            f"MCP dispatch: task={task_id}, agent={agent_name}, skill={skill_name}"
        )
        return {"task_id": task_id, "status": "dispatched", "message": "任务已分发"}

    # ============================================================
    # API: 状态同步
    # ============================================================

    async def sync_state(
        self,
        agent_name: str,
        state: dict[str, Any],
        cockpit_id: str = "",
    ) -> dict[str, Any]:
        """多 Agent 间状态同步。

        Args:
            agent_name: Agent 名称
            state: 要同步的状态数据
            cockpit_id: 座舱 ID

        Returns:
            同步结果
        """
        key = f"{cockpit_id}:{agent_name}" if cockpit_id else agent_name
        self._agents[key] = {
            "agent_name": agent_name,
            "state": state,
            "cockpit_id": cockpit_id,
            "synced_at": time.time(),
        }
        logger.info(f"MCP state sync: agent={agent_name}, cockpit={cockpit_id}")
        return {"status": "synced", "agent": agent_name}

    # ============================================================
    # API: 结果回调
    # ============================================================

    async def result_callback(
        self,
        task_id: str,
        result: dict[str, Any],
        status: str = "ok",
    ) -> dict[str, Any]:
        """异步任务结果回调。

        Args:
            task_id: 任务 ID
            result: 执行结果
            status: 执行状态 (ok/error)

        Returns:
            回调确认
        """
        self._results[task_id] = {
            "task_id": task_id,
            "result": result,
            "status": status,
            "callback_at": time.time(),
        }
        # 从任务队列移除已完成任务
        if task_id in self._tasks:
            self._tasks[task_id]["status"] = status
        logger.info(f"MCP result callback: task={task_id}, status={status}")
        return {"task_id": task_id, "acknowledged": True}

    # ============================================================
    # API: 异常上报
    # ============================================================

    async def report_exception(
        self,
        agent_name: str,
        exception: str,
        context: dict[str, Any] | None = None,
        cockpit_id: str = "",
    ) -> dict[str, Any]:
        """异常上报到监控中心。

        Args:
            agent_name: 发生异常的 Agent
            exception: 异常描述
            context: 异常上下文
            cockpit_id: 座舱 ID

        Returns:
            上报确认
        """
        logger.error(
            f"MCP exception report: agent={agent_name}, "
            f"exception={exception}, cockpit={cockpit_id}"
        )
        return {
            "acknowledged": True,
            "agent": agent_name,
            "message": "异常已记录",
        }

    # ============================================================
    # API: 心跳保活
    # ============================================================

    async def heartbeat(self) -> dict[str, Any]:
        """服务心跳保活。

        Returns:
            心跳响应，包含服务状态和时间戳
        """
        self._heartbeat = time.time()
        return {
            "status": "alive",
            "timestamp": self._heartbeat,
            "running": self._running,
            "active_tasks": len(self._tasks),
            "active_agents": len(self._agents),
        }

    # ============================================================
    # 查询接口
    # ============================================================

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        """获取任务状态。"""
        return self._tasks.get(task_id)

    def get_result(self, task_id: str) -> dict[str, Any] | None:
        """获取任务结果。"""
        return self._results.get(task_id)

    def list_active_tasks(self) -> list[dict[str, Any]]:
        """列出所有活跃任务。"""
        return list(self._tasks.values())

    def list_registered_agents(self) -> list[dict[str, Any]]:
        """列出所有注册的 Agent。"""
        return list(self._agents.values())


# 全局单例
_mcp_server: MCPServer | None = None


def get_mcp_server() -> MCPServer:
    """获取 MCP 服务端全局单例。"""
    global _mcp_server
    if _mcp_server is None:
        _mcp_server = MCPServer()
    return _mcp_server
