"""
Mock Vehicle Bus — 模拟车控总线
用于开发环境联调，维护完整的车辆状态模型
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from nexus.core.logger import get_logger
from nexus.vehicle.base import BaseVehicleAdapter, VehicleCommandResult

logger = get_logger(__name__)


class MockVehicleBus(BaseVehicleAdapter):
    """模拟车控总线"""

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
        # 内置播放列表 (10 首热门歌曲)
        self._playlist = [
            "爱错 - 王力宏",
            "晴天 - 周杰伦",
            "起风了 - 买辣椒也用券",
            "夜曲 - 周杰伦",
            "稻香 - 周杰伦",
            "光年之外 - 邓紫棋",
            "说好不哭 - 周杰伦",
            "圈圈叉叉 - 蔡依林",
            "告白气球 - 周杰伦",
            "年少有为 - 李荣浩",
        ]
        self._track_index = 0
        self.climate: Dict[str, Any] = {
            "temperature": 22,
            "fan_speed": 3,
            "mode": "auto",
            "power": True,
        }
        self.windows: Dict[str, int] = {
            "all": 0,
            "front_left": 0,
            "front_right": 0,
            "rear_left": 0,
            "rear_right": 0,
            "sunroof": 0,
        }
        self.seats: Dict[str, Dict[str, Any]] = {
            "driver": {"heat": 0, "cool": 0, "massage": False, "position": "neutral"},
            "passenger": {"heat": 0, "cool": 0, "massage": False, "position": "neutral"},
        }
        self.media: Dict[str, Any] = {
            "playing": False,
            "volume": 18,
            "source": "local",
            "track": self._playlist[0],
            "playlist": list(self._playlist),
            "track_index": 0,
        }
        self.navigation: Dict[str, Any] = {
            "destination": "",
            "waypoint": "",
            "mode": "drive",
        }
        self.status: Dict[str, Any] = {
            "tire_pressure": "normal",
            "range_km": 420,
            "fuel_percent": 58,
            "battery_percent": 76,
            "maintenance": "normal",
        }
        logger.info("MockVehicleBus initialized")

    def vehicle_climate(
        self,
        op: str = "status",
        target_temp: Optional[int] = None,
        delta: Optional[int] = None,
        fan_speed: Optional[int] = None,
        mode: Optional[str] = None,
    ) -> VehicleCommandResult:
        if mode:
            self.climate["mode"] = mode
        if fan_speed is not None:
            self.climate["fan_speed"] = max(1, min(7, int(fan_speed)))
        if target_temp is not None:
            self.climate["temperature"] = max(16, min(30, int(target_temp)))
        elif delta:
            self.climate["temperature"] = max(16, min(30, self.climate["temperature"] + int(delta)))
        else:
            if op in ("temp_up", "up"):
                self.climate["temperature"] = min(30, self.climate["temperature"] + 1)
            elif op in ("temp_down", "down"):
                self.climate["temperature"] = max(16, self.climate["temperature"] - 1)

        return VehicleCommandResult(
            success=True,
            message=f"已将空调设置为 {self.climate['temperature']} 度，风量 {self.climate['fan_speed']} 档。",
            data={"climate": dict(self.climate)},
        )

    def vehicle_window(
        self, op: str = "status", position: str = "all", percent: Optional[int] = None
    ) -> VehicleCommandResult:
        if op in ("status", "query", "query_status"):
            return VehicleCommandResult(
                success=True,
                message=f"车窗状态：{self.windows}",
                data={"windows": dict(self.windows)},
            )

        if op in ("set_position", "set", "move_to"):
            value = max(0, min(100, int(percent))) if percent is not None else self.windows.get(position, self.windows["all"])
        else:
            value = 0 if op in ("close", "down", "lower") else 100
            if percent is not None:
                value = max(0, min(100, int(percent)))

        if position == "all":
            for key in self.windows:
                self.windows[key] = value
        elif position in self.windows:
            self.windows[position] = value
        else:
            position = "all"
            for key in self.windows:
                self.windows[key] = value

        return VehicleCommandResult(
            success=True,
            message=f"已将{position}车窗调整到 {value}%。",
            data={"windows": dict(self.windows)},
        )

    def vehicle_seat(
        self,
        op: str = "status",
        position: str = "driver",
        level: Optional[int] = None,
        direction: Optional[str] = None,
    ) -> VehicleCommandResult:
        seat = self.seats.get(position, self.seats["driver"])
        if op in ("heat_on", "heat", "seat_heat"):
            seat["heat"] = max(1, int(level or 1))
            seat["cool"] = 0
        elif op in ("heat_off", "heat_stop"):
            seat["heat"] = 0
        elif op in ("cool_on", "cool", "seat_cool"):
            seat["cool"] = max(1, int(level or 1))
            seat["heat"] = 0
        elif op in ("cool_off", "cool_stop"):
            seat["cool"] = 0
        elif op in ("massage_on", "massage"):
            seat["massage"] = True
        elif op in ("massage_off", "stop_massage"):
            seat["massage"] = False
        elif op in ("forward", "backward", "forward_adjust", "back_adjust"):
            seat["position"] = direction or op

        self.seats[position] = seat
        return VehicleCommandResult(
            success=True,
            message=f"已调整{position}座椅状态。",
            data={"seats": dict(self.seats)},
        )

    def vehicle_navigation(
        self, destination: str, waypoint: str = "", mode: str = "drive"
    ) -> VehicleCommandResult:
        self.navigation["destination"] = destination
        self.navigation["waypoint"] = waypoint
        self.navigation["mode"] = mode
        return VehicleCommandResult(
            success=True,
            message=f"已开始导航到 {destination}。",
            data={"navigation": dict(self.navigation)},
        )

    def vehicle_media(
        self,
        op: str = "play",
        source: Optional[str] = None,
        track: Optional[str] = None,
        volume: Optional[int] = None,
    ) -> VehicleCommandResult:
        if op in ("set_volume", "volume"):
            if volume is not None:
                self.media["volume"] = max(0, min(30, int(volume)))
            return VehicleCommandResult(
                success=True,
                message=f"已将音量调整到 {self.media['volume']}。",
                data={"media": dict(self.media)},
            )

        if op in ("set_source",):
            if source:
                self.media["source"] = source
            return VehicleCommandResult(
                success=True,
                message=f"已将媒体来源切换为 {self.media['source']}。",
                data={"media": dict(self.media)},
            )

        if op in ("status", "query", "query_status"):
            return VehicleCommandResult(
                success=True,
                message=f"媒体状态：{self.media}",
                data={"media": dict(self.media)},
            )

        if source:
            self.media["source"] = source
        if track:
            self.media["track"] = track
        if volume is not None:
            self.media["volume"] = max(0, min(30, int(volume)))

        if op in ("play", "resume"):
            self.media["playing"] = True
            if not self.media.get("track"):
                self.media["track"] = self._playlist[self._track_index]
        elif op in ("pause", "stop"):
            self.media["playing"] = False
        elif op in ("next", "next_track"):
            self._track_index = (self._track_index + 1) % len(self._playlist)
            self.media["track"] = self._playlist[self._track_index]
            self.media["track_index"] = self._track_index
            self.media["playing"] = True
        elif op in ("prev", "previous_track"):
            self._track_index = (self._track_index - 1) % len(self._playlist)
            self.media["track"] = self._playlist[self._track_index]
            self.media["track_index"] = self._track_index
            self.media["playing"] = True
        elif op in ("play_track", "select_track"):
            if track is not None:
                # 按名称或索引选择歌曲
                if isinstance(track, int) or (isinstance(track, str) and track.isdigit()):
                    idx = int(track)
                    if 0 <= idx < len(self._playlist):
                        self._track_index = idx
                else:
                    # 按名称查找
                    for i, t in enumerate(self._playlist):
                        if track in t:
                            self._track_index = i
                            break
                self.media["track"] = self._playlist[self._track_index]
                self.media["track_index"] = self._track_index
                self.media["playing"] = True

        self.media["playlist"] = list(self._playlist)

        return VehicleCommandResult(
            success=True,
            message=f"已执行媒体操作 {op}。当前音量 {self.media['volume']}。",
            data={"media": dict(self.media)},
        )

    def vehicle_status(self) -> VehicleCommandResult:
        """返回完整车辆状态，包含所有子系统数据。"""
        summary = (
            f"胎压{self.status['tire_pressure']}，续航{self.status['range_km']}公里，"
            f"油量{self.status['fuel_percent']}%，电量{self.status['battery_percent']}%，"
            f"保养状态{self.status['maintenance']}。"
        )
        return VehicleCommandResult(
            success=True,
            message=summary,
            data={
                "climate": dict(self.climate),
                "windows": dict(self.windows),
                "seats": dict(self.seats),
                "media": dict(self.media),
                "navigation": dict(self.navigation),
                "status": dict(self.status),
            },
        )

    def invoke_command(self, command_name: str, payload: Dict[str, Any]) -> VehicleCommandResult:
        """统一命令入口，支持别名映射"""
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
