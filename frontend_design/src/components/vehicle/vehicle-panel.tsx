"use client";

import { useState, useEffect } from "react";
import {
  Thermometer,
  Wind,
  Volume2,
  Music,
  Navigation as NavIcon,
  Gauge,
  Battery,
  Fuel,
  Settings2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { getVehicleStatus, sendVehicleCommand, type VehicleStatus } from "@/lib/api";

export function VehiclePanel() {
  const [status, setStatus] = useState<VehicleStatus | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchStatus = async () => {
    try {
      const s = await getVehicleStatus();
      setStatus(s);
    } catch {
      // Use mock data if API not available
      setStatus({
        climate: { temperature: 22, fan_speed: 3, mode: "auto", power: true },
        windows: { all: 0, front_left: 0, front_right: 0, rear_left: 0, rear_right: 0, sunroof: 0 },
        seats: {
          driver: { heat: 0, cool: 0, massage: false, position: "neutral" },
          passenger: { heat: 0, cool: 0, massage: false, position: "neutral" },
        },
        media: { playing: false, volume: 18, source: "local", track: "" },
        navigation: { destination: "", mode: "drive" },
        status: { tire_pressure: "normal", range_km: 420, fuel_percent: 58, battery_percent: 76, maintenance: "normal" },
      });
    }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  const handleCommand = async (command: string, args: Record<string, any>) => {
    setLoading(true);
    try {
      await sendVehicleCommand({ command, arguments: args });
      await fetchStatus();
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  if (!status) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="text-muted-foreground">加载车辆状态...</div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {/* Climate */}
      <Card className="glass">
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-base">空调控制</CardTitle>
          <Thermometer className="h-5 w-5 text-primary" />
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-3xl font-bold text-primary">
              {status.climate.temperature}°C
            </span>
            <span className="text-sm text-muted-foreground">
              {status.climate.mode} | {status.climate.fan_speed}档
            </span>
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleCommand("vehicle_climate", { op: "temp_down" })}
              disabled={loading}
            >
              -1°
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleCommand("vehicle_climate", { op: "set_temp", target_temp: 24 })}
              disabled={loading}
            >
              24°
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleCommand("vehicle_climate", { op: "temp_up" })}
              disabled={loading}
            >
              +1°
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleCommand("vehicle_climate", { op: "set_fan", fan_speed: 3 })}
              disabled={loading}
            >
              <Wind className="h-4 w-4" />
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Windows */}
      <Card className="glass">
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-base">车窗控制</CardTitle>
          <Settings2 className="h-5 w-5 text-primary" />
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-2 text-sm">
            {Object.entries(status.windows).map(([key, val]) => (
              <div key={key} className="flex justify-between">
                <span className="text-muted-foreground">{key}</span>
                <span className="font-medium">{val}%</span>
              </div>
            ))}
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleCommand("vehicle_window", { op: "open", position: "all" })}
              disabled={loading}
            >
              全开
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleCommand("vehicle_window", { op: "close", position: "all" })}
              disabled={loading}
            >
              全关
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Media */}
      <Card className="glass">
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-base">媒体控制</CardTitle>
          <Music className="h-5 w-5 text-primary" />
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">
              {status.media.playing ? "播放中" : "已暂停"}
            </span>
            <span className="flex items-center gap-1 text-sm">
              <Volume2 className="h-4 w-4" />
              {status.media.volume}
            </span>
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleCommand("vehicle_media", { op: "play" })}
              disabled={loading}
            >
              播放
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleCommand("vehicle_media", { op: "pause" })}
              disabled={loading}
            >
              暂停
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleCommand("vehicle_media", { op: "next" })}
              disabled={loading}
            >
              下一首
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Vehicle Status */}
      <Card className="glass">
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-base">车辆状态</CardTitle>
          <Gauge className="h-5 w-5 text-primary" />
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="flex items-center gap-2">
              <Fuel className="h-4 w-4 text-muted-foreground" />
              <span className="text-muted-foreground">油量</span>
              <span className="font-medium">{status.status.fuel_percent}%</span>
            </div>
            <div className="flex items-center gap-2">
              <Battery className="h-4 w-4 text-muted-foreground" />
              <span className="text-muted-foreground">电量</span>
              <span className="font-medium">{status.status.battery_percent}%</span>
            </div>
            <div className="flex items-center gap-2">
              <NavIcon className="h-4 w-4 text-muted-foreground" />
              <span className="text-muted-foreground">续航</span>
              <span className="font-medium">{status.status.range_km}km</span>
            </div>
            <div className="flex items-center gap-2">
              <Gauge className="h-4 w-4 text-muted-foreground" />
              <span className="text-muted-foreground">胎压</span>
              <span className="font-medium">{status.status.tire_pressure}</span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Navigation */}
      <Card className="glass">
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-base">导航</CardTitle>
          <NavIcon className="h-5 w-5 text-primary" />
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="text-sm text-muted-foreground">
            {status.navigation.destination
              ? `目的地: ${status.navigation.destination}`
              : "当前无导航任务"}
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={() => handleCommand("vehicle_navigation", { destination: "上海虹桥火车站", mode: "drive" })}
            disabled={loading}
            className="w-full"
          >
            导航到上海虹桥
          </Button>
        </CardContent>
      </Card>

      {/* Seats */}
      <Card className="glass">
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-base">座椅</CardTitle>
          <Settings2 className="h-5 w-5 text-primary" />
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="text-sm space-y-1">
            <div className="flex justify-between">
              <span className="text-muted-foreground">主驾加热</span>
              <span className="font-medium">{status.seats.driver.heat > 0 ? `${status.seats.driver.heat}档` : "关闭"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">主驾按摩</span>
              <span className="font-medium">{status.seats.driver.massage ? "开启" : "关闭"}</span>
            </div>
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleCommand("vehicle_seat", { op: "heat_on", position: "driver", level: 1 })}
              disabled={loading}
            >
              加热
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleCommand("vehicle_seat", { op: "massage_on", position: "driver", level: 1 })}
              disabled={loading}
            >
              按摩
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
