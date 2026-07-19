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

    显式为 uvicorn/uvicorn.access logger 添加 FileHandler，
    确保 uvicorn 的终端输出（如 "INFO: 127.0.0.1:..." 访问日志）也写入文件。
    """
    config = get_config()
    # 将字符串日志级别 (如 "INFO") 转为 logging 常量 (如 logging.INFO)
    log_level = getattr(logging, config.server.log_level.upper(), logging.INFO)

    # 日志文件输出 - 写入 NexusCockpit/logs/backend_logs/ 文件夹
    # logger.py 位于 backend_design/nexus/core/logger.py，需上溯 4 级到项目根目录
    import os
    from datetime import datetime
    _project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    log_dir = os.path.join(_project_root, "logs", "backend_logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"backend_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

    # 创建共享的 FileHandler，供 root logger 和 uvicorn logger 共用
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(log_level)
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))

    # 标准 logging 配置 (同时输出到控制台和文件)
    logging.basicConfig(
        handlers=[console_handler, file_handler],
        level=log_level,
        force=True,
    )

    # 显式为 uvicorn 的 logger 添加 FileHandler
    # uvicorn 启动时会用自己的 dictConfig 覆盖 root logger 的 handlers，
    # 导致 "INFO: 127.0.0.1:..." 等访问日志只输出到终端，不写入文件。
    # 这里在 setup_logging 阶段为 uvicorn logger 添加共享的 FileHandler。
    for uvicorn_logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uv_logger = logging.getLogger(uvicorn_logger_name)
        # 检查是否已经有 FileHandler（避免重复添加）
        has_file_handler = any(
            isinstance(h, logging.FileHandler) for h in uv_logger.handlers
        )
        if not has_file_handler:
            uv_logger.addHandler(file_handler)
        uv_logger.setLevel(log_level)

    # 将日志文件路径保存到全局变量，供 main.py 读取并打印
    global _current_log_file
    _current_log_file = log_file

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


# 保存当前日志文件路径，供外部读取
_current_log_file: str = ""


def get_log_file_path() -> str:
    """获取当前日志文件路径。

    Returns:
        当前日志文件路径，如果未初始化则返回空字符串
    """
    return _current_log_file


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
