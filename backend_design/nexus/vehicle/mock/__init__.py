# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Mock Vehicle Bus — 模拟车控总线 (Facade 门面模式)

替代原单文件 mock.py (~640 行)，按职责拆分为 7 个文件:
  vehicle/mock/__init__.py       本文件 — MockVehicleBus Facade + COMMAND_ALIASES + invoke_command
  vehicle/mock/climate_state.py  空调状态模型
  vehicle/mock/window_state.py   车窗状态模型
  vehicle/mock/seat_state.py     座椅状态模型
  vehicle/mock/navigation_state.py 导航状态模型 + IP 定位
  vehicle/mock/media_state.py    媒体状态模型 + 播放列表扫描
  vehicle/mock/status_state.py   车况状态模型

Facade 模式: MockVehicleBus 对外接口不变 (vehicle_climate / vehicle_window / ...)，
内部委托到各状态子模块的 handle() 方法。底层逻辑零修改，仅文件组织调整。
"""

from __future__ import annotations

from typing import Any

from nexus.core.logger import get_logger
from nexus.vehicle.base import BaseVehicleAdapter, VehicleCommandResult
from nexus.vehicle.mock.climate_state import ClimateState
from nexus.vehicle.mock.media_state import MediaState
from nexus.vehicle.mock.navigation_state import NavigationState
from nexus.vehicle.mock.seat_state import SeatState
from nexus.vehicle.mock.status_state import StatusState
from nexus.vehicle.mock.window_state import WindowState

logger = get_logger(__name__)

__all__ = ["MockVehicleBus"]


class MockVehicleBus(BaseVehicleAdapter):
    """模拟车控总线 (Facade 门面)。

    对外暴露与 BaseVehicleAdapter 相同的接口 (vehicle_climate, vehicle_window, ...)，
    内部委托到各状态子模块。各子模块独立管理自己的状态字典。
    """

    COMMAND_ALIASES = {
        "climate.set": "vehicle_climate",
        "climate.set_temperature": "vehicle_climate",
        "climate.adjust_temperature": "vehicle_climate",
        "climate.set_fan_speed": "vehicle_climate",
        "climate.set_mode": "vehicle_climate",
        "climate.query_status": "vehicle_climate",
        "window.set": "vehicle_window",
        "window.open": "vehicle_window",
        "window.close": "vehicle_window",
        "window.set_position": "vehicle_window",
        "window.query_status": "vehicle_window",
        "seat.set": "vehicle_seat",
        "seat.set_heating": "vehicle_seat",
        "seat.set_cooling": "vehicle_seat",
        "seat.set_massage": "vehicle_seat",
        "seat.stop_massage": "vehicle_seat",
        "seat.adjust_position": "vehicle_seat",
        "seat.query_status": "vehicle_seat",
        "navigation.route": "vehicle_navigation",
        "navigation.navigate_to": "vehicle_navigation",
        "navigation.set_waypoint": "vehicle_navigation",
        "navigation.cancel": "vehicle_navigation",
        "navigation.query_status": "vehicle_navigation",
        "media.control": "vehicle_media",
        "media.play": "vehicle_media",
        "media.pause": "vehicle_media",
        "media.next": "vehicle_media",
        "media.prev": "vehicle_media",
        "media.set_volume": "vehicle_media",
        "media.set_source": "vehicle_media",
        "media.query_status": "vehicle_media",
        "vehicle.status": "vehicle_status",
        "vehicle.query_status": "vehicle_status",
    }

    def __init__(self):
        # 各状态子模块独立初始化
        self._climate = ClimateState()
        self._window = WindowState()
        self._seat = SeatState()
        self._navigation = NavigationState()
        self._media = MediaState()
        self._status = StatusState()
        logger.info("MockVehicleBus initialized (Facade mode)")

    # ============================================================
    # 兼容性属性 — 对外暴露各子模块的状态字典 (与原 mock.py 接口一致)
    # ============================================================

    @property
    def climate(self) -> dict[str, Any]:
        return self._climate.climate

    @property
    def windows(self) -> dict[str, int]:
        return self._window.windows

    @property
    def seats(self) -> dict[str, dict[str, Any]]:
        return self._seat.seats

    @property
    def media(self) -> dict[str, Any]:
        return self._media.media

    @property
    def navigation(self) -> dict[str, Any]:
        return self._navigation.navigation

    @property
    def status(self) -> dict[str, Any]:
        return self._status.status

    # ============================================================
    # 车控方法 — 委托到各状态子模块
    # ============================================================

    def vehicle_climate(
        self,
        op: str = "status",
        target_temp: int | None = None,
        delta: int | None = None,
        fan_speed: int | None = None,
        mode: str | None = None,
    ) -> VehicleCommandResult:
        return self._climate.handle(op=op, target_temp=target_temp, delta=delta, fan_speed=fan_speed, mode=mode)

    def vehicle_window(
        self, op: str = "status", position: str = "all", percent: int | None = None
    ) -> VehicleCommandResult:
        return self._window.handle(op=op, position=position, percent=percent)

    def vehicle_seat(
        self,
        op: str = "status",
        position: str = "driver",
        level: int | None = None,
        direction: str | None = None,
    ) -> VehicleCommandResult:
        return self._seat.handle(op=op, position=position, level=level, direction=direction)

    def vehicle_navigation(
        self, destination: str = "", waypoint: str = "", mode: str = "drive",
        op: str = "navigate",
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> VehicleCommandResult:
        return self._navigation.handle(
            destination=destination, waypoint=waypoint, mode=mode, op=op,
            latitude=latitude, longitude=longitude,
        )

    def vehicle_media(
        self,
        op: str = "play",
        source: str | None = None,
        track: str | None = None,
        volume: int | None = None,
        play_mode: str | None = None,
    ) -> VehicleCommandResult:
        return self._media.handle(op=op, source=source, track=track, volume=volume, play_mode=play_mode)

    def vehicle_status(self, op: str = "status") -> VehicleCommandResult:
        """返回完整车辆状态，包含所有子系统数据。"""
        # 如果是查询位置，委托到导航子模块
        if op in ("location", "current_location", "where", "位置", "我在哪"):
            loc = self._navigation.navigation.get("current_location", "")
            if not loc:
                loc = self._navigation._fetch_ip_location()
            return VehicleCommandResult(
                success=True,
                message=f"您当前位于{loc}，朝{self._navigation.navigation.get('heading', '北')}方向行驶。",
                data={"navigation": dict(self._navigation.navigation)},
            )
        # 车况摘要
        result = self._status.handle(op=op)
        # 聚合所有子系统数据
        result.data = {
            "climate": dict(self._climate.climate),
            "windows": dict(self._window.windows),
            "seats": dict(self._seat.seats),
            "media": dict(self._media.media),
            "navigation": dict(self._navigation.navigation),
            "status": dict(self._status.status),
        }
        return result

    def invoke_command(self, command_name: str, payload: dict[str, Any]) -> VehicleCommandResult:
        """统一命令入口，支持别名映射。"""
        payload = payload or {}
        normalized_name = self.COMMAND_ALIASES.get(command_name, command_name)

        handler = getattr(self, normalized_name, None)
        if handler is None:
            return VehicleCommandResult(
                False,
                f"模拟车控不支持命令: {command_name}",
                error="command_not_found",
            )

        # 清理 None 值
        cleaned = {k: v for k, v in payload.items() if v is not None}
        try:
            return handler(**cleaned)
        except TypeError:
            # 参数不匹配，尝试直接调用
            return handler()
        except Exception as exc:
            return VehicleCommandResult(
                False,
                f"模拟车控命令执行失败: {exc}",
                error="invoke_failed",
            )
