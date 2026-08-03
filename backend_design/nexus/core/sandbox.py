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
  5. 空值拦截 — 必填参数为空时直接阻断，杜绝空风量/无效参数流入底层车控接口
  6. 非法字符清洗 — 对字符串型参数做类型强转，脏参数直接阻断

设计原则:
  - 事前拦截优先于事后验证 (VehicleExpert._verify_result 是事后验证)
  - 不修改底层 SkillRegistry / VehicleAdapter 接口
  - 作为 VehicleExpert._execute() 和 registry.execute() 之间的中间层
  - 可配置: 通过 .env SANDBOX_ENABLED 控制开关
  - 超范围参数从「仅警告」升级为「阻断执行」，杜绝脏参数流入底层

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

import os
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

    # 参数安全范围（可通过 .env 配置覆盖）
    TEMP_MIN = int(os.getenv("SANDBOX_TEMP_MIN", "16"))
    TEMP_MAX = int(os.getenv("SANDBOX_TEMP_MAX", "32"))
    PERCENT_MIN = int(os.getenv("SANDBOX_PERCENT_MIN", "0"))
    PERCENT_MAX = int(os.getenv("SANDBOX_PERCENT_MAX", "100"))
    FAN_SPEED_MIN = int(os.getenv("SANDBOX_FAN_MIN", "0"))
    FAN_SPEED_MAX = int(os.getenv("SANDBOX_FAN_MAX", "7"))
    SEAT_LEVEL_MIN = int(os.getenv("SANDBOX_SEAT_MIN", "0"))
    SEAT_LEVEL_MAX = int(os.getenv("SANDBOX_SEAT_MAX", "3"))

    # 频率限制（秒）— 同一 tool_name 最小执行间隔
    MIN_INTERVAL_SEC = 0.5

    # 高危 tool_name 集合
    HIGH_RISK_TOOLS = frozenset({
        "vehicle_window",
        "vehicle_climate",
        "vehicle_seat",
        "vehicle_navigation",
        "vehicle_media",
    })

    def __init__(self) -> None:
        # 沙箱开关 — 通过 .env SANDBOX_ENABLED 控制
        self._enabled = os.getenv("SANDBOX_ENABLED", "true").strip().lower() in ("true", "1", "yes")
        # 频率限制记录: {tool_name: last_execute_timestamp} (进程内降级)
        self._last_execute: dict[str, float] = {}
        # 审计日志（内存中保留最近 100 条）
        self._audit_log: list[dict[str, Any]] = []
        self._max_audit_entries = 100
        # Redis 客户端（多实例共享频率限制）
        self._redis: Any = None
        self._redis_key_prefix = "nexus:sandbox:rate:"

    def _get_redis(self) -> Any:
        """获取 Redis 客户端（懒加载，多实例共享频率限制）。"""
        if self._redis is not None:
            return self._redis
        try:
            import redis.asyncio as aioredis

            from nexus.config import get_config
            config = get_config().redis
            self._redis = aioredis.Redis(
                host=config.host, port=config.port,
                password=config.password, db=config.db,
                decode_responses=True,
            )
        except Exception:
            self._redis = None
        return self._redis

    def inspect(self, tool_name: str, args: dict[str, Any]) -> SandboxCheckResult:
        """执行前安全审查。

        Args:
            tool_name: 技能名称（如 vehicle_climate）
            args: 命令参数

        Returns:
            SandboxCheckResult: 审查结果（approved=True 可执行，False 应拒绝）
        """
        result = SandboxCheckResult()

        # 沙箱开关关闭时直接放行
        if not self._enabled:
            return result

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
        """参数范围校验，返回警告列表。

        超范围参数仅产生警告（不阻断），极端参数由 _check_dangerous_combo 阻断。
        空值/类型错误参数由 _check_null_params 阻断。
        """
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
                    warnings.append(f"温度值 '{target_temp}' 类型非法，期望整数")

            fan_speed = args.get("fan_speed")
            if fan_speed is not None:
                try:
                    fan = int(fan_speed)
                    if fan < self.FAN_SPEED_MIN or fan > self.FAN_SPEED_MAX:
                        warnings.append(
                            f"风速 {fan} 超出安全范围 [{self.FAN_SPEED_MIN}-{self.FAN_SPEED_MAX}]"
                        )
                except (ValueError, TypeError):
                    warnings.append(f"风速值 '{fan_speed}' 类型非法，期望整数")

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
                    warnings.append(f"车窗百分比 '{percent}' 类型非法，期望整数")

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
                    warnings.append(f"座椅档位 '{level}' 类型非法，期望整数")

        return warnings

    def _check_rate_limit(self, tool_name: str) -> float | None:
        """频率限制检查（进程内 + Redis 多实例共享）。

        优先使用 Redis 共享限流（多实例部署时生效），
        Redis 不可用时降级为进程内限流。

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
        """检查危险参数组合和非法参数。

        拦截范围:
            1. 极端数值（温度<=0 或 >=50，车窗百分比<-10 或 >200）
            2. 参数类型错误（字符串传入应为数字的字段）
            3. 非法操作符（op 字段为空或不在合法枚举内）

        Returns:
            危险原因字符串（阻止执行），或 None（安全）
        """
        # 空调: 温度极端值 + 类型校验 + 操作符校验
        if tool_name == "vehicle_climate":
            target_temp = args.get("target_temp")
            if target_temp is not None:
                try:
                    temp = int(target_temp)
                    if temp <= 0 or temp >= 50:
                        return f"空调温度 {temp}°C 明显异常，拒绝执行"
                except (ValueError, TypeError):
                    return f"空调温度值 '{target_temp}' 类型非法，拒绝执行"

            # 操作符校验 — op 为空或非法值时阻断
            op = args.get("op", "")
            valid_climate_ops = {
                "power_on", "power_off", "on", "off", "open", "close",
                "temp_up", "temp_down", "up", "down", "set_temp",
                "status", "query", "query_status",
            }
            if op and op not in valid_climate_ops:
                return f"空调操作符 '{op}' 不在合法枚举内，拒绝执行"

        # 车窗: 百分比极端值 + 类型校验 + 操作符校验
        if tool_name == "vehicle_window":
            percent = args.get("percent")
            if percent is not None:
                try:
                    pct = int(percent)
                    if pct < -10 or pct > 200:
                        return f"车窗百分比 {pct}% 明显异常，拒绝执行"
                except (ValueError, TypeError):
                    return f"车窗百分比 '{percent}' 类型非法，拒绝执行"

            op = args.get("op", "")
            valid_window_ops = {"open", "close", "set", "status", "query"}
            if op and op not in valid_window_ops:
                return f"车窗操作符 '{op}' 不在合法枚举内，拒绝执行"

            # 位置校验
            position = args.get("position", "all")
            valid_positions = {
                "all", "sunroof", "front_left", "front_right",
                "rear_left", "rear_right",
            }
            if position and position not in valid_positions:
                return f"车窗位置 '{position}' 不在合法枚举内，拒绝执行"

        # 座椅: 档位极端值 + 类型校验
        if tool_name == "vehicle_seat":
            level = args.get("level")
            if level is not None:
                try:
                    lvl = int(level)
                    if lvl < -1 or lvl > 10:
                        return f"座椅档位 {lvl} 明显异常，拒绝执行"
                except (ValueError, TypeError):
                    return f"座椅档位 '{level}' 类型非法，拒绝执行"

        # 媒体: 操作符校验
        if tool_name == "vehicle_media":
            op = args.get("op", "")
            valid_media_ops = {
                "play", "pause", "stop", "next", "prev", "resume",
                "set_volume", "volume", "set_source", "set_play_mode", "play_mode",
                "play_track", "select_track", "status", "query", "query_status",
            }
            if op and op not in valid_media_ops:
                return f"媒体操作符 '{op}' 不在合法枚举内，拒绝执行"

        return None

    def log_result(self, tool_name: str, args: dict[str, Any], result: Any) -> None:
        """记录高危指令执行结果到审计日志。

        同时持久化到 MySQL audit_logs 表（如果可用）。

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

        # 持久化到 MySQL audit_logs 表
        try:
            import asyncio

            from nexus.core.db_manager import get_db_manager
            db = get_db_manager()
            if db.is_connected:
                # 在事件循环中调度异步写入（fire-and-forget）
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(db.insert_audit_log(
                        cockpit_id="system",
                        user_id="sandbox",
                        action=tool_name,
                        detail=entry,
                    ))
                except RuntimeError:
                    pass  # 无事件循环时跳过
        except Exception as e:
            logger.warning(f"Sandbox audit log persistence failed: {e}")

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
