# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Vehicle Bus Base — 车控适配层抽象基类

定义了车控适配器的统一接口。所有车控适配器 (Mock/HTTP/MCP) 都继承此类。
通过抽象基类实现多态，让技能层无需关心具体的车控通信方式。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VehicleCommandResult:
    """车控命令执行结果。

    Attributes:
        success: 是否执行成功
        message: 人类可读的结果描述
        data: 结构化结果数据 (如当前空调温度)
        error: 错误信息 (失败时)
    """
    success: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""


class BaseVehicleAdapter(ABC):
    """车控适配层抽象接口。

    子类必须实现所有 abstractmethod，包括:
        空调控制 / 车窗控制 / 座椅控制 / 导航 / 媒体 / 状态查询 / 通用命令调用
    """

    @abstractmethod
    def vehicle_climate(
        self,
        op: str = "status",
        target_temp: int | None = None,
        delta: int | None = None,
        fan_speed: int | None = None,
        mode: str | None = None,
    ) -> VehicleCommandResult:
        raise NotImplementedError

    @abstractmethod
    def vehicle_window(
        self, op: str = "status", position: str = "all", percent: int | None = None
    ) -> VehicleCommandResult:
        raise NotImplementedError

    @abstractmethod
    def vehicle_seat(
        self,
        op: str = "status",
        position: str = "driver",
        level: int | None = None,
        direction: str | None = None,
    ) -> VehicleCommandResult:
        raise NotImplementedError

    @abstractmethod
    def vehicle_navigation(
        self, destination: str, waypoint: str = "", mode: str = "drive"
    ) -> VehicleCommandResult:
        raise NotImplementedError

    @abstractmethod
    def vehicle_media(
        self,
        op: str = "play",
        source: str | None = None,
        track: str | None = None,
        volume: int | None = None,
    ) -> VehicleCommandResult:
        raise NotImplementedError

    @abstractmethod
    def vehicle_status(self) -> VehicleCommandResult:
        raise NotImplementedError

    @abstractmethod
    def invoke_command(self, command_name: str, payload: dict[str, Any]) -> VehicleCommandResult:
        raise NotImplementedError
