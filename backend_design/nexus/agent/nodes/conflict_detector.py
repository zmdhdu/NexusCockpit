# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Conflict Detector — 多 Agent 并行冲突检测器

在 DispatchNode 并行执行专家后，检测多个专家是否同时修改了冲突的车辆状态。

冲突场景:
    - VehicleExpert 调空调 + NavExpert 调导航 → 无冲突（不同子系统）
    - VehicleExpert 开车窗 + VehicleExpert 开空调 → 无冲突（不同部件）
    - 两个专家同时设置温度 → 冲突（同一参数被多次修改）

使用方式:
    from nexus.agent.nodes.conflict_detector import ConflictDetector

    detector = ConflictDetector()
    conflicts = detector.detect(expert_results)
    if conflicts:
        # 处理冲突
        pass
"""

from __future__ import annotations

from typing import Any

from nexus.core.logger import get_logger

logger = get_logger(__name__)


class ConflictDetector:
    """多 Agent 并行冲突检测器。

    检测多个专家执行结果中的车辆状态修改冲突。

    冲突规则:
        - 同一 tool_name 被多个专家调用 → 潜在冲突
        - 同一参数（如 target_temp）被设置不同值 → 确认冲突
    """

    # 车控类 tool_name → 冲突维度映射
    # 同一维度的修改如果值不同则冲突
    _CONFLICT_DIMENSIONS = {
        "vehicle_climate": "climate",
        "vehicle_window": "window",
        "vehicle_seat": "seat",
        "vehicle_navigation": "navigation",
        "vehicle_media": "media",
    }

    def detect(self, expert_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """检测多个专家结果中的冲突。

        Args:
            expert_results: 专家执行结果列表

        Returns:
            冲突列表，每个冲突包含 conflicting_experts、tool_name、reason
        """
        conflicts: list[dict[str, Any]] = []

        # 收集所有车控类 tool_name 的调用记录
        tool_calls: dict[str, list[str]] = {}  # dimension → [expert_name, ...]

        for result in expert_results:
            expert_name = result.get("expert", "")
            action = result.get("action", "")
            if action in self._CONFLICT_DIMENSIONS:
                dim = self._CONFLICT_DIMENSIONS[action]
                if dim not in tool_calls:
                    tool_calls[dim] = []
                tool_calls[dim].append(expert_name)

        # 检测冲突：同一维度被多个专家调用
        for dim, experts in tool_calls.items():
            if len(experts) > 1:
                conflict = {
                    "dimension": dim,
                    "conflicting_experts": experts,
                    "reason": f"多个专家同时修改 {dim} 子系统: {', '.join(experts)}",
                }
                conflicts.append(conflict)
                logger.warning(f"Conflict detected: {conflict}")

        return conflicts

    def resolve(self, conflicts: list[dict[str, Any]], expert_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """解决冲突：保留第一个专家的结果，丢弃后续冲突结果。

        Args:
            conflicts: 检测到的冲突列表
            expert_results: 专家执行结果列表

        Returns:
            解决冲突后的专家结果列表
        """
        if not conflicts:
            return expert_results

        # 收集需要丢弃的专家+维度组合
        discard_set: set[tuple[str, str]] = set()
        for conflict in conflicts:
            dim = conflict["dimension"]
            experts = conflict["conflicting_experts"]
            # 保留第一个专家，丢弃后续
            for expert in experts[1:]:
                discard_set.add((expert, dim))

        # 过滤结果
        filtered = []
        for result in expert_results:
            expert_name = result.get("expert", "")
            action = result.get("action", "")
            dim = self._CONFLICT_DIMENSIONS.get(action, "")
            if (expert_name, dim) in discard_set:
                logger.info(f"Conflict resolved: discarded {expert_name}'s {action} result")
                continue
            filtered.append(result)

        return filtered


# 全局单例
_detector: ConflictDetector | None = None


def get_conflict_detector() -> ConflictDetector:
    """获取冲突检测器全局单例。"""
    global _detector
    if _detector is None:
        _detector = ConflictDetector()
    return _detector
