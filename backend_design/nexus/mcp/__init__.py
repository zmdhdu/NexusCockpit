# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
MCP (Model Context Protocol) Server — 标准化协同服务端

提供跨进程、跨服务的标准化协同接口：
  - mcp/task/dispatch: 标准化任务分发到指定 Agent/Skill
  - mcp/state/sync: 多 Agent 间状态同步
  - mcp/result/callback: 异步任务结果回调
  - mcp/exception/report: 异常上报到监控中心
  - mcp/health/heartbeat: 服务心跳保活
"""

from nexus.mcp.server import MCPServer, get_mcp_server

__all__ = ["MCPServer", "get_mcp_server"]
