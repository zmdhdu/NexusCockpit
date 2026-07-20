# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Mock Vehicle Bus — 模拟车控总线
用于开发环境联调，维护完整的车辆状态模型
"""

from __future__ import annotations

import glob
import os
from typing import Any, Dict, List, Optional

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
        # 动态扫描音频目录，构建播放列表
        self._playlist: List[Dict[str, Any]] = self._scan_music_dir()
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
            "track": self._playlist[0] if self._playlist else None,  # 改为 dict
            "track_index": 0,
            "play_mode": "sequential",  # 播放模式: sequential(列表循环) / single(单曲循环) / shuffle(随机播放)
            "playlist": list(self._playlist),  # 完整的播放列表（含 url）
        }
        self.navigation: Dict[str, Any] = {
            "destination": "",
            "waypoint": "",
            "mode": "drive",
            "current_location": "",  # 初始为空，首次查询时动态获取
            "latitude": None,
            "longitude": None,
            "speed_kmh": 0,
            "heading": "北",
        }
        self.status: Dict[str, Any] = {
            "tire_pressure": "normal",
            "range_km": 420,
            "fuel_percent": 58,
            "battery_percent": 76,
            "maintenance": "normal",
        }
        logger.info("MockVehicleBus initialized")

    def _scan_music_dir(self) -> List[Dict[str, Any]]:
        """扫描 assets/audio/music/ 目录，构建播放列表。

        替代硬编码播放列表，动态扫描本地音频文件。

        支持的格式: .mp3, .wav

        Returns:
            播放列表，每项包含 title, filename, url, format
        """
        # 项目根目录: backend_design/nexus/vehicle/mock.py → 向上四级
        music_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            ))),
            "assets", "audio", "music"
        )
        supported_formats = {".mp3", ".wav"}
        playlist: List[Dict[str, Any]] = []

        if os.path.isdir(music_dir):
            for filepath in sorted(glob.glob(os.path.join(music_dir, "*"))):
                ext = os.path.splitext(filepath)[1].lower()
                if ext not in supported_formats:
                    continue
                filename = os.path.basename(filepath)
                title = self._parse_title(filename)
                playlist.append({
                    "title": title,
                    "filename": filename,
                    "url": f"/audio/music/{filename}",  # 前端可直接用
                    "format": ext.lstrip("."),
                })

        if not playlist:
            logger.warning(f"No audio files found in {music_dir}")
        else:
            logger.info(f"Loaded {len(playlist)} songs from {music_dir}")

        return playlist

    @staticmethod
    def _parse_title(filename: str) -> str:
        """从文件名解析歌曲标题。

        "王力宏-爱错.mp3" → "爱错 - 王力宏"
        "周杰伦 - 晴天.wav" → "晴天 - 周杰伦"（已规范则不变）
        """
        name = os.path.splitext(filename)[0]
        if " - " in name:
            parts = [p.strip() for p in name.split(" - ", 1)]
            return f"{parts[1]} - {parts[0]}" if len(parts) == 2 else name
        elif "-" in name:
            parts = [p.strip() for p in name.split("-", 1)]
            return f"{parts[1]} - {parts[0]}" if len(parts) == 2 else name
        return name

    def vehicle_climate(
        self,
        op: str = "status",
        target_temp: Optional[int] = None,
        delta: Optional[int] = None,
        fan_speed: Optional[int] = None,
        mode: Optional[str] = None,
    ) -> VehicleCommandResult:
        # 电源开关
        if op in ("power_on", "on", "open"):
            self.climate["power"] = True
            return VehicleCommandResult(
                success=True,
                message="空调已开启。",
                data={"climate": dict(self.climate)},
            )
        if op in ("power_off", "off", "close"):
            self.climate["power"] = False
            return VehicleCommandResult(
                success=True,
                message="空调已关闭。",
                data={"climate": dict(self.climate)},
            )

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
        self, destination: str = "", waypoint: str = "", mode: str = "drive",
        op: str = "navigate",
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> VehicleCommandResult:
        # 查询当前位置
        if op in ("location", "current_location", "where", "位置", "我在哪"):
            loc = self.navigation.get("current_location", "")
            # 只缓存成功获取的位置，失败时每次重试
            if not loc or "未知" in loc or "不可用" in loc:
                loc = self._fetch_ip_location(latitude, longitude)
            # 坐标降级时也算部分成功（至少有坐标）
            is_failure = "未知" in loc and "坐标" not in loc
            return VehicleCommandResult(
                success=not is_failure,
                message=f"您当前位于{loc}。" if not is_failure else f"{loc}。请尝试开启浏览器定位或稍后重试。",
                data={"navigation": dict(self.navigation)},
            )
        if destination:
            self.navigation["destination"] = destination
        self.navigation["waypoint"] = waypoint
        self.navigation["mode"] = mode
        return VehicleCommandResult(
            success=True,
            message=f"已开始导航到 {destination}。",
            data={"navigation": dict(self.navigation)},
        )

    def _fetch_ip_location(self, latitude: Optional[float] = None, longitude: Optional[float] = None) -> str:
        """通过 IP 或浏览器坐标获取当前位置。

        优先级:
            1. 浏览器 GPS 坐标 (latitude/longitude) → 逆地理编码
               1a. 高德地图 (Amap) — 国内服务，速度快
               1b. Nominatim (OpenStreetMap) — 国际备选
            2. IP 定位 — 多服务尝试
               2a. 高德 IP 定位 API — 国内服务，速度快
               2b. ip-api.com — 国际备选
            3. 降级：返回坐标字符串（仍存储坐标）

        注: IP 定位优先使用高德 IP API（国内速度快），ip-api.com 降为备选
        """
        # 无论逆地理编码是否成功，先存储坐标
        if latitude is not None and longitude is not None:
            self.navigation["latitude"] = latitude
            self.navigation["longitude"] = longitude

        # 1a. 优先使用高德地图逆地理编码（国内速度快，需配置 AMAP_KEY）
        if latitude is not None and longitude is not None:
            try:
                import httpx
                from nexus.config import get_config
                amap_key = get_config().amap.api_key
                if amap_key:
                    resp = httpx.get(
                        "https://restapi.amap.com/v3/geocode/regeo",
                        params={
                            "location": f"{longitude},{latitude}",
                            "key": amap_key,
                            "extensions": "base",
                            "output": "json",
                        },
                        timeout=3.0,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("status") == "1":
                            comp = data.get("regeocode", {}).get("formatted_address", "")
                            if comp:
                                self.navigation["current_location"] = comp
                                logger.info(f"Location updated via Amap: {comp}")
                                return comp
            except Exception as e:
                logger.warning(f"Amap reverse geocoding failed: {e}")

        # 1b. Nominatim (OpenStreetMap) — 国际备选
        if latitude is not None and longitude is not None:
            try:
                import httpx
                resp = httpx.get(
                    "https://nominatim.openstreetmap.org/reverse",
                    params={
                        "lat": latitude,
                        "lon": longitude,
                        "format": "json",
                        "accept-language": "zh-CN",
                    },
                    headers={"User-Agent": "NexusCockpit/2.1"},
                    timeout=3.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    addr = data.get("display_name", "")
                    if addr:
                        self.navigation["current_location"] = addr
                        logger.info(f"Location updated via GPS (Nominatim): {addr}")
                        return addr
            except Exception as e:
                logger.warning(f"GPS reverse geocoding (Nominatim) failed: {e}")

        # 2a. IP 定位 — 高德 IP 定位 API (国内服务，速度快)
        try:
            import httpx
            from nexus.config import get_config
            amap_key = get_config().amap.api_key
            if amap_key:
                resp = httpx.get(
                    "https://restapi.amap.com/v3/ip",
                    params={"key": amap_key, "output": "json"},
                    timeout=3.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "1":
                        province = data.get("province", "") or ""
                        city = data.get("city", "") or ""
                        # 高德 IP 定位返回的 city 可能为空（直辖市等）
                        parts = [p for p in (province, city) if p and p != "[]"]
                        addr = " ".join(parts) if parts else "未知位置"
                        if addr != "未知位置":
                            self.navigation["current_location"] = addr
                            # 高德 IP 定位返回 rectangle（矩形区域），取中心点作为坐标
                            rect = data.get("rectangle", "")
                            if rect and ";" in rect:
                                try:
                                    lo, hi = rect.split(";")
                                    lon1, lat1 = [float(x) for x in lo.split(",")]
                                    lon2, lat2 = [float(x) for x in hi.split(",")]
                                    self.navigation["latitude"] = (lat1 + lat2) / 2
                                    self.navigation["longitude"] = (lon1 + lon2) / 2
                                except Exception:
                                    pass
                            logger.info(f"Location updated via IP (Amap): {addr}")
                            return addr
        except Exception as e:
            logger.warning(f"IP geolocation (Amap) failed: {e}")

        # 2b. IP 定位 — ip-api.com (国际备选)
        try:
            import httpx
            resp = httpx.get(
                "http://ip-api.com/json/",
                params={"lang": "zh-CN", "fields": "status,country,regionName,city,lat,lon,query"},
                timeout=5.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success":
                    parts = []
                    for key in ("country", "regionName", "city"):
                        val = data.get(key, "")
                        if val:
                            parts.append(val)
                    addr = " ".join(parts) if parts else data.get("query", "未知位置")
                    self.navigation["current_location"] = addr
                    self.navigation["latitude"] = data.get("lat")
                    self.navigation["longitude"] = data.get("lon")
                    logger.info(f"Location updated via IP (ip-api): {addr}")
                    return addr
        except Exception as e:
            logger.warning(f"IP geolocation (ip-api.com) failed: {e}")

        # 3. 降级：返回坐标字符串（已存储坐标，不缓存地址）
        if latitude is not None and longitude is not None:
            fallback = f"坐标 ({latitude:.4f}, {longitude:.4f})（逆地理编码服务暂不可用）"
            logger.warning(f"All reverse geocoding failed, using coordinates: ({latitude}, {longitude})")
            return fallback

        fallback = "未知位置（定位服务不可用）"
        logger.warning("All geolocation methods failed, location unknown")
        return fallback

    def vehicle_media(
        self,
        op: str = "play",
        source: Optional[str] = None,
        track: Optional[str] = None,
        volume: Optional[int] = None,
        play_mode: Optional[str] = None,
    ) -> VehicleCommandResult:
        # 设置播放模式 (sequential / single / shuffle)
        if op in ("set_play_mode", "play_mode"):
            valid_modes = ("sequential", "single", "shuffle")
            if play_mode and play_mode in valid_modes:
                self.media["play_mode"] = play_mode
                mode_names = {"sequential": "列表循环", "single": "单曲循环", "shuffle": "随机播放"}
                return VehicleCommandResult(
                    success=True,
                    message=f"播放模式已切换为{mode_names.get(play_mode, play_mode)}。",
                    data={"media": dict(self.media)},
                )
            return VehicleCommandResult(
                success=False,
                message=f"不支持的播放模式: {play_mode}",
                error="invalid_play_mode",
                data={"media": dict(self.media)},
            )

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
            if not self.media.get("track") and self._playlist:
                self.media["track"] = self._playlist[self._track_index]
        elif op in ("pause", "stop"):
            self.media["playing"] = False
        elif op in ("next", "next_track"):
            if self._playlist:
                mode = self.media.get("play_mode", "sequential")
                if mode == "shuffle":
                    import random
                    if len(self._playlist) > 1:
                        new_idx = random.randint(0, len(self._playlist) - 1)
                        while new_idx == self._track_index:
                            new_idx = random.randint(0, len(self._playlist) - 1)
                        self._track_index = new_idx
                    else:
                        self._track_index = 0
                else:
                    # sequential 和 single 都前进到下一首
                    # single 模式下由前端 audio.loop = true 控制循环
                    # 手动点下一首时也应该前进
                    self._track_index = (self._track_index + 1) % len(self._playlist)
                self.media["track"] = self._playlist[self._track_index]
                self.media["track_index"] = self._track_index
                self.media["playing"] = True
        elif op in ("prev", "previous_track"):
            if self._playlist:
                mode = self.media.get("play_mode", "sequential")
                if mode == "shuffle":
                    import random
                    if len(self._playlist) > 1:
                        new_idx = random.randint(0, len(self._playlist) - 1)
                        while new_idx == self._track_index:
                            new_idx = random.randint(0, len(self._playlist) - 1)
                        self._track_index = new_idx
                    else:
                        self._track_index = 0
                else:
                    self._track_index = (self._track_index - 1) % len(self._playlist)
                self.media["track"] = self._playlist[self._track_index]
                self.media["track_index"] = self._track_index
                self.media["playing"] = True
        elif op in ("play_track", "select_track"):
            if track is not None and self._playlist:
                # 按索引或名称选择歌曲
                if isinstance(track, int) or (isinstance(track, str) and track.isdigit()):
                    idx = int(track)
                    if 0 <= idx < len(self._playlist):
                        self._track_index = idx
                else:
                    # 按名称模糊查找（支持 title 和 filename 匹配）
                    for i, t in enumerate(self._playlist):
                        if track in t["title"] or track in t["filename"]:
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

    def vehicle_status(self, op: str = "status") -> VehicleCommandResult:
        """返回完整车辆状态，包含所有子系统数据。"""
        # 如果是查询位置，返回导航中的位置信息
        if op in ("location", "current_location", "where", "位置", "我在哪"):
            loc = self.navigation.get("current_location", "")
            if not loc:
                loc = self._fetch_ip_location()
            return VehicleCommandResult(
                success=True,
                message=f"您当前位于{loc}，朝{self.navigation.get('heading', '北')}方向行驶。",
                data={"navigation": dict(self.navigation)},
            )
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
