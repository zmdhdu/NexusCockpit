# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
车辆健康/诊断技能组 — v2.0 新增

3 个技能:
  1. diagnose_vehicle:    车辆异常问题解读，调取车辆状态
  2. decode_dtc:          故障码释义，查询故障知识库
  3. maintenance_advice:  根据里程/时间生成保养建议

依赖: Cherry 知识库（Phase 3 实现后生效），车辆状态适配器
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from nexus.core.logger import get_logger
from nexus.skills.base import BaseSkill, SkillGroup, SkillResult, register_skill

logger = get_logger(__name__)


@register_skill(
    "diagnose_vehicle",
    SkillGroup.HEALTH,
    description="当用户询问车辆异常、异响、报警、故障灯等健康问题时调用此技能。",
    cache_ttl=3600,
)
class DiagnoseVehicleSkill(BaseSkill):
    """车辆诊断技能：调取车辆状态 + 知识库检索诊断建议。"""

    name = "diagnose_vehicle"
    required_parameters = ["query"]
    optional_parameters = ["user_id"]
    examples = [
        {"input": "发动机故障灯亮了", "arguments": {"query": "发动机故障灯亮"}},
        {"input": "刹车有异响", "arguments": {"query": "刹车异响"}},
    ]
    parameters = {
        "query": {"type": "string", "description": "车辆异常问题描述"},
    }

    def __init__(self, vehicle_adapter=None):
        self.vehicle_adapter = vehicle_adapter

    async def execute(self, query: str = "", **kwargs: Any) -> SkillResult:
        logger.info(f"DiagnoseVehicle: query={query}")

        # 调取车辆状态
        vehicle_status: Dict[str, Any] = {}
        if self.vehicle_adapter:
            try:
                result = self.vehicle_adapter.invoke_command("vehicle_status", {"op": "status"})
                vehicle_status = result.data if hasattr(result, "data") else {}
            except Exception as e:
                logger.warning(f"Vehicle status query failed: {e}")

        # 知识库检索（Phase 3 后接入 Cherry KB）
        kb_answer = self._search_knowledge_base(query)

        # 组装诊断报告
        diagnosis_parts: list[str] = []
        if vehicle_status:
            diagnosis_parts.append(f"【车辆状态】{vehicle_status}")
        if kb_answer:
            diagnosis_parts.append(f"【诊断建议】{kb_answer}")

        if not diagnosis_parts:
            diagnosis_parts.append("建议您前往4S店进行专业检测。")

        return SkillResult(
            status="ok",
            message="\n".join(diagnosis_parts),
            search_context=kb_answer,
            action="diagnose_vehicle",
            handled=True,
            metadata={"query": query, "has_status": bool(vehicle_status)},
        )

    def _search_knowledge_base(self, query: str) -> str:
        """搜索 Cherry 知识库（Phase 3 接入）。"""
        # TODO: Phase 3 接入 Cherry KB 检索
        return ""


@register_skill(
    "decode_dtc",
    SkillGroup.HEALTH,
    description="当用户提供故障码（如P0301、U0073）要求翻译时调用此技能。",
    cache_ttl=86400,
)
class DecodeDtcSkill(BaseSkill):
    """故障码翻译技能：查询故障知识库。"""

    name = "decode_dtc"
    required_parameters = ["dtc_code"]
    examples = [
        {"input": "P0301是什么故障码", "arguments": {"dtc_code": "P0301"}},
        {"input": "U0073什么意思", "arguments": {"dtc_code": "U0073"}},
    ]
    parameters = {
        "dtc_code": {"type": "string", "description": "OBD-II 故障码，如 P0301"},
    }

    # 常见故障码速查表（Phase 3 由 Cherry KB 替代）
    _DTC_QUICK_REF = {
        "P0301": "第1缸失火 — 可能原因：火花塞、点火线圈、燃油喷射器",
        "P0300": "多缸随机失火 — 可能原因：进气系统漏气、燃油压力不足",
        "P0171": "混合气过稀 — 可能原因：进气管漏气、MAF传感器故障",
        "P0420": "催化效率低于阈值 — 可能原因：催化转换器老化",
        "U0073": "CAN总线通信故障 — 可能原因：总线接线松动、模块故障",
        "P0128": "冷却液温度低于节温器调节温度 — 可能原因：节温器故障",
    }

    async def execute(self, dtc_code: str = "", **kwargs: Any) -> SkillResult:
        logger.info(f"DecodeDTC: code={dtc_code}")

        if not dtc_code:
            return SkillResult(
                status="error",
                message="请提供故障码。",
                action="decode_dtc",
                handled=True,
            )

        code = dtc_code.strip().upper()
        explanation = self._DTC_QUICK_REF.get(code, "")

        if not explanation:
            # TODO: Phase 3 查询 Cherry KB
            explanation = f"故障码 {code} 未在速查表中找到，建议查询专业维修手册或前往4S店。"

        return SkillResult(
            status="ok",
            message=f"故障码 {code}：{explanation}",
            search_context=explanation,
            action="decode_dtc",
            handled=True,
            metadata={"dtc_code": code},
        )


@register_skill(
    "maintenance_advice",
    SkillGroup.HEALTH,
    description="当用户询问保养建议、保养周期、何时保养时调用此技能。",
    cache_ttl=86400,
)
class MaintenanceAdviceSkill(BaseSkill):
    """保养建议技能：根据里程/时间生成保养建议。"""

    name = "maintenance_advice"
    required_parameters: list[str] = []
    optional_parameters = ["mileage", "months"]
    examples = [
        {"input": "我该保养了吗", "arguments": {}},
        {"input": "车开了5万公里需要做什么保养", "arguments": {"mileage": 50000}},
    ]
    parameters = {
        "mileage": {"type": "integer", "description": "当前里程数（公里）"},
        "months": {"type": "integer", "description": "上次保养至今的月数"},
    }

    def __init__(self, vehicle_adapter=None):
        self.vehicle_adapter = vehicle_adapter

    async def execute(self, mileage: int = 0, months: int = 0, **kwargs: Any) -> SkillResult:
        logger.info(f"MaintenanceAdvice: mileage={mileage}, months={months}")

        # 尝试从车辆适配器获取里程
        if not mileage and self.vehicle_adapter:
            try:
                result = self.vehicle_adapter.invoke_command("vehicle_status", {"op": "status"})
                if hasattr(result, "data"):
                    mileage = result.data.get("mileage", 0)
            except Exception:
                pass

        advice_items: list[str] = []

        # 里程保养规则
        if mileage >= 50000:
            advice_items.append("• 5万公里大保：更换刹车油、变速箱油、火花塞")
        elif mileage >= 30000:
            advice_items.append("• 3万公里保养：更换空气滤芯、空调滤芯")
        elif mileage >= 10000:
            advice_items.append("• 1万公里保养：更换机油、机滤")

        # 时间保养规则
        if months >= 12:
            advice_items.append("• 超过1年未保养：建议立即做全面检查")
        elif months >= 6:
            advice_items.append("• 6个月保养：检查轮胎、刹车片磨损")

        if not advice_items:
            advice_items.append("• 暂无需特殊保养，保持定期检查即可。")

        message = f"【保养建议】（里程：{mileage}km）\n" + "\n".join(advice_items)
        return SkillResult(
            status="ok",
            message=message,
            action="maintenance_advice",
            handled=True,
            metadata={"mileage": mileage, "months": months},
        )
