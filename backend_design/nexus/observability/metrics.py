# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Prometheus Metrics — 指标采集
使用 prometheus_client 暴露 /metrics 端点
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, Info

# --- 应用信息 ---
APP_INFO = Info(
    "nexus_cockpit",
    "NexusCockpit Vehicle Voice Agent",
)

# --- 请求指标 ---
REQUEST_COUNT = Counter(
    "nexus_requests_total",
    "Total requests processed",
    ["endpoint", "method", "status"],
)

REQUEST_LATENCY = Histogram(
    "nexus_request_latency_seconds",
    "Request latency in seconds",
    ["endpoint"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
)

# --- Agent 指标 ---
AGENT_INVOCATIONS = Counter(
    "nexus_agent_invocations_total",
    "Total agent invocations",
    ["agent_name", "status"],
)

AGENT_LATENCY = Histogram(
    "nexus_agent_latency_seconds",
    "Agent node latency in seconds",
    ["agent_name"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)

# --- 技能指标 ---
SKILL_EXECUTIONS = Counter(
    "nexus_skill_executions_total",
    "Total skill executions",
    ["skill_name", "status"],
)

# --- 缓存指标 ---
CACHE_HITS = Counter(
    "nexus_cache_hits_total",
    "Total cache hits",
)

CACHE_MISSES = Counter(
    "nexus_cache_misses_total",
    "Total cache misses",
)

# --- RAG 指标 ---
RAG_RETRIEVALS = Counter(
    "nexus_rag_retrievals_total",
    "Total RAG retrievals",
    ["source"],  # vector, graph, fusion
)

RAG_LATENCY = Histogram(
    "nexus_rag_latency_seconds",
    "RAG retrieval latency in seconds",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)

# --- LLM 指标 ---
LLM_CALLS = Counter(
    "nexus_llm_calls_total",
    "Total LLM API calls",
    ["model", "status"],
)

LLM_LATENCY = Histogram(
    "nexus_llm_latency_seconds",
    "LLM API call latency in seconds",
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
)

# --- 系统指标 ---
ACTIVE_CONNECTIONS = Gauge(
    "nexus_active_connections",
    "Active WebSocket connections",
)

ACTIVE_USERS = Gauge(
    "nexus_active_users",
    "Active unique users in the last 5 minutes",
)


def init_metrics() -> None:
    """初始化指标"""
    APP_INFO.info(
        {
            "version": "1.0.0",
            "service": "nexus-cockpit",
            "description": "Enterprise Vehicle Voice Agent",
        }
    )
