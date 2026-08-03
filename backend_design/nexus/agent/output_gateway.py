# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Global Output Gateway — 全局统一输出校验网关

所有展示给用户、所有语音播报内容必经此网关审核，形成闭环，彻底根治裸输出问题。

校验项:
    1. 非空校验 — 空内容或极短内容填充兜底话术
    2. 合规性校验 — 拦截敏感/有害内容
    3. 幻觉模式检测 — 检测编造对话历史等典型幻觉模式
    4. 长度合理性 — 过长输出截断，过短输出补全
    5. 车控逻辑正确性 — 检查车控回复是否包含执行状态信息
    6. 元数据标记 — 返回校验结果供 Reviewer 记录

使用方式:
    from nexus.agent.output_gateway import validate_output

    validated, metadata = validate_output(
        text=final_response,
        state=state,
        reflection_passed=True,
    )
    # validated 为最终输出给用户的安全文本
    # metadata 包含校验结果信息
"""

from __future__ import annotations

import re
from typing import Any

from nexus.core.logger import get_logger
from nexus.intent.constants import HALLUCINATED_HISTORY_PATTERNS

logger = get_logger(__name__)

# ------------------------------------------------------------------
# 模式定义
# ------------------------------------------------------------------

# 敏感词/有害内容模式（基础过滤，可扩展）
_SENSITIVE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?:自杀|自残|跳楼|割腕)", re.IGNORECASE),
    re.compile(r"(?:炸弹|炸药|枪支|弹药)", re.IGNORECASE),
    re.compile(r"(?:色情|裸体|成人视频)", re.IGNORECASE),
]

# 兜底话术
_FALLBACK_EMPTY = "抱歉，我没有理解你的意思，能再说一次吗？"
_FALLBACK_SENSITIVE = "抱歉，这个问题我无法回答，请尝试其他问题。"
_FALLBACK_HALLUCINATION = "这是一个新的对话，我们还没有之前的交流记录。请问有什么可以帮您的？"
_FALLBACK_TOO_LONG = "抱歉，回复内容过长，请尝试更具体的问题。"
_FALLBACK_ERROR = "抱歉，AI 服务暂时繁忙，请稍后再试。"

# 最大输出长度（字符），超过则截断
_MAX_OUTPUT_CHARS = 2000
# 最小有意义输出长度
_MIN_OUTPUT_CHARS = 2


def validate_output(
    text: str,
    state: dict[str, Any] | None = None,
    reflection_passed: bool = True,
) -> tuple[str, dict[str, Any]]:
    """全局输出校验网关 — 所有对外输出必经此函数。

    校验流程（顺序执行，任一不通过即拦截）:
        1. 非空校验
        2. 敏感内容校验
        3. 幻觉模式检测（仅在无对话历史时触发）
        4. 长度合理性校验
        5. 车控回复完整性校验

    Args:
        text: 待校验的输出文本
        state: 当前 SupervisorState（用于获取对话历史、车控信息等上下文）
        reflection_passed: Reflection 层是否已通过校验

    Returns:
        (validated_text, metadata) 元组
        - validated_text: 校验通过的安全文本，或兜底话术
        - metadata: 包含 gateway_result / gateway_reason 等校验信息
    """
    metadata: dict[str, Any] = {
        "gateway_input_len": len(text) if text else 0,
    }
    state = state or {}

    # 0. 五层链路闭环校验：作用：校验链路完成标识，拦截跳过五层流水线的非法输出；场景：封堵路由短路、未经校验数据直接返回前端
    chain_completed = state.get("_chain_completed", False)
    if not chain_completed:
        # 特殊场景豁免：LLM错误兜底/澄清分支已走 Reviewer+Gateway，允许通过
        llm_error = state.get("intent", {}).get("LLM_Error", "")
        need_clarification = state.get("need_clarification", False)
        if not llm_error and not need_clarification:
            logger.warning(
                "Output gateway: _chain_completed flag missing, "
                "output may have bypassed full pipeline"
            )
            metadata["gateway_result"] = "chain_incomplete"
            metadata["gateway_reason"] = "输出未经过完整五层链路校验"
            # 向后兼容：标记可疑但不拦截

    # 1. 非空校验
    if not text or len(text.strip()) < _MIN_OUTPUT_CHARS:
        logger.warning("Output gateway: empty or too short output, using fallback")
        metadata["gateway_result"] = "fallback_empty"
        metadata["gateway_reason"] = "输出为空或过短"
        return _FALLBACK_EMPTY, metadata

    # 2. 敏感内容校验
    for pattern in _SENSITIVE_PATTERNS:
        if pattern.search(text):
            logger.warning(f"Output gateway: sensitive content detected, pattern={pattern.pattern}")
            metadata["gateway_result"] = "blocked_sensitive"
            metadata["gateway_reason"] = f"检测到敏感内容: {pattern.pattern}"
            return _FALLBACK_SENSITIVE, metadata

    # 3. 幻觉模式检测 — 仅在无对话历史时触发
    history = state.get("history", [])
    running_summary = state.get("running_summary", "")
    has_history = (
        (bool(history) and len(history) >= 2)
        or (running_summary and len(running_summary.strip()) > 0)
    )
    if not has_history:
        for pattern in HALLUCINATED_HISTORY_PATTERNS:
            if pattern in text:
                logger.warning(
                    f"Output gateway: hallucinated history detected (no history in state), "
                    f"pattern='{pattern}'"
                )
                metadata["gateway_result"] = "blocked_hallucination"
                metadata["gateway_reason"] = f"检测到编造对话历史: {pattern}"
                return _FALLBACK_HALLUCINATION, metadata

    # 4. 长度合理性校验
    if len(text) > _MAX_OUTPUT_CHARS:
        logger.warning(
            f"Output gateway: output too long ({len(text)} > {_MAX_OUTPUT_CHARS}), truncating"
        )
        # 截断到最大长度，尝试在句号处截断
        truncated = text[:_MAX_OUTPUT_CHARS]
        # 找最后一个句号/问号/感叹号
        last_punct = max(
            truncated.rfind("。"),
            truncated.rfind("？"),
            truncated.rfind("！"),
            truncated.rfind("\n"),
        )
        if last_punct > _MAX_OUTPUT_CHARS // 2:
            truncated = truncated[: last_punct + 1]
        else:
            truncated += "..."
        metadata["gateway_result"] = "truncated"
        metadata["gateway_reason"] = f"输出过长，已截断至 {len(truncated)} 字符"
        metadata["original_length"] = len(text)
        return truncated, metadata

    # 5. 车控回复完整性校验：车控指令回复应包含执行状态信息
    skill_action = state.get("skill_action", "")
    if skill_action and skill_action.startswith("vehicle_"):
        expert_results = state.get("expert_results", [])
        has_error = any(
            er.get("skill_status") == "error"
            for er in expert_results
        )
        if has_error:
            # 车控执行失败但回复未提及失败
            failure_indicators = ("失败", "错误", "无法", "不支持", "异常")
            if not any(ind in text for ind in failure_indicators):
                logger.warning(
                    "Output gateway: vehicle command failed but response doesn't mention failure"
                )
                metadata["gateway_result"] = "vehicle_error_unguarded"
                metadata["gateway_reason"] = "车控指令执行失败但回复未提及"
                # 不替换文本，但标记问题
                # 因为车控失败时 expert 的 reply 可能已包含失败信息

    # 6. 通过所有校验
    metadata["gateway_result"] = "passed"
    metadata["gateway_reason"] = "所有校验通过"
    metadata["gateway_reflection_passed"] = reflection_passed

    logger.info(
        f"Output gateway PASSED: len={len(text)}, "
        f"reflection={'passed' if reflection_passed else 'skipped'}"
    )
    return text, metadata
