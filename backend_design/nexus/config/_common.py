# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Config Common — 配置模块共享常量与工具函数

所有子配置文件都依赖此模块中的路径常量和 _resolve_path() 函数。
将公共部分独立到此文件，避免子配置文件与 __init__.py 之间的循环导入。

路径说明:
  本文件位于 backend_design/nexus/config/_common.py
  项目根目录 (NexusCockpit/) 在此文件向上四级
"""

from __future__ import annotations

import logging
import os

# ============================================================
# 路径常量 — 自动定位项目根目录
# ============================================================
# _common.py 的位置: NexusCockpit/backend_design/nexus/config/_common.py
# 向上四级 (__file__ → config/ → nexus/ → backend_design/ → NexusCockpit/) 得到项目根目录
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

# ============================================================
# 环境文件加载策略
# ============================================================
# 加载逻辑:
#   1. .env.local 存在 → 加载 .env.local (覆盖 .env 默认值, 含个人密钥)
#   2. .env.local 不存在 → 加载 .env (开箱即用的默认配置)
#
# .env = 统一默认配置 (提交 GitHub, 开发者克隆即可运行)
# .env.local = 本机覆盖配置 (不提交, 含个人 API Key 等敏感信息)

_APP_ENV = os.getenv("APP_ENV", "local").strip().lower()
_ENV_LOCAL = os.path.join(_PROJECT_ROOT, ".env.local")
_ENV_DEFAULT = os.path.join(_PROJECT_ROOT, ".env")

if os.path.exists(_ENV_LOCAL):
    _ENV_FILE = _ENV_LOCAL
else:
    _ENV_FILE = _ENV_DEFAULT

# 显式加载环境文件到 os.environ，确保 .env.local 中的值不会被 .env 中的空值覆盖
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(_ENV_FILE, override=True)
except ImportError:
    pass


def _resolve_path(relative_path: str) -> str:
    """将相对路径 (如 ./models/asr) 解析为基于项目根目录的绝对路径。

    为什么需要这个函数:
        项目可能在任意目录下被启动 (如从 backend_design/ 启动或从根目录启动)，
        使用相对路径会因工作目录不同而失效。此函数确保所有路径都基于项目根目录。

    Args:
        relative_path: 以 ./ 开头的相对路径，或已经是绝对路径。

    Returns:
        解析后的绝对路径字符串。
    """
    # 如果已经是绝对路径 (如 C:\...)，直接返回
    if os.path.isabs(relative_path):
        return relative_path
    # 去掉开头的 ./ 前缀，然后拼接到项目根目录
    clean = relative_path.lstrip("./") if relative_path.startswith("./") else relative_path
    return os.path.join(_PROJECT_ROOT, clean)
