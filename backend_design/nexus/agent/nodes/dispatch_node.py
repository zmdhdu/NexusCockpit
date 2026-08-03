# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Dispatch Node — 专家并行分派节点

作用：使用 asyncio.gather 并行调用所有活跃专家，合并 partial updates 为最终 update；
场景：Supervisor 分派多个专家并行执行车控/导航/生活等混合意图。
"""

from __future__ import annotations

import asyncio
from typing import Any

from nexus.agent.nodes.context import NodeContext
from nexus.core.logger import get_logger
from nexus.models.state import SupervisorState
from nexus.observability.langfuse import observe

logger = get_logger(__name__)


class DispatchNode:
    """专家并行分派节点：同时执行所有活跃专家。

    通过 NodeContext 依赖注入获取专家字典，不持有 SupervisorGraph 引用。

    Args:
        ctx: NodeContext 共享依赖容器
    """

    def __init__(self, ctx: NodeContext):
        self._ctx = ctx

    @observe(name="expert-dispatch", as_type="agent")
    async def run(self, state: SupervisorState) -> dict[str, Any]:
        """专家并行分派节点：同时执行所有活跃专家。

        使用 asyncio.gather 并行调用所有活跃专家的 run() 方法，
        合并所有 partial updates 为一个最终 update。
        expert_results 通过 reducer 自动累加。
        """
        ctx = self._ctx
        active_experts = state.get("active_experts", [])
        if not active_experts:
            return {}

        # 并行执行所有活跃专家
        tasks = []
        expert_names = []
        for name in active_experts:
            expert = ctx.experts.get(name)
            if expert:
                tasks.append(expert.run(state))
                expert_names.append(name)

        if not tasks:
            return {}

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 合并所有专家的 partial updates
        merged: dict[str, Any] = {"expert_results": []}
        merged_metadata: dict[str, Any] = {}

        for name, result in zip(expert_names, results):
            if isinstance(result, Exception):
                logger.error(f"Expert '{name}' raised: {result}")
                merged["expert_results"].append({
                    "expert": name,
                    "action": "",
                    "reply": "",
                    "handled": False,
                    "error": str(result),
                })
                merged_metadata[f"{name}_error"] = str(result)
            elif isinstance(result, dict):
                # 累加 expert_results
                if "expert_results" in result:
                    merged["expert_results"].extend(result["expert_results"])
                # 合并 skill_action/skill_handled/search_context
                for key in ("skill_action", "skill_handled", "search_context"):
                    val = result.get(key)
                    if val is None:
                        continue
                    if key == "skill_handled":
                        if val:
                            merged[key] = True
                    elif key == "search_context":
                        if val:
                            if merged.get(key):
                                merged[key] = f"{merged[key]}\n---\n{val}"
                            else:
                                merged[key] = val
                    elif key == "skill_action":
                        if val and not merged.get(key):
                            merged[key] = val
                        elif val and merged.get(key) and val != merged[key]:
                            # 多个不同动作 — 记录到 metadata 供调试
                            merged_metadata.setdefault("multi_actions", []).append(val)
                # 传递 has_side_effect 标记（车控指令禁止缓存）
                if result.get("has_side_effect"):
                    merged["has_side_effect"] = True
                # 传递 tool_result 到顶层 state（列表收集避免后者覆盖前者）
                if result.get("tool_result"):
                    if "tool_results" not in merged:
                        merged["tool_results"] = []
                    merged["tool_results"].append(result["tool_result"])
                    # 保留首个 tool_result 作为主结果（向后兼容 B2 分支）
                    if not merged.get("tool_result"):
                        merged["tool_result"] = result["tool_result"]
                # 合并 metadata
                if "metadata" in result:
                    merged_metadata.update(result["metadata"])

        if merged_metadata:
            merged["metadata"] = merged_metadata

        # 确保 skill_handled 有默认值
        merged.setdefault("skill_handled", False)
        merged.setdefault("skill_action", "")
        merged.setdefault("search_context", "")

        # 并行调度日志埋点：记录专家列表、结果数、handled状态
        multi_actions = merged_metadata.get("multi_actions", [])
        expert_summary = ", ".join(
            f"{name}={len(r.get('expert_results', [])) if isinstance(r, dict) else 'err'}"
            for name, r in zip(expert_names, results)
        )
        logger.info(
            f"Dispatch done: {len(active_experts)} experts, "
            f"{len(merged['expert_results'])} results, "
            f"handled={merged.get('skill_handled', False)}, "
            f"multi_actions={len(multi_actions)}, "
            f"experts_detail=[{expert_summary}]"
        )
        return merged
