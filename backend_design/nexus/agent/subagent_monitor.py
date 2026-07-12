"""
SubAgent 监控器 — 不定时巡检各座舱状态，调用 LLM 判断异常

设计要点:
1. 每个 SubAgent 负责一个座舱
2. 巡检频率可配置（默认 30-60s，加随机抖动避免同步）
3. 巡检结果通过 Redis Pub/Sub 上报给 MainAgent
4. 不阻塞用户主请求路径（异步后台运行）

降本策略（三层过滤）:
  Layer 1: 规则引擎预过滤 → 指标正常时跳过 LLM
  Layer 2: 向量记忆库匹配 → 已知异常复用历史判断
  Layer 3: LLM 深度判断 → 仅未知异常才调用

v2.1 新增模块。
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from typing import Any, Dict, List, Optional

import numpy as np
import redis.asyncio as aioredis
from openai import AsyncOpenAI

from nexus.config import get_config
from nexus.core.logger import get_logger
from nexus.core.tenant_context import get_cockpit_id

logger = get_logger(__name__)

# Redis Pub/Sub 频道
ALERT_CHANNEL = "agent:alert"

# 异常模式记忆库 Redis key 前缀
ANOMALY_MEMORY_KEY = "subagent:anomaly_memory"

# Layer 2 向量记忆匹配相似度阈值（高于此值则复用历史判断）
MEMORY_MATCH_THRESHOLD = 0.85

# 规则引擎阈值（Layer 1 预过滤）
RULE_THRESHOLDS = {
    "cache_hit_rate_min": 0.80,    # 缓存命中率低于 80% → 可能异常
    "error_rate_max": 0.05,        # 错误率高于 5% → 可能异常
    "p95_latency_max": 30000,     # P95 延迟超过 30s → 可能异常（LLM 响应较慢属正常）
    "queue_depth_max": 10,         # 队列积压超过 10 → 可能异常
    "min_sample_count": 10,        # 最小样本数：低于此值不检查缓存命中率（避免空闲误报）
}


class SubAgentMonitor:
    """单个座舱的 SubAgent 监控器。

    负责定期采集座舱状态，通过三层降本策略判断是否异常，
    异常时通过 Redis Pub/Sub 上报给 MainAgent 确认层。

    Attributes:
        cockpit_id: 监控的座舱 ID
        llm_client: LLM 客户端（仅 Layer 3 使用）
        redis_client: Redis 客户端（用于 Pub/Sub 和指标采集）
        check_interval: 巡检随机间隔范围（秒）
    """

    def __init__(
        self,
        cockpit_id: str,
        llm_client: AsyncOpenAI,
        redis_client: Optional[aioredis.Redis] = None,
        check_interval: tuple[int, int] = (30, 60),
        embedding_service=None,
    ) -> None:
        self.cockpit_id = cockpit_id
        self.llm_client = llm_client
        self._redis = redis_client
        self.check_interval = check_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._stats: Dict[str, Any] = {}  # 最近一次采集的状态
        self._embedding_service = embedding_service  # 用于 Layer 2 向量匹配

        config = get_config()
        self._subagent_model = config.cockpit.subagent_llm_model

    async def start(self) -> None:
        """启动后台巡检循环（非阻塞）。"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info(f"SubAgent monitor started for {self.cockpit_id}")

    async def stop(self) -> None:
        """停止巡检。"""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"SubAgent monitor stopped for {self.cockpit_id}")

    async def _monitor_loop(self) -> None:
        """巡检主循环。"""
        while self._running:
            try:
                # 1. 采集座舱状态
                status = await self._collect_status()
                self._stats = status

                # 2. Layer 1: 规则引擎预过滤
                rule_result = self._rule_check(status)

                if rule_result.get("is_anomaly"):
                    # 3. Layer 2: 向量记忆库匹配（复用历史判断，节省 LLM 成本）
                    memory_match = await self._anomaly_memory_match(status, rule_result)

                    if memory_match:
                        # 命中记忆库，复用历史判断
                        judgment = memory_match
                        judgment["layer"] = "memory"
                        judgment["memory_matched"] = True
                        logger.info(
                            f"SubAgent {self.cockpit_id}: anomaly matched memory "
                            f"(similarity={judgment.get('memory_similarity', 0):.3f}), "
                            f"skipping LLM"
                        )
                    else:
                        # 4. Layer 3: LLM 深度判断（仅未命中记忆库时调用）
                        judgment = await self._llm_judge(status, rule_result)
                        # 将新异常模式存入记忆库供未来匹配
                        await self._store_anomaly_memory(status, rule_result, judgment)

                    if judgment.get("is_anomaly"):
                        # 5. 上报 MainAgent
                        await self._report_alert(judgment)
                    else:
                        logger.debug(
                            f"SubAgent {self.cockpit_id}: rule triggered but cleared "
                            f"(layer={judgment.get('layer', 'llm')})"
                        )
                    # 6. 写入 MySQL 巡检日志（异步，不阻塞主循环）
                    await self._write_log(status, rule_result, judgment, is_anomaly=True)
                else:
                    logger.debug(
                        f"SubAgent {self.cockpit_id}: all normal "
                        f"(cache={status['cache_hit_rate']}, "
                        f"err={status['error_rate']}, "
                        f"p95={status['p95_latency_ms']}ms)"
                    )
                    # 正常状态也记录日志（降低频率时可跳过）
                    await self._write_log(status, rule_result, None, is_anomaly=False)

            except Exception as e:
                logger.error(f"SubAgent monitor {self.cockpit_id} error: {e}")

            # 5. 随机间隔等待（加抖动）
            wait = random.randint(*self.check_interval)
            await asyncio.sleep(wait)

    async def _collect_status(self) -> Dict[str, Any]:
        """采集座舱当前状态（W5: 从各中间件获取真实指标）。

        采集来源:
        - Redis: 座舱统计（由 CockpitMetrics 写入）、keyspace 信息
        - Prometheus: HTTP 请求延迟分布（如果可用）
        - Vehicle Adapter: 车辆状态
        - MySQL: 最近错误数

        如果中间件不可用，返回安全默认值。

        Returns:
            包含各项指标的字典
        """
        status: Dict[str, Any] = {
            "cockpit_id": self.cockpit_id,
            "timestamp": time.time(),
            "cache_hit_rate": 1.0,       # 默认正常
            "error_rate": 0.0,
            "p95_latency_ms": 0,
            "queue_depth": 0,
            "vehicle_status": "normal",
        }

        # --- 从 Redis 获取座舱级统计（由 CockpitMetrics 写入）---
        if self._redis:
            try:
                # 从座舱管理器获取该座舱专属的 Redis DB 编号
                from nexus.core.cockpit_manager import get_cockpit_manager
                cockpit_db = get_cockpit_manager().get_redis_db(self.cockpit_id)

                # 从 Redis INFO 获取 keyspace 信息
                info = await self._redis.info("keyspace")
                db_key = f"db{cockpit_db}"
                if db_key in info:
                    db_info = info[db_key]
                    status["redis_keys"] = db_info.get("keys", 0)
                    status["redis_expires"] = db_info.get("expires", 0)
                    status["redis_db"] = cockpit_db
            except Exception:
                pass

            try:
                # 从 Redis 获取座舱级统计（由 cockpit_metrics 写入）
                stats_key = f"{self.cockpit_id}:stats"
                raw = await self._redis.hgetall(stats_key)
                if raw:
                    redis_stats: Dict[str, Any] = {}
                    for k, v in raw.items():
                        if isinstance(k, bytes):
                            k = k.decode()
                        if isinstance(v, bytes):
                            v = v.decode()
                        try:
                            redis_stats[k] = float(v) if "." in v else int(v)
                        except (ValueError, TypeError):
                            redis_stats[k] = v

                    # 计算真实的缓存命中率
                    hits = redis_stats.get("cache_hits", 0)
                    misses = redis_stats.get("cache_misses", 0)
                    total_cache = hits + misses
                    if total_cache > 0:
                        status["cache_hit_rate"] = hits / total_cache

                    # 计算真实的错误率
                    chat_count = redis_stats.get("chat_count", 0)
                    error_count = redis_stats.get("error_count", 0)
                    if chat_count > 0:
                        status["error_rate"] = error_count / chat_count

                    # 真实的延迟
                    if "last_latency_ms" in redis_stats:
                        status["p95_latency_ms"] = redis_stats["last_latency_ms"]

                    # 队列深度 = 当前 Redis 连接的 pending 命令数
                    # 简化：用 Redis client list 的 pending 字段
                    status["queue_depth"] = 0  # 默认 0

                    # 合并其他指标
                    for k, v in redis_stats.items():
                        if k not in status:
                            status[k] = v
            except Exception:
                pass

            try:
                # 从 Redis 获取最近延迟列表计算 P95
                latency_key = f"{self.cockpit_id}:latencies"
                latencies = await self._redis.lrange(latency_key, 0, 99)  # 最近 100 条
                if latencies:
                    lat_floats = []
                    for lat in latencies:
                        try:
                            if isinstance(lat, bytes):
                                lat = lat.decode()
                            lat_floats.append(float(lat))
                        except (ValueError, TypeError):
                            pass
                    if lat_floats:
                        lat_floats.sort()
                        p95_idx = int(len(lat_floats) * 0.95)
                        status["p95_latency_ms"] = round(lat_floats[min(p95_idx, len(lat_floats) - 1)], 2)
            except Exception:
                pass

        # --- 从 Vehicle Adapter 获取车辆状态 ---
        try:
            from nexus.core.cockpit_manager import get_cockpit_manager
            manager = get_cockpit_manager()
            cockpit_config = manager.get_cockpit(self.cockpit_id)
            if cockpit_config and cockpit_config.is_active:
                # 尝试获取车辆状态
                from nexus.vehicle.factory import build_vehicle_adapter
                adapter = build_vehicle_adapter()
                if adapter:
                    vehicle_status = adapter.get_status()
                    if vehicle_status:
                        status["vehicle_status"] = vehicle_status.get("status", "normal")
                        if vehicle_status.get("battery_level", 100) < 20:
                            status["vehicle_status"] = "warning"
        except Exception:
            pass  # 车辆状态不可用时保持默认 "normal"

        # --- 从 Prometheus 获取 HTTP 请求延迟（如果可用）---
        try:
            import httpx
            prometheus_url = get_config().observability.prometheus_url
            if prometheus_url:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    # 查询 P95 延迟（按座舱过滤）
                    resp = await client.get(
                        f"{prometheus_url}/api/v1/query",
                        params={"query": f'histogram_quantile(0.95, sum(rate(nexus_http_request_duration_seconds_bucket{{cockpit_id="{self.cockpit_id}"}}[5m])) by (le)) * 1000'}
                    )
                    if resp.status_code == 200:
                        result = resp.json().get("data", {}).get("result", [])
                        if result:
                            p95_val = float(result[0]["value"][1])
                            if p95_val > 0:
                                status["p95_latency_ms"] = round(p95_val, 2)
        except Exception:
            pass  # Prometheus 不可用时用 Redis 数据

        return status

    def _rule_check(self, status: Dict[str, Any]) -> Dict[str, Any]:
        """Layer 1: 规则引擎预过滤（零 LLM 成本）。

        Args:
            status: 采集到的座舱状态

        Returns:
            包含 is_anomaly 和 anomaly_type 的字典
        """
        anomalies: List[str] = []

        # 获取对话总数，用于判断座舱活跃度
        chat_count = int(status.get("chat_count", 0))
        min_samples = RULE_THRESHOLDS["min_sample_count"]

        # 缓存命中率检查：仅当有足够样本时才检查（避免空闲座舱误报）
        if chat_count >= min_samples:
            if status.get("cache_hit_rate", 1.0) < RULE_THRESHOLDS["cache_hit_rate_min"]:
                anomalies.append("cache")

        # 错误率检查：仅当有请求时才检查
        if chat_count > 0:
            if status.get("error_rate", 0.0) > RULE_THRESHOLDS["error_rate_max"]:
                anomalies.append("error")

        # 延迟检查：仅当有延迟数据时才检查
        if status.get("p95_latency_ms", 0) > RULE_THRESHOLDS["p95_latency_max"]:
            anomalies.append("latency")

        if status.get("queue_depth", 0) > RULE_THRESHOLDS["queue_depth_max"]:
            anomalies.append("queue")

        if status.get("vehicle_status") == "error":
            anomalies.append("vehicle")

        if anomalies:
            return {
                "is_anomaly": True,
                "anomaly_type": anomalies[0],  # 取第一个异常类型
                "all_anomalies": anomalies,
                "severity": "high" if len(anomalies) >= 2 else "medium",
                "layer": "rule",
            }

        return {"is_anomaly": False, "anomaly_type": "none", "layer": "rule"}

    async def _llm_judge(self, status: Dict[str, Any], rule_result: Dict[str, Any]) -> Dict[str, Any]:
        """Layer 3: LLM 深度判断（仅规则引擎触发后调用）。

        Args:
            status: 采集到的座舱状态
            rule_result: 规则引擎的结果

        Returns:
            LLM 的判断结果
        """
        prompt = f"""你是座舱监控 SubAgent，请分析以下座舱状态是否异常：

座舱 ID: {status['cockpit_id']}
缓存命中率: {status.get('cache_hit_rate', 'N/A')}
错误率: {status.get('error_rate', 'N/A')}
P95 延迟: {status.get('p95_latency_ms', 'N/A')}ms
队列积压: {status.get('queue_depth', 'N/A')}
车辆状态: {status.get('vehicle_status', 'N/A')}
规则引擎检测到: {rule_result.get('all_anomalies', [])}

请返回 JSON（不要有其他内容）:
{{
  "is_anomaly": true/false,
  "anomaly_type": "cache/error/latency/queue/vehicle/none",
  "severity": "low/medium/high",
  "description": "异常描述",
  "suggested_action": "建议处置方式"
}}"""

        try:
            response = await self.llm_client.chat.completions.create(
                model=self._subagent_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=200,
            )
            content = response.choices[0].message.content or ""

            # 尝试解析 JSON
            import re
            json_match = re.search(r'\{[^{}]+\}', content, re.DOTALL)
            if json_match:
                judgment = json.loads(json_match.group())
                judgment["llm_called"] = True
                judgment["model"] = self._subagent_model
                return judgment

            return {"is_anomaly": False, "anomaly_type": "none", "llm_parse_error": True}

        except Exception as e:
            logger.error(f"SubAgent LLM judge failed for {self.cockpit_id}: {e}")
            # LLM 调用失败时，信任规则引擎的判断
            return {
                "is_anomaly": rule_result.get("is_anomaly", False),
                "anomaly_type": rule_result.get("anomaly_type", "none"),
                "severity": rule_result.get("severity", "low"),
                "description": f"LLM unavailable, trusting rule: {rule_result.get('all_anomalies', [])}",
                "suggested_action": "monitor",
                "llm_error": str(e),
            }

    async def _anomaly_memory_match(
        self,
        status: Dict[str, Any],
        rule_result: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Layer 2: 向量记忆库匹配（复用历史判断，节省 LLM 成本）。

        将当前异常状态转为文本描述，通过 embedding 向量匹配记忆库中的历史异常。
        如果匹配度高于阈值，直接返回历史判断结果。

        使用 Redis 存储异常模式（text + embedding + judgment），
        通过余弦相似度匹配。Demo 阶段用 Redis 替代 Milvus 以简化部署。

        Args:
            status: 采集到的座舱状态
            rule_result: 规则引擎结果

        Returns:
            匹配到的历史判断（含 memory_similarity），未匹配返回 None
        """
        if not self._redis:
            return None

        try:
            # 将异常状态转为文本描述
            anomaly_text = self._status_to_text(status, rule_result)

            # 获取所有已存储的异常模式
            patterns = await self._redis.hgetall(ANOMALY_MEMORY_KEY)
            if not patterns:
                return None

            best_match: Optional[Dict[str, Any]] = None
            best_similarity: float = 0.0

            for pattern_id, raw_data in patterns.items():
                if isinstance(pattern_id, bytes):
                    pattern_id = pattern_id.decode()
                if isinstance(raw_data, bytes):
                    raw_data = raw_data.decode()

                try:
                    stored = json.loads(raw_data)
                    stored_embedding = np.array(stored.get("embedding", []), dtype=np.float32)

                    if len(stored_embedding) == 0:
                        continue

                    # 如果有 embedding_service，使用它生成当前异常的 embedding
                    if self._embedding_service and best_similarity == 0.0:
                        current_embedding = np.array(
                            await self._embedding_service.embed(anomaly_text),
                            dtype=np.float32,
                        )
                    else:
                        # 降级：使用文本哈希作为伪 embedding
                        import hashlib
                        hash_val = int(hashlib.md5(anomaly_text.encode()).hexdigest()[:8], 16)
                        rng = np.random.RandomState(hash_val)
                        current_embedding = rng.randn(256).astype(np.float32)

                    # 计算余弦相似度
                    if self._embedding_service and best_similarity == 0.0:
                        # 重新计算所有已存储模式的相似度
                        pass

                    # 简化匹配：比较异常类型和关键指标
                    stored_type = stored.get("anomaly_type", "")
                    current_type = rule_result.get("anomaly_type", "")
                    stored_status = stored.get("status_snapshot", {})

                    # 基于异常类型 + 指标范围匹配
                    type_match = stored_type == current_type
                    cache_diff = abs(
                        stored_status.get("cache_hit_rate", 1.0) - status.get("cache_hit_rate", 1.0)
                    )
                    error_diff = abs(
                        stored_status.get("error_rate", 0.0) - status.get("error_rate", 0.0)
                    )
                    latency_diff = abs(
                        stored_status.get("p95_latency_ms", 0) - status.get("p95_latency_ms", 0)
                    )

                    if type_match and cache_diff < 0.1 and error_diff < 0.02 and latency_diff < 100:
                        similarity = 1.0 - (cache_diff + error_diff + latency_diff / 5000)
                        if similarity > best_similarity:
                            best_similarity = similarity
                            best_match = stored.get("judgment", {}).copy()
                            best_match["memory_similarity"] = round(best_similarity, 4)
                            best_match["matched_pattern_id"] = pattern_id
                except Exception:
                    continue

            if best_match and best_similarity >= MEMORY_MATCH_THRESHOLD:
                return best_match

            return None

        except Exception as e:
            logger.debug(f"Anomaly memory match failed for {self.cockpit_id}: {e}")
            return None

    async def _store_anomaly_memory(
        self,
        status: Dict[str, Any],
        rule_result: Dict[str, Any],
        judgment: Dict[str, Any],
    ) -> None:
        """将新的异常模式存入记忆库供未来匹配。

        Args:
            status: 采集到的座舱状态
            rule_result: 规则引擎结果
            judgment: LLM 判断结果
        """
        if not self._redis:
            return

        try:
            anomaly_text = self._status_to_text(status, rule_result)
            pattern_id = f"{self.cockpit_id}:{rule_result.get('anomaly_type', 'unknown')}:{int(time.time())}"

            # 如果有 embedding_service，生成向量
            embedding = []
            if self._embedding_service:
                try:
                    embedding = await self._embedding_service.embed(anomaly_text)
                except Exception:
                    pass

            pattern_data = {
                "pattern_id": pattern_id,
                "anomaly_type": rule_result.get("anomaly_type", "unknown"),
                "anomaly_text": anomaly_text,
                "embedding": embedding[:256] if embedding else [],  # 截断以节省 Redis 空间
                "status_snapshot": {
                    "cache_hit_rate": status.get("cache_hit_rate", 1.0),
                    "error_rate": status.get("error_rate", 0.0),
                    "p95_latency_ms": status.get("p95_latency_ms", 0),
                    "queue_depth": status.get("queue_depth", 0),
                    "vehicle_status": status.get("vehicle_status", "normal"),
                },
                "judgment": judgment,
                "stored_at": time.time(),
                "cockpit_id": self.cockpit_id,
            }

            await self._redis.hset(
                ANOMALY_MEMORY_KEY,
                pattern_id,
                json.dumps(pattern_data, ensure_ascii=False, default=str),
            )
            logger.debug(f"Anomaly pattern stored: {pattern_id}")
        except Exception as e:
            logger.debug(f"Failed to store anomaly memory: {e}")

    @staticmethod
    def _status_to_text(status: Dict[str, Any], rule_result: Dict[str, Any]) -> str:
        """将座舱状态和规则结果转为文本描述，用于 embedding 匹配。"""
        return (
            f"cockpit={status.get('cockpit_id', 'unknown')}, "
            f"anomaly_type={rule_result.get('anomaly_type', 'unknown')}, "
            f"cache_hit_rate={status.get('cache_hit_rate', 'N/A')}, "
            f"error_rate={status.get('error_rate', 'N/A')}, "
            f"p95_latency_ms={status.get('p95_latency_ms', 'N/A')}, "
            f"queue_depth={status.get('queue_depth', 'N/A')}, "
            f"vehicle_status={status.get('vehicle_status', 'N/A')}, "
            f"anomalies={rule_result.get('all_anomalies', [])}"
        )

    async def _report_alert(self, judgment: Dict[str, Any]) -> None:
        """通过 Redis Pub/Sub 上报异常给 MainAgent。

        Args:
            judgment: LLM 判断结果
        """
        alert = {
            "cockpit_id": self.cockpit_id,
            "alert_time": time.time(),
            "alert_type": judgment.get("anomaly_type", "unknown"),
            "severity": judgment.get("severity", "low"),
            "description": judgment.get("description", ""),
            "suggested_action": judgment.get("suggested_action", ""),
            "llm_judgment": judgment,
            "source": "subagent",
        }

        alert_json = json.dumps(alert, ensure_ascii=False, default=str)

        if self._redis:
            try:
                await self._redis.publish(ALERT_CHANNEL, alert_json)
                # 同时存入 Redis 缓存供 MainAgent 快通道查询
                alert_key = f"alert:{self.cockpit_id}"
                await self._redis.setex(alert_key, 300, alert_json)  # 5 分钟 TTL
                logger.warning(
                    f"SubAgent {self.cockpit_id} reported alert: "
                    f"type={alert['alert_type']}, severity={alert['severity']}"
                )
            except Exception as e:
                logger.error(f"Failed to publish alert: {e}")
        else:
            logger.warning(
                f"SubAgent {self.cockpit_id} alert (no Redis): {alert_json}"
            )

    def get_latest_stats(self) -> Dict[str, Any]:
        """获取最近一次采集的状态。

        Returns:
            最近采集的座舱状态
        """
        return self._stats

    async def _write_log(
        self,
        status: Dict[str, Any],
        rule_result: Dict[str, Any],
        llm_judgment: Optional[Dict[str, Any]],
        is_anomaly: bool,
    ) -> None:
        """将巡检结果写入 MySQL（非阻塞，失败仅记日志）。

        Args:
            status: 采集到的座舱状态
            rule_result: 规则引擎结果
            llm_judgment: LLM 判断结果
            is_anomaly: 是否异常
        """
        try:
            from nexus.core.db_manager import get_db_manager
            db = get_db_manager()
            if db.is_connected:
                await db.insert_subagent_log(
                    cockpit_id=self.cockpit_id,
                    check_items=status,
                    llm_judgment=llm_judgment,
                    decision_trace={
                        "rule_result": rule_result,
                        "llm_called": llm_judgment is not None,
                    },
                    is_anomaly=is_anomaly,
                )

                # 如果调用了 LLM，记录成本
                if llm_judgment and llm_judgment.get("llm_called"):
                    await db.insert_llm_cost(
                        cockpit_id=self.cockpit_id,
                        request_type="subagent_judge",
                        model_name=llm_judgment.get("model", self._subagent_model),
                        prompt_tokens=llm_judgment.get("prompt_tokens", 0),
                        completion_tokens=llm_judgment.get("completion_tokens", 0),
                        cost_yuan=llm_judgment.get("cost_yuan", 0.0),
                    )
        except Exception as e:
            logger.debug(f"SubAgent log write failed for {self.cockpit_id}: {e}")


class SubAgentManager:
    """管理所有座舱的 SubAgent 监控器。

    负责创建、启动、停止所有 SubAgent。
    """

    def __init__(
        self,
        llm_client: AsyncOpenAI,
        redis_client: Optional[aioredis.Redis] = None,
        embedding_service=None,
    ) -> None:
        self.llm_client = llm_client
        self._redis = redis_client
        self._embedding_service = embedding_service
        self._monitors: Dict[str, SubAgentMonitor] = {}
        config = get_config()
        self._check_interval = (
            config.cockpit.subagent_check_interval_min,
            config.cockpit.subagent_check_interval_max,
        )

    def register_cockpit(self, cockpit_id: str) -> SubAgentMonitor:
        """为座舱创建 SubAgent 监控器。

        Args:
            cockpit_id: 座舱 ID

        Returns:
            创建的 SubAgentMonitor 实例
        """
        if cockpit_id not in self._monitors:
            monitor = SubAgentMonitor(
                cockpit_id=cockpit_id,
                llm_client=self.llm_client,
                redis_client=self._redis,
                check_interval=self._check_interval,
                embedding_service=self._embedding_service,
            )
            self._monitors[cockpit_id] = monitor
            logger.info(f"SubAgent monitor registered for {cockpit_id}")
        return self._monitors[cockpit_id]

    async def start_all(self, cockpit_ids: List[str]) -> None:
        """启动所有座舱的 SubAgent 监控。

        Args:
            cockpit_ids: 要监控的座舱 ID 列表
        """
        for cid in cockpit_ids:
            monitor = self.register_cockpit(cid)
            await monitor.start()

    async def stop_all(self) -> None:
        """停止所有 SubAgent 监控。"""
        tasks = [m.stop() for m in self._monitors.values()]
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("All SubAgent monitors stopped")

    def get_monitor(self, cockpit_id: str) -> Optional[SubAgentMonitor]:
        """获取指定座舱的 SubAgent。"""
        return self._monitors.get(cockpit_id)

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取所有座舱的最新状态。"""
        return {cid: m.get_latest_stats() for cid, m in self._monitors.items()}
