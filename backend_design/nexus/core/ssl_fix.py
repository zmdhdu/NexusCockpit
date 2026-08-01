# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
SSL Fix — 修复 conda-forge Python 在 Windows 上的 SSL 证书库解析 bug。

问题: ssl._load_windows_store_certs() 调用 load_verify_locations(cadata=certs)
      时抛出 SSLError: [ASN1: NOT_ENOUGH_DATA] not enough data (_ssl.c:4030)
      导致 aiohttp / requests / pip 等库无法创建 SSL 上下文。

修复: 拦截 _load_windows_store_certs 的 SSLError，静默跳过 Windows 证书库，
      改用 certifi 提供的 CA 证书包（通过 SSL_CERT_FILE 环境变量或直接加载）。

用法: 在 sitecustomize.py 或项目入口处 import nexus.core.ssl_fix
"""

from __future__ import annotations

import os
import ssl as _ssl
import sys

# 仅在 Windows + conda 环境下应用 SSL 补丁
# 原因: conda-forge Python 在 Windows 上的 ssl._load_windows_store_certs() 存在 ASN1 解析 bug
# 非 Windows 或非 conda 环境无需此补丁
_IS_WINDOWS = sys.platform == "win32"
_IS_CONDA = os.path.exists(os.path.join(sys.prefix, "conda-meta"))


def apply_ssl_fix() -> None:
    """Patch ssl._SSLContext._load_windows_store_certs to catch SSLError.

    仅在 Windows + conda 环境下生效，避免影响其他环境的正常 SSL 行为。
    """

    if not (_IS_WINDOWS and _IS_CONDA):
        # 非 Windows 或非 conda 环境，无需 SSL 补丁
        return

    import logging
    logging.getLogger(__name__).info(
        "Applying SSL fix: Windows + conda environment detected, "
        "patching ssl._SSLContext._load_windows_store_certs to handle ASN1 parse errors"
    )

    _original = _ssl._SSLContext._load_windows_store_certs

    def _patched(self, storename, purpose):  # type: ignore[no-untyped-def]
        try:
            return _original(self, storename, purpose)
        except _ssl.SSLError:
            # Windows 证书库 ASN1 解析失败，静默跳过
            # 后续由 certifi / SSL_CERT_FILE 提供 CA 证书
            return 0

    _ssl._SSLContext._load_windows_store_certs = _patched  # type: ignore[method-assign]

    # 确保使用 certifi 作为 CA 证书来源
    try:
        import certifi

        ca_path = certifi.where()
        os.environ.setdefault("SSL_CERT_FILE", ca_path)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", ca_path)
        os.environ.setdefault("CURL_CA_BUNDLE", ca_path)
    except ImportError:
        pass


# 模块导入时自动应用修复
apply_ssl_fix()
