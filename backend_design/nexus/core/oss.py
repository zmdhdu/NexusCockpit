# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
OSS Storage — 阿里云对象存储服务封装
用于上传/下载音频文件、模型文件、用户数据等
"""

from __future__ import annotations

import os
from typing import Optional

from nexus.config import get_config
from nexus.core.logger import get_logger

logger = get_logger(__name__)


class OSSStorage:
    """
    阿里云 OSS 对象存储服务
    封装 oss2 SDK，提供文件上传/下载/删除/签名 URL 功能
    """

    def __init__(self):
        self.config = get_config().oss
        self._bucket = None
        self._loaded = False

    def connect(self) -> None:
        """初始化 OSS 连接"""
        if not self.config.enabled:
            logger.warning("OSS not configured, storage disabled")
            return

        try:
            import oss2

            auth = oss2.Auth(self.config.access_key, self.config.secret_key)
            self._bucket = oss2.Bucket(
                auth, self.config.endpoint, self.config.bucket_name
            )
            # 测试连接
            info = self._bucket.get_bucket_info()
            self._loaded = True
            logger.info(
                f"OSS connected: bucket={info.name}, "
                f"region={info.location}, "
                f"public_url={self.config.public_base_url}"
            )
        except ImportError:
            logger.warning("oss2 not installed, OSS storage disabled")
        except Exception as e:
            logger.error(f"OSS connection failed: {e}")

    @property
    def is_available(self) -> bool:
        return self._loaded and self._bucket is not None

    def upload_file(
        self,
        local_path: str,
        oss_key: str,
        public_read: bool = True,
    ) -> Optional[str]:
        """
        上传本地文件到 OSS

        Args:
            local_path: 本地文件路径
            oss_key: OSS 中的对象键 (如 "audio/user/test.wav")
            public_read: 是否公开读

        Returns:
            公开访问 URL，失败返回 None
        """
        if not self.is_available:
            logger.warning("OSS not available, upload skipped")
            return None

        try:
            import oss2

            headers = {}
            if public_read:
                headers[oss2.headers.OSS_OBJECT_ACL] = oss2.OBJECT_ACL_PUBLIC_READ

            self._bucket.put_object_from_file(
                oss_key, local_path, headers=headers
            )

            url = f"{self.config.public_base_url}/{oss_key}"
            logger.info(f"OSS upload success: {oss_key} → {url}")
            return url
        except Exception as e:
            logger.error(f"OSS upload failed: {e}")
            return None

    def upload_bytes(
        self,
        data: bytes,
        oss_key: str,
        public_read: bool = True,
    ) -> Optional[str]:
        """
        上传字节数据到 OSS

        Args:
            data: 字节数据
            oss_key: OSS 中的对象键
            public_read: 是否公开读

        Returns:
            公开访问 URL，失败返回 None
        """
        if not self.is_available:
            logger.warning("OSS not available, upload skipped")
            return None

        try:
            import oss2

            headers = {}
            if public_read:
                headers[oss2.headers.OSS_OBJECT_ACL] = oss2.OBJECT_ACL_PUBLIC_READ

            self._bucket.put_object(oss_key, data, headers=headers)

            url = f"{self.config.public_base_url}/{oss_key}"
            logger.info(f"OSS upload bytes success: {oss_key} → {url}")
            return url
        except Exception as e:
            logger.error(f"OSS upload bytes failed: {e}")
            return None

    def download_file(
        self,
        oss_key: str,
        local_path: str,
    ) -> bool:
        """
        从 OSS 下载文件到本地

        Args:
            oss_key: OSS 中的对象键
            local_path: 本地保存路径

        Returns:
            成功返回 True，失败返回 False
        """
        if not self.is_available:
            logger.warning("OSS not available, download skipped")
            return False

        try:
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            self._bucket.get_object_to_file(oss_key, local_path)
            logger.info(f"OSS download success: {oss_key} → {local_path}")
            return True
        except Exception as e:
            logger.error(f"OSS download failed: {e}")
            return False

    def delete(self, oss_key: str) -> bool:
        """删除 OSS 上的对象"""
        if not self.is_available:
            return False

        try:
            self._bucket.delete_object(oss_key)
            logger.info(f"OSS delete success: {oss_key}")
            return True
        except Exception as e:
            logger.error(f"OSS delete failed: {e}")
            return False

    def exists(self, oss_key: str) -> bool:
        """检查对象是否存在"""
        if not self.is_available:
            return False

        try:
            return self._bucket.object_exists(oss_key)
        except Exception as e:
            logger.error(f"OSS exists check failed: {e}")
            return False

    def get_public_url(self, oss_key: str) -> str:
        """获取对象的公开访问 URL"""
        return f"{self.config.public_base_url}/{oss_key}"

    def sign_url(
        self,
        oss_key: str,
        expires: int = 3600,
        method: str = "GET",
    ) -> Optional[str]:
        """
        生成临时签名 URL (用于私有文件)

        Args:
            oss_key: OSS 中的对象键
            expires: 过期时间 (秒)
            method: HTTP 方法

        Returns:
            签名 URL，失败返回 None
        """
        if not self.is_available:
            return None

        try:
            import oss2

            url = self._bucket.sign_url(method, oss_key, expires)
            return url
        except Exception as e:
            logger.error(f"OSS sign URL failed: {e}")
            return None

    def list_objects(
        self,
        prefix: str = "",
        max_keys: int = 100,
    ) -> list[dict]:
        """
        列举 OSS 对象

        Args:
            prefix: 对象键前缀
            max_keys: 最大返回数量

        Returns:
            对象列表 [{"key": ..., "size": ..., "last_modified": ...}]
        """
        if not self.is_available:
            return []

        try:
            results = []
            for obj in self._bucket.list_objects(
                prefix=prefix, max_keys=max_keys
            ).object_list:
                results.append(
                    {
                        "key": obj.key,
                        "size": obj.size,
                        "last_modified": obj.last_modified,
                    }
                )
            return results
        except Exception as e:
            logger.error(f"OSS list objects failed: {e}")
            return []
