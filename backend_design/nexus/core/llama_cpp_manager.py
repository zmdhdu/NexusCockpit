# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
LlamaCpp Process Manager — llama.cpp 子进程生命周期管理

将 llama-server 作为 Python 服务的子进程运行，实现:
  - 启动时自动拉起 llama-server
  - 健康检查 + 崩溃自动重启
  - 优雅停止（SIGTERM → 等待 → SIGKILL）
  - GPU/CPU 自动检测与参数选择

依赖: 需预编译 llama.cpp 或下载预编译二进制
  - Windows: llama-server.exe
  - Linux: llama-server
  - 路径: ./models/llm/llama.cpp/llama-server (或通过 .env LLAMA_CPP_BINARY 配置)
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
from typing import Any

import httpx

from nexus.config import get_config
from nexus.core.logger import get_logger

logger = get_logger(__name__)

# 项目根目录: backend_design/nexus/core/llama_cpp_manager.py → 向上四级
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


class LlamaCppProcessManager:
    """llama.cpp 子进程管理器。

    在 Python 服务启动时自动拉起 llama-server 子进程，
    提供健康检查、崩溃重启、优雅停止等生命周期管理。

    Attributes:
        _process: 子进程 Popen 对象
        _port: llama-server 监听端口
        _binary_path: llama-server 二进制路径
        _model_path: GGUF 模型文件路径
        _max_restarts: 最大重启次数
        _restart_count: 当前重启计数
        _health_check_url: 健康检查 URL
        _shutdown_event: 停止信号
    """

    def __init__(self):
        self._binary_path = os.getenv(
            "LLAMA_CPP_BINARY",
            self._default_binary_path(),
        )
        self._model_path = os.getenv(
            "LLAMA_CPP_MODEL_PATH",
            os.path.join(
                _PROJECT_ROOT,
                "models", "llm", "qwen", "Qwen3.5-4B-Q4_K_M.gguf",
            ),
        )
        self._port = int(os.getenv("LLAMA_CPP_PORT", "8082"))
        self._host = "127.0.0.1"
        self._ctx_size = int(os.getenv("LLAMA_CPP_CTX_SIZE", "4096"))
        self._gpu_layers = int(os.getenv("LLAMA_CPP_GPU_LAYERS", "0"))
        self._threads = int(os.getenv("LLAMA_CPP_THREADS", str(os.cpu_count() or 4)))
        self._max_restarts = 3
        self._restart_count = 0
        self._process: subprocess.Popen | None = None
        self._health_check_url = f"http://{self._host}:{self._port}/health"
        self._shutdown_event = asyncio.Event()

    @staticmethod
    def _default_binary_path() -> str:
        """根据操作系统返回默认二进制路径。"""
        if sys.platform == "win32":
            return os.path.join(_PROJECT_ROOT, "models", "llm", "llama.cpp", "llama-server.exe")
        return os.path.join(_PROJECT_ROOT, "models", "llm", "llama.cpp", "llama-server")

    async def start(self) -> bool:
        """启动 llama-server 子进程。

        Returns:
            True 表示启动成功且健康检查通过
        """
        if not os.path.exists(self._binary_path):
            logger.warning(
                f"llama-server binary not found at {self._binary_path}, "
                f"subprocess integration disabled"
            )
            return False

        if not os.path.exists(self._model_path):
            logger.warning(
                f"GGUF model not found at {self._model_path}, "
                f"subprocess integration disabled"
            )
            return False

        logger.info(
            f"Starting llama-server: binary={self._binary_path}, "
            f"model={self._model_path}, port={self._port}, "
            f"ctx={self._ctx_size}, gpu_layers={self._gpu_layers}, "
            f"threads={self._threads}"
        )

        cmd = [
            self._binary_path,
            "--model", self._model_path,
            "--host", self._host,
            "--port", str(self._port),
            "--ctx-size", str(self._ctx_size),
            "--threads", str(self._threads),
        ]

        # GPU 层数参数（-1 表示全部 GPU，0 表示纯 CPU）
        if self._gpu_layers != 0:
            cmd.extend(["--gpu-layers", str(self._gpu_layers)])

        # 高性能参数
        cmd.extend([
            "--parallel", "4",       # 支持多专家并行请求
            "--cont-batching",       # 连续批处理
        ])

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            logger.info(f"llama-server started (PID={self._process.pid})")

            # 等待健康检查通过（最多 60 秒）
            if await self._wait_for_health(timeout=60):
                logger.info("llama-server healthy, ready to serve")
                self._restart_count = 0
                # 启动后台监控任务
                asyncio.create_task(self._monitor())
                return True
            else:
                logger.error("llama-server failed health check within 60s")
                await self.stop()
                return False

        except Exception as e:
            logger.error(f"Failed to start llama-server: {e}")
            return False

    async def _wait_for_health(self, timeout: float = 60.0) -> bool:
        """等待 llama-server 健康检查通过。"""
        async with httpx.AsyncClient() as client:
            for _ in range(int(timeout / 2)):
                try:
                    resp = await client.get(self._health_check_url, timeout=2.0)
                    if resp.status_code == 200:
                        return True
                except Exception:
                    pass
                await asyncio.sleep(2)
        return False

    async def _monitor(self) -> None:
        """后台监控子进程状态，崩溃时自动重启。"""
        while not self._shutdown_event.is_set():
            if self._process and self._process.poll() is not None:
                # 子进程已退出
                exit_code = self._process.returncode
                logger.error(f"llama-server exited (code={exit_code})")

                if self._restart_count < self._max_restarts:
                    self._restart_count += 1
                    logger.info(
                        f"Restarting llama-server "
                        f"(attempt {self._restart_count}/{self._max_restarts})"
                    )
                    await asyncio.sleep(3)  # 等待 3 秒后重启
                    await self.start()
                else:
                    logger.error(
                        "llama-server max restart attempts reached, "
                        "falling back to cloud LLM if available"
                    )
                    break

            await asyncio.sleep(5)  # 每 5 秒检查一次

    async def stop(self) -> None:
        """优雅停止 llama-server 子进程。"""
        self._shutdown_event.set()

        if not self._process:
            return

        logger.info("Stopping llama-server...")

        # 先尝试 SIGTERM
        try:
            if sys.platform == "win32":
                self._process.terminate()
            else:
                self._process.send_signal(signal.SIGTERM)

            # 等待最多 10 秒
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                # SIGTERM 超时，强制 SIGKILL
                logger.warning("llama-server did not stop gracefully, force killing")
                self._process.kill()
                self._process.wait(timeout=5)

            logger.info("llama-server stopped")
        except Exception as e:
            logger.error(f"Error stopping llama-server: {e}")
            if self._process:
                self._process.kill()
        finally:
            self._process = None

    @property
    def is_running(self) -> bool:
        """子进程是否正在运行。"""
        return self._process is not None and self._process.poll() is None

    @property
    def base_url(self) -> str:
        """OpenAI 兼容 API 的 base URL。"""
        return f"http://{self._host}:{self._port}/v1"
