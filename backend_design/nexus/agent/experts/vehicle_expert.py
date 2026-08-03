# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Vehicle Expert — 车控专家 Agent

作用：封装车控类技能（空调/车窗/座椅/媒体/状态查询），支持多动作并行执行与互斥检测；
场景：用户单条指令含多个车控需求时，遍历全部 intent 字段并行执行，互斥动作串行避免冲突。
"""

from __future__ import annotations

import asyncio
from typing import Any

from nexus.agent.experts.base import BaseExpertAgent
from nexus.core.logger import get_logger
from nexus.core.sandbox import get_sandbox
from nexus.models.state import SupervisorState
from nexus.skills.base import SkillGroup, SkillResult

logger = get_logger(__name__)

# intent 字段 → 技能名映射（按优先级排序）
_VEHICLE_ACTION_MAP = {
    "Climate_Action": "vehicle_climate",
    "Window_Action": "vehicle_window",
    "Seat_Action": "vehicle_seat",
    "Media_Action": "vehicle_media",
    "Vehicle_Status_Action": "vehicle_status",
}

# 硬件互斥组 — 同一组内的指令必须串行执行
_MUTEX_GROUPS: dict[str, list[str]] = {
    "climate": ["vehicle_climate"],
    "window": ["vehicle_window"],
    "seat": ["vehicle_seat"],
    "media": ["vehicle_media"],
}


class VehicleExpert(BaseExpertAgent):
    """车控专家：作用：处理空调/车窗/座椅/媒体/状态查询，多动作并行执行，互斥组内串行避免冲突；场景：用户单条指令含多个车控需求。"""

    expert_name = "vehicle"
    group = SkillGroup.VEHICLE

    async def _execute(self, state: SupervisorState) -> dict[str, Any]:
        """执行车控指令：作用：收集匹配动作→沙箱审查→并行/串行执行→聚合回复；场景：多动作并行与互斥检测。"""
        intent = state.get("intent", {})

        # 1. 收集所有匹配的车控动作
        pending_actions: list[dict[str, Any]] = []
        for intent_key, tool_name in _VEHICLE_ACTION_MAP.items():
            action_data = intent.get(intent_key) or {}
            if not action_data:
                continue
            # 过滤 None 值
            cleaned = {k: v for k, v in action_data.items() if v is not None}
            if not cleaned:
                continue
            pending_actions.append({
                "intent_key": intent_key,
                "tool_name": tool_name,
                "args": cleaned,
            })

        if not pending_actions:
            return self._build_expert_result(
                action="",
                reply="",
                handled=False,
            )

        # 2. 沙箱安全审查（逐个检查，被拦截的直接标记为失败）
        approved_actions: list[dict[str, Any]] = []
        blocked_results: list[dict[str, Any]] = []
        sandbox = get_sandbox()

        for action in pending_actions:
            tool_name = action["tool_name"]
            args = action["args"]
            check = sandbox.inspect(tool_name, args)
            if not check.approved:
                logger.warning(
                    f"Sandbox blocked vehicle command: tool={tool_name}, "
                    f"reason={check.reason}"
                )
                blocked_results.append({
                    "tool_name": tool_name,
                    "args": args,
                    "result": SkillResult(
                        status="error",
                        message=check.reason,
                        error="sandbox_blocked",
                        action=tool_name,
                        handled=True,
                    ),
                })
            else:
                action["check"] = check
                approved_actions.append(action)

        # 3. 执行审批通过的动作
        if approved_actions:
            executed_results = await self._execute_actions_parallel(approved_actions)
        else:
            executed_results = []

        # 4. 合并所有结果（被拦截 + 已执行）
        all_results = blocked_results + executed_results

        # 5. 聚合为统一回复
        return self._aggregate_results(all_results)

    async def _execute_actions_parallel(
        self, actions: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """并行执行多个车控动作。

        无冲突的动作通过 asyncio.gather 并行执行。
        同一互斥组内的动作串行执行（按出现顺序）。
        """
        # 按互斥组分组
        independent: list[dict[str, Any]] = []
        mutex_queues: dict[str, list[dict[str, Any]]] = {}

        for action in actions:
            tool_name = action["tool_name"]
            # 查找所属互斥组
            mutex_group = None
            for group_name, group_tools in _MUTEX_GROUPS.items():
                if tool_name in group_tools:
                    mutex_group = group_name
                    break
            if mutex_group:
                mutex_queues.setdefault(mutex_group, []).append(action)
            else:
                independent.append(action)

        # 构建并行任务列表
        parallel_tasks: list[Any] = []

        # 独立动作直接并行
        for action in independent:
            parallel_tasks.append(self._execute_single(action))

        # 互斥组内串行执行，组间并行
        for group_name, queue in mutex_queues.items():
            parallel_tasks.append(self._execute_serial(queue))

        # 并行等待所有任务完成
        results_nested = await asyncio.gather(*parallel_tasks, return_exceptions=True)

        # 展平结果列表
        all_results: list[dict[str, Any]] = []
        for r in results_nested:
            if isinstance(r, Exception):
                logger.error(f"Vehicle action execution failed: {r}")
                all_results.append({
                    "tool_name": "unknown",
                    "args": {},
                    "result": SkillResult(
                        status="error",
                        message=f"执行异常: {r}",
                        error=str(r),
                        action="unknown",
                        handled=False,
                    ),
                })
            elif isinstance(r, list):
                all_results.extend(r)
            else:
                all_results.append(r)

        return all_results

    async def _execute_single(self, action: dict[str, Any]) -> dict[str, Any]:
        """执行单个车控动作：作用：沙箱审查→执行→审计日志→结果验证，异常统一捕获返回标准化提示；场景：车控动作执行。"""
        tool_name = action["tool_name"]
        args = action["args"]
        check = action.get("check")

        try:
            # 沙箱审查已通过 → 正常执行技能
            result = await asyncio.wait_for(
                self.registry.execute(tool_name, args),
                timeout=10.0,
            )
        except asyncio.TimeoutError:
            logger.error(f"Vehicle command timeout: tool={tool_name}, args={args}")
            result = SkillResult(
                status="error",
                message=f"车控指令执行超时，设备可能离线，请稍后重试。",
                error="timeout",
                action=tool_name,
                handled=True,
            )
        except Exception as e:
            logger.error(f"Vehicle command execution error: tool={tool_name}, error={e}")
            result = SkillResult(
                status="error",
                message=f"车控指令执行异常: {e}",
                error=str(e),
                action=tool_name,
                handled=True,
            )

        # 记录到沙箱审计日志
        sandbox = get_sandbox()
        sandbox.log_result(tool_name, args, result)

        # 车控指令执行后验证结果
        verified = self._verify_result(tool_name, result, args)

        # 如果沙箱有参数警告，附加到回复中
        if check and check.warnings:
            verified = SkillResult(
                status=verified.status,
                message=f"{verified.message}（注意: {'; '.join(check.warnings)}）",
                data=verified.data,
                error=verified.error,
                action=verified.action,
                handled=verified.handled,
            )

        return {
            "tool_name": tool_name,
            "args": args,
            "result": verified,
        }

    async def _execute_serial(self, queue: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """串行执行互斥组内的动作。

        同一互斥组（如车窗）内的多个动作按顺序执行，
        确保前一个动作完成后才执行下一个，避免硬件冲突。
        """
        results: list[dict[str, Any]] = []
        for action in queue:
            r = await self._execute_single(action)
            results.append(r)
        return results

    def _aggregate_results(self, all_results: list[dict[str, Any]]) -> dict[str, Any]:
        """聚合多个车控动作的执行结果为统一的 partial state update。

        合并策略:
            - expert_results: 每个动作生成一条独立记录
            - skill_action: 取第一个动作（主动作），多动作记录到 metadata
            - skill_handled: 任一动作 handled=True 则为 True
            - has_side_effect: 任一动作有副作用则为 True
            - reply: 所有动作回复拼接，用换行分隔
        """
        expert_results: list[dict[str, Any]] = []
        replies: list[str] = []
        all_handled = False
        has_side_effect = False
        primary_action = ""
        multi_actions: list[str] = []

        for r in all_results:
            tool_name = r["tool_name"]
            args = r["args"]
            result: SkillResult = r["result"]

            if not primary_action:
                primary_action = tool_name
            else:
                multi_actions.append(tool_name)

            if result.handled:
                all_handled = True
            if result.status != "error":
                has_side_effect = True

            reply = result.message or ""
            expert_results.append({
                "expert": self.expert_name,
                "action": tool_name,
                "reply": reply,
                "handled": result.handled,
                "skill_status": result.status,
                "skill_data": result.data,
            })
            if reply:
                replies.append(reply)

        # 构建合并后的回复文本
        merged_reply = "\n".join(replies) if replies else ""

        update: dict[str, Any] = {
            "expert_results": expert_results,
            "skill_action": primary_action,
            "skill_handled": all_handled,
            "metadata": {
                f"{self.expert_name}_action": primary_action,
                f"{self.expert_name}_handled": all_handled,
            },
        }

        if multi_actions:
            update["metadata"]["multi_actions"] = multi_actions
            logger.info(
                f"Vehicle expert multi-action: primary={primary_action}, "
                f"additional={multi_actions}, total={len(all_results)}"
            )

        if has_side_effect:
            update["has_side_effect"] = True

        # 车控指令直接使用工具返回的自然语言消息，跳过 LLM 合成
        # skip_synthesis=True 时 _build_expert_result 不设置 tool_result

        # 确保 skill_handled 有默认值
        update.setdefault("skill_handled", False)
        update.setdefault("skill_action", "")

        logger.info(
            f"Vehicle expert done: {len(all_results)} actions, "
            f"handled={all_handled}, reply_len={len(merged_reply)}"
        )

        # 直接返回合并结果（不走 _build_expert_result，因为需要自定义结构）
        return update

    def _verify_result(self, tool_name: str, result: Any, args: dict[str, Any]) -> Any:
        """验证车控命令执行结果。

        检查工具返回的 data 是否反映了预期的状态变更，
        避免返回成功但实际未变动的问题。

        Args:
            tool_name: 技能名称（如 vehicle_climate）
            result: SkillResult 执行结果
            args: 原始命令参数

        Returns:
            验证后的 SkillResult（可能修正 message 和 status）
        """
        if not result.handled:
            return result

        data = result.data or {}

        # 空调温度验证
        if tool_name == "vehicle_climate" and "climate" in data:
            climate = data["climate"]
            target_temp = args.get("target_temp")
            if target_temp is not None:
                actual_temp = climate.get("temperature")
                if actual_temp is not None and int(actual_temp) != int(target_temp):
                    logger.warning(
                        f"Climate verification FAILED: target={target_temp}, actual={actual_temp}"
                    )
                    return SkillResult(
                        status="error",
                        message=f"空调温度设置失败，目标 {target_temp} 度，当前 {actual_temp} 度，请重试。",
                        data=data,
                        error="temp_mismatch",
                        action=tool_name,
                        handled=True,
                    )

        # 车窗位置验证
        if tool_name == "vehicle_window" and "windows" in data:
            windows = data["windows"]
            position = args.get("position", "all")
            target_percent = args.get("percent")
            op = args.get("op", "")
            if target_percent is not None:
                actual = windows.get(position, windows.get("all"))
                if actual is not None and int(actual) != int(target_percent):
                    logger.warning(
                        f"Window verification FAILED: pos={position}, target={target_percent}%, actual={actual}%"
                    )
                    return SkillResult(
                        status="error",
                        message=f"车窗设置失败，目标 {target_percent}%，当前 {actual}%，请重试。",
                        data=data,
                        error="position_mismatch",
                        action=tool_name,
                        handled=True,
                    )
            elif op in ("open", "close"):
                expected = 100 if op == "open" else 0
                actual = windows.get(position, windows.get("all"))
                if actual is not None and int(actual) != expected:
                    logger.warning(
                        f"Window verification FAILED: op={op}, pos={position}, expected={expected}%, actual={actual}%"
                    )
                    return SkillResult(
                        status="error",
                        message=f"车窗{op}失败，当前 {actual}%，请重试。",
                        data=data,
                        error="position_mismatch",
                        action=tool_name,
                        handled=True,
                    )

        # 媒体播放验证
        if tool_name == "vehicle_media" and "media" in data:
            media = data["media"]
            op = args.get("op", "")
            if op == "play" and not media.get("playing"):
                logger.warning("Media verification FAILED: play requested but not playing")
                return SkillResult(
                    status="error",
                    message="播放失败，请重试。",
                    data=data,
                    error="play_failed",
                    action=tool_name,
                    handled=True,
                )
            elif op == "pause" and media.get("playing"):
                logger.warning("Media verification FAILED: pause requested but still playing")
                return SkillResult(
                    status="error",
                    message="暂停失败，请重试。",
                    data=data,
                    error="pause_failed",
                    action=tool_name,
                    handled=True,
                )

        logger.info(f"Vehicle command verified OK: {tool_name}")
        return result
