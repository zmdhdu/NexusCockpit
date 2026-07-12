"""
MainAgent 确认层 — 接收 SubAgent 异常上报，二次确认后决定是否放行

设计要点:
1. 订阅 Redis Pub/Sub channel "agent:alert"
2. 收到异常上报后调用 LLM 二次确认
3. 确认结果写入审计日志
4. 提供同步接口供主请求路径查询是否有未决告警

快慢双通道架构:
  - 快通道 (<50ms): 查 Redis 缓存的告警状态，无告警直接放行
  - 慢通道 (<3s): 有 pending 告警时调用 LLM 二次确认

v2.1 新增模块。
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, Optional

import redis.asyncio as aioredis
from openai import AsyncOpenAI

from nexus.config import get_config
from nexus.core.logger import get_logger

logger = get_logger(__name__)

ALERT_CHANNEL = "agent:alert"
ALERT_KEY_PREFIX = "alert:"  # Redis key: alert:{cockpit_id}
ALERT_TTL = 300  # 5 分钟


class MainAgentConfirmLayer:
    """主 Agent 确认层。

    接收 SubAgent 的异常上报，通过 LLM 二次确认后决定是否拦截。
    主请求路径通过 check_before_response() 做快速检查。

    Attributes:
        llm_client: LLM 客户端
        redis_client: Redis 客户端
    """

    def __init__(
        self,
        llm_client: AsyncOpenAI,
        redis_client: Optional[aioredis.Redis] = None,
    ) -> None:
        self.llm_client = llm_client
        self._redis = redis_client
        self._pending_alerts: Dict[str, Dict[str, Any]] = {}  # cockpit_id → latest_alert
        self._pubsub_task: Optional[asyncio.Task] = None
        self._running = False

        config = get_config()
        self._confirm_enabled = config.cockpit.mainagent_confirm_enabled
        self._subagent_model = config.cockpit.subagent_llm_model

    async def start_listening(self) -> None:
        """启动 Redis Pub/Sub 订阅，监听 SubAgent 上报。"""
        if not self._redis or self._running:
            return

        self._running = True
        self._pubsub_task = asyncio.create_task(self._listen_loop())
        logger.info("MainAgent confirm layer started listening for alerts")

    async def stop_listening(self) -> None:
        """停止监听。"""
        self._running = False
        if self._pubsub_task and not self._pubsub_task.done():
            self._pubsub_task.cancel()
            try:
                await self._pubsub_task
            except asyncio.CancelledError:
                pass
        logger.info("MainAgent confirm layer stopped")

    async def _listen_loop(self) -> None:
        """Pub/Sub 订阅循环。"""
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(ALERT_CHANNEL)

        try:
            while self._running:
                try:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=1.0
                    )
                    if message and message["type"] == "message":
                        await self._handle_alert(message["data"])
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"MainAgent pubsub error: {e}")
                    await asyncio.sleep(1)
        finally:
            await pubsub.unsubscribe(ALERT_CHANNEL)
            await pubsub.close()

    async def _handle_alert(self, raw_data: Any) -> None:
        """处理收到的告警消息。

        Args:
            raw_data: Redis Pub/Sub 消息体（JSON 字符串）
        """
        try:
            if isinstance(raw_data, bytes):
                raw_data = raw_data.decode()
            alert = json.loads(raw_data)

            cockpit_id = alert.get("cockpit_id", "")
            logger.warning(
                f"MainAgent received alert from {cockpit_id}: "
                f"type={alert.get('alert_type')}, severity={alert.get('severity')}"
            )

            # 调用 LLM 二次确认
            confirmation = await self._confirm_alert(alert)

            # 合并原始告警和确认结果
            alert["mainagent_confirmation"] = confirmation
            alert["confirm_time"] = time.time()

            # 更新 pending_alerts
            self._pending_alerts[cockpit_id] = alert

            # 写入 Redis 供快通道查询
            if self._redis:
                alert_key = f"{ALERT_KEY_PREFIX}{cockpit_id}"
                await self._redis.setex(
                    alert_key,
                    ALERT_TTL,
                    json.dumps(alert, ensure_ascii=False, default=str),
                )

            logger.info(
                f"MainAgent confirmed alert for {cockpit_id}: "
                f"action={confirmation.get('action')}, "
                f"should_block={confirmation.get('should_block')}"
            )

            # 写入 MySQL 审计日志（非阻塞）
            try:
                from nexus.core.db_manager import get_db_manager
                db = get_db_manager()
                if db.is_connected:
                    await db.insert_mainagent_log(
                        cockpit_id=cockpit_id,
                        alert_type=alert.get("alert_type", "unknown"),
                        severity=alert.get("severity", "low"),
                        subagent_judgment=alert.get("llm_judgment", {}),
                        mainagent_judgment=confirmation,
                        action_taken=confirmation.get("action", "pass"),
                        alert_time=alert.get("alert_time"),
                        confirm_time=alert.get("confirm_time"),
                    )

                    # 记录 LLM 成本
                    await db.insert_llm_cost(
                        cockpit_id=cockpit_id,
                        request_type="mainagent_confirm",
                        model_name=self._subagent_model,
                        prompt_tokens=0,  # 实际应从 LLM response 获取
                        completion_tokens=0,
                        cost_yuan=0.0,
                    )
            except Exception as db_err:
                logger.debug(f"MainAgent MySQL log write failed: {db_err}")

        except Exception as e:
            logger.error(f"MainAgent alert handling error: {e}")

    async def _confirm_alert(self, alert: Dict[str, Any]) -> Dict[str, Any]:
        """调用 LLM 对 SubAgent 上报的异常进行二次确认。

        Args:
            alert: SubAgent 上报的告警信息

        Returns:
            LLM 的确认结果
        """
        prompt = f"""你是主 Agent，SubAgent 上报了以下异常，请二次确认：

座舱 ID: {alert.get('cockpit_id')}
异常类型: {alert.get('alert_type')}
严重程度: {alert.get('severity')}
SubAgent 描述: {alert.get('description')}
建议处置: {alert.get('suggested_action')}

请判断:
1. 此异常是否为真实故障？（排除误报）
2. 是否需要拦截该座舱的执行结果？
3. 降级策略是什么？

返回 JSON（不要有其他内容）:
{{
  "confirmed": true/false,
  "should_block": true/false,
  "action": "pass/degrade/block/alert_only",
  "degrade_strategy": "降级策略说明",
  "reason": "确认理由"
}}"""

        try:
            response = await self.llm_client.chat.completions.create(
                model=self._subagent_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=200,
            )
            content = response.choices[0].message.content or ""

            import re
            json_match = re.search(r'\{[^{}]+\}', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())

            return {"confirmed": False, "action": "pass", "reason": "LLM parse error"}

        except Exception as e:
            logger.error(f"MainAgent LLM confirm failed: {e}")
            # LLM 不可用时，信任 SubAgent 的判断但默认不拦截
            return {
                "confirmed": alert.get("severity") == "high",
                "should_block": False,
                "action": "alert_only",
                "reason": f"LLM unavailable: {e}",
            }

    async def check_before_response(self, cockpit_id: str) -> Optional[Dict[str, Any]]:
        """主请求路径调用：返回该座舱是否有未决告警。

        快通道 (<50ms)：查 Redis 缓存的告警状态。
        如果 Redis 中有 confirmed_block → 返回告警信息。
        如果无告警或 confirmed_pass → 返回 None（放行）。

        Args:
            cockpit_id: 座舱 ID

        Returns:
            告警信息字典（需要拦截时）或 None（放行时）
        """
        if not self._confirm_enabled:
            return None

        # 快通道：先查 Redis 缓存
        if self._redis:
            try:
                alert_key = f"{ALERT_KEY_PREFIX}{cockpit_id}"
                raw = await self._redis.get(alert_key)
                if raw:
                    if isinstance(raw, bytes):
                        raw = raw.decode()
                    alert = json.loads(raw)
                    confirmation = alert.get("mainagent_confirmation", {})
                    action = confirmation.get("action", "pass")
                    if action in ("block", "degrade"):
                        return alert
                    # action=pass 或 alert_only → 放行
                    return None
            except Exception as e:
                logger.debug(f"MainAgent fast-path check error: {e}")

        # 回退到内存缓存
        alert = self._pending_alerts.get(cockpit_id)
        if alert:
            confirmation = alert.get("mainagent_confirmation", {})
            action = confirmation.get("action", "pass")
            if action in ("block", "degrade"):
                return alert

        return None

    def get_pending_alerts(self) -> Dict[str, Dict[str, Any]]:
        """获取所有未决告警。"""
        return dict(self._pending_alerts)

    def clear_alert(self, cockpit_id: str) -> None:
        """清除指定座舱的告警。"""
        self._pending_alerts.pop(cockpit_id, None)
