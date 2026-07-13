# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
结构化日志模块 (Structured Logging)

本模块基于 structlog 库，提供 JSON 格式的结构化日志输出。
相比传统 print()，结构化日志有以下优势:
  1. 每条日志自带时间戳、日志级别、模块名等元信息
  2. 生产环境输出 JSON 格式，方便 ELK/Loki 采集和搜索
  3. 开发环境输出彩色控制台格式，便于阅读调试
  4. 支持上下文绑定 (如绑定 request_id)，实现链路追踪

使用方式:
    from nexus.core.logger import get_logger
    logger = get_logger(__name__)
    logger.info("User logged in", user_id="12345")
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from nexus.config import get_config


def setup_logging() -> None:
    """初始化全局结构化日志配置。

    根据配置选择输出格式:
    - debug=True: 彩色控制台输出 (开发环境，方便阅读)
    - debug=False: JSON 格式输出 (生产环境，方便日志系统采集)
    """
    config = get_config()
    # 将字符串日志级别 (如 "INFO") 转为 logging 常量 (如 logging.INFO)
    log_level = getattr(logging, config.server.log_level.upper(), logging.INFO)

    # 标准 logging 配置 (供第三方库如 uvicorn/sqlalchemy 使用)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # structlog 配置 (供项目代码使用)
    structlog.configure(
        processors=[
            # 合并上下文变量 (如 request_id、user_id)
            structlog.contextvars.merge_contextvars,
            # 添加日志级别字段 (info/warning/error)
            structlog.processors.add_log_level,
            # 添加 ISO 格式时间戳
            structlog.processors.TimeStamper(fmt="iso"),
            # 添加调用栈信息 (便于调试)
            structlog.processors.StackInfoRenderer(),
            # 格式化异常信息
            structlog.processors.format_exc_info,
            # 输出格式: 生产环境用 JSON，开发环境用彩色控制台
            structlog.processors.JSONRenderer(ensure_ascii=False)
            if not config.server.debug
            else structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """获取结构化日志器。

    Args:
        name: 通常传入 __name__ (模块名)，用于标识日志来源。

    Returns:
        structlog 日志器实例
    """
    return structlog.get_logger(name)


def bind_context(**kwargs: Any) -> None:
    """绑定日志上下文变量。

    绑定后，后续所有日志都会自动携带这些字段。
    常用于绑定 request_id、user_id 等追踪信息。

    Example:
        bind_context(request_id="abc123", user_id="user_001")
        logger.info("Processing request")  # 日志中会包含 request_id 和 user_id
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_context() -> None:
    """清除所有日志上下文变量。

    通常在请求结束时调用，防止上下文泄漏到下一个请求。
    """
    structlog.contextvars.clear_contextvars()
