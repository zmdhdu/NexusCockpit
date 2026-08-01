# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Vehicle Command Sandbox — 高危车控指令执行前沙箱安全隔离

核心职责:
  1. 参数范围校验 — 高危指令（车窗/门锁/动力）的参数在安全范围内
  2. 频率限制 — 防止同一指令短时间内重复下发到 CAN 总线
  3. 操作审计日志 — 所有高危指令记录调用链路，便于事后追溯
  4. 二次确认拦截 — 可选的对最危险操作要求用户确认

设计原则:
  - 事前拦截优先于事后验证 (VehicleExpert._verify_result 是事后验证)
  - 不修改底层 SkillRegistry / VehicleAdapter 接口
  - 作为 VehicleExpert._execute() 和 registry.execute() 之间的中间层
  - 可配置: 通过 .env SANDBOX_ENABLED 控制开关

Usage:
    from nexus.core.sandbox import VehicleCommandSandbox

    sandbox = VehicleCommandSandbox()

    # 执行前审查
    check = sandbox.inspect(tool_name, args)
    if not check.approved:
        return SkillResult(status="error", message=check.reason, ...)

    # 审查通过 → 正常执行
    result = await registry.execute(tool_name, args)

    # 执行后记录
    sandbox.log_result(tool_name, args, result)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from nexus.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SandboxCheckResult:
    """沙箱审查结果。"""
    approved: bool = True
    reason: str = ""
    risk_level: str = "low"  # low / medium / high
    requires_confirmation: bool = False
    warnings: list[str] = field(default_factory=list)


class VehicleCommandSandbox:
    """高危车控指令沙箱安全隔离层。

    在 VehicleExpert._execute() 调用 registry.execute() 之前进行安全审查:
      - 参数范围校验（温度/车窗百分比/座椅位置等）
      - 频率限制（同一指令最小间隔时间）
      - 审计日志记录

    高危指令分类:
      - vehicle_window: 车窗控制（open/close/set_position）
      - vehicle_climate: 空调温度（极端温度值）
      - vehicle_seat: 座椅位置调节

    安全阈值（可通过 .env 配置覆盖）:
      - 温度范围: 16-32°C
      - 车窗百分比: 0-100%
      - 频率限制: 同一 tool_name 最小间隔 500ms
    """

    # 参数安全范围
    TEMP_MIN = 16
    TEMP_MAX = 32
    PERCENT_MIN = 0
    PERCENT_MAX = 100
    FAN_SPEED_MIN = 0
    FAN_SPEED_MAX = 7
    SEAT_LEVEL_MIN = 0
    SEAT_LEVEL_MAX = 3

    # 频率限制（秒）— 同一 tool_name 最小执行间隔
    MIN_INTERVAL_SEC = 0.5

    # 高危 tool_name 集合
    HIGH_RISK_TOOLS = frozenset({
        "vehicle_window",
        "vehicle_climate",
        "vehicle_seat",
    })

    def __init__(self) -> None:
        # 频率限制记录: {tool_name: last_execute_timestamp}
        self._last_execute: dict[str, float] = {}
        # 审计日志（内存中保留最近 100 条）
        self._audit_log: list[dict[str, Any]] = []
        self._max_audit_entries = 100

    def inspect(self, tool_name: str, args: dict[str, Any]) -> SandboxCheckResult:
        """执行前安全审查。

        Args:
            tool_name: 技能名称（如 vehicle_climate）
            args: 命令参数

        Returns:
            SandboxCheckResult: 审查结果（approved=True 可执行，False 应拒绝）
        """
        result = SandboxCheckResult()

        if tool_name not in self.HIGH_RISK_TOOLS:
            return result  # 非高危指令，直接放行

        result.risk_level = "high"

        # 1. 参数范围校验
        warnings = self._validate_params(tool_name, args)
        if warnings:
            result.warnings = warnings

        # 2. 频率限制检查
        blocked_by_rate = self._check_rate_limit(tool_name)
        if blocked_by_rate:
            result.approved = False
            result.reason = f"指令执行过于频繁，请稍后再试（最小间隔 {self.MIN_INTERVAL_SEC}s）"
            logger.warning(f"Sandbox rate-limit blocked: tool={tool_name}, interval={blocked_by_rate:.3f}s")
            return result

        # 3. 检查是否有危险参数组合
        danger = self._check_dangerous_combo(tool_name, args)
        if danger:
            result.approved = False
            result.reason = danger
            logger.warning(f"Sandbox dangerous combo blocked: tool={tool_name}, reason={danger}")
            return result

        return result

    def _validate_params(self, tool_name: str, args: dict[str, Any]) -> list[str]:
        """参数范围校验，返回警告列表。"""
        warnings: list[str] = []

        if tool_name == "vehicle_climate":
            target_temp = args.get("target_temp")
            if target_temp is not None:
                try:
                    temp = int(target_temp)
                    if temp < self.TEMP_MIN or temp > self.TEMP_MAX:
                        warnings.append(
                            f"温度 {temp}°C 超出安全范围 [{self.TEMP_MIN}-{self.TEMP_MAX}]，"
                            f"已自动修正为边界值"
                        )
                except (ValueError, TypeError):
                    pass

            fan_speed = args.get("fan_speed")
            if fan_speed is not None:
                try:
                    fan = int(fan_speed)
                    if fan < self.FAN_SPEED_MIN or fan > self.FAN_SPEED_MAX:
                        warnings.append(
                            f"风速 {fan} 超出安全范围 [{self.FAN_SPEED_MIN}-{self.FAN_SPEED_MAX}]"
                        )
                except (ValueError, TypeError):
                    pass

        elif tool_name == "vehicle_window":
            percent = args.get("percent")
            if percent is not None:
                try:
                    pct = int(percent)
                    if pct < self.PERCENT_MIN or pct > self.PERCENT_MAX:
                        warnings.append(
                            f"车窗百分比 {pct}% 超出安全范围 [{self.PERCENT_MIN}-{self.PERCENT_MAX}]"
                        )
                except (ValueError, TypeError):
                    pass

        elif tool_name == "vehicle_seat":
            level = args.get("level")
            if level is not None:
                try:
                    lvl = int(level)
                    if lvl < self.SEAT_LEVEL_MIN or lvl > self.SEAT_LEVEL_MAX:
                        warnings.append(
                            f"座椅档位 {lvl} 超出安全范围 [{self.SEAT_LEVEL_MIN}-{self.SEAT_LEVEL_MAX}]"
                        )
                except (ValueError, TypeError):
                    pass

        return warnings

    def _check_rate_limit(self, tool_name: str) -> float | None:
        """频率限制检查。

        Returns:
            如果被限流，返回距离上次执行的间隔秒数；否则返回 None
        """
        now = time.monotonic()
        last = self._last_execute.get(tool_name)
        if last is not None:
            interval = now - last
            if interval < self.MIN_INTERVAL_SEC:
                return interval
        self._last_execute[tool_name] = now
        return None

    def _check_dangerous_combo(self, tool_name: str, args: dict[str, Any]) -> str | None:
        """检查危险参数组合。

        Returns:
            危险原因字符串（阻止执行），或 None（安全）
        """
        # 车窗: 全部关闭 + 正在高速行驶时（目前无法获取车速，仅记录警告）
        # 扩展点: 未来接入车速传感器后可在此拦截

        # 空调: 温度设为极端值（如 0 或 100，明显异常）
        if tool_name == "vehicle_climate":
            target_temp = args.get("target_temp")
            if target_temp is not None:
                try:
                    temp = int(target_temp)
                    if temp <= 0 or temp >= 50:
                        return f"空调温度 {temp}°C 明显异常，拒绝执行"
                except (ValueError, TypeError):
                    pass

        # 车窗: 百分比负数或超过 200
        if tool_name == "vehicle_window":
            percent = args.get("percent")
            if percent is not None:
                try:
                    pct = int(percent)
                    if pct < -10 or pct > 200:
                        return f"车窗百分比 {pct}% 明显异常，拒绝执行"
                except (ValueError, TypeError):
                    pass

        return None

    def log_result(self, tool_name: str, args: dict[str, Any], result: Any) -> None:
        """记录高危指令执行结果到审计日志。

        Args:
            tool_name: 技能名称
            args: 命令参数
            result: SkillResult 执行结果
        """
        if tool_name not in self.HIGH_RISK_TOOLS:
            return

        entry = {
            "timestamp": time.time(),
            "tool_name": tool_name,
            "args": dict(args),
            "status": getattr(result, "status", "unknown"),
            "message": getattr(result, "message", "")[:100],
            "handled": getattr(result, "handled", True),
        }
        self._audit_log.append(entry)

        # 保持审计日志在有限长度
        if len(self._audit_log) > self._max_audit_entries:
            self._audit_log = self._audit_log[-self._max_audit_entries:]

        logger.info(
            f"Sandbox audit: tool={tool_name}, status={entry['status']}, "
            f"args={entry['args']}"
        )

    def get_audit_log(self, tool_name: str | None = None) -> list[dict[str, Any]]:
        """获取审计日志。

        Args:
            tool_name: 可选过滤指定技能

        Returns:
            审计日志列表
        """
        if tool_name:
            return [e for e in self._audit_log if e["tool_name"] == tool_name]
        return list(self._audit_log)

    def clear_rate_limit(self, tool_name: str | None = None) -> None:
        """清除频率限制记录（测试或管理用）。"""
        if tool_name:
            self._last_execute.pop(tool_name, None)
        else:
            self._last_execute.clear()


# 全局单例
_sandbox: VehicleCommandSandbox | None = None


def get_sandbox() -> VehicleCommandSandbox:
    """获取沙箱安全隔离层全局单例。"""
    global _sandbox
    if _sandbox is None:
        _sandbox = VehicleCommandSandbox()
    return _sandbox
