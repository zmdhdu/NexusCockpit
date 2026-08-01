# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""导航状态模型 + 导航控制方法 + IP 定位逻辑。"""

from __future__ import annotations

from typing import Any

from nexus.core.logger import get_logger
from nexus.vehicle.base import VehicleCommandResult

logger = get_logger(__name__)


class NavigationState:
    """导航状态管理 + IP/GPS 定位。"""

    def __init__(self):
        self.navigation: dict[str, Any] = {
            "destination": "",
            "waypoint": "",
            "mode": "drive",
            "current_location": "",  # 初始为空，首次查询时动态获取
            "latitude": None,
            "longitude": None,
            "speed_kmh": 0,
            "heading": "北",
        }

    def handle(
        self, destination: str = "", waypoint: str = "", mode: str = "drive",
        op: str = "navigate",
        latitude: float | None = None,
        longitude: float | None = None,
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

    def _fetch_ip_location(self, latitude: float | None = None, longitude: float | None = None) -> str:
        """通过 IP 或浏览器坐标获取当前位置。

        优先级:
            1. 浏览器 GPS 坐标 (latitude/longitude) → 逆地理编码
               1a. 高德地图 (Amap) — 国内服务，速度快
               1b. Nominatim (OpenStreetMap) — 国际备选
            2. IP 定位 — 多服务尝试
               2a. 高德 IP 定位 API — 国内服务，速度快
               2b. ip-api.com — 国际备选
            3. 降级：返回坐标字符串（仍存储坐标）
        """
        # 无论逆地理编码是否成功，先存储坐标
        if latitude is not None and longitude is not None:
            self.navigation["latitude"] = latitude
            self.navigation["longitude"] = longitude

        # 1a. 优先使用高德地图逆地理编码
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

        # 2a. IP 定位 — 高德 IP 定位 API
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
                        parts = [p for p in (province, city) if p and p != "[]"]
                        addr = " ".join(parts) if parts else "未知位置"
                        if addr != "未知位置":
                            self.navigation["current_location"] = addr
                            rect = data.get("rectangle", "")
                            if rect and ";" in rect:
                                try:
                                    lo, hi = rect.split(";")
                                    lon1, lat1 = [float(x) for x in lo.split(",")]
                                    lon2, lat2 = [float(x) for x in hi.split(",")]
                                    self.navigation["latitude"] = (lat1 + lat2) / 2
                                    self.navigation["longitude"] = (lon1 + lon2) / 2
                                except Exception as e:
                                    logger.debug(f"Failed to parse GPS rectangle: {e}")
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

        # 3. 降级：返回坐标字符串
        if latitude is not None and longitude is not None:
            fallback = f"坐标 ({latitude:.4f}, {longitude:.4f})（逆地理编码服务暂不可用）"
            logger.warning(f"All reverse geocoding failed, using coordinates: ({latitude}, {longitude})")
            return fallback

        fallback = "未知位置（定位服务不可用）"
        logger.warning("All geolocation methods failed, location unknown")
        return fallback
