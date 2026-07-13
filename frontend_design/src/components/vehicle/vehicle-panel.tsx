/**
 * 车辆控制面板组件 — 可视化车控交互界面
 *
 * 功能模块:
 *   - 空调控制: 温度调节/模式切换/风量调节
 *   - 座椅控制: 加热/按摩开关
 *   - 媒体播放: 播放/暂停/上一首/下一首/音量/播放列表
 *   - 导航控制: 输入目的地/取消导航
 *   - 车窗控制: 各车窗开度显示/全开全关
 *   - 车辆状态: 油量/电量/续航/胎压概览
 *
 * 数据来源:
 *   - 初始化时调用 getVehicleStatus() 拉取完整状态
 *   - 用户操作通过 sendVehicleCommand() 发送指令后异步刷新
 *   - 语音助手触发车控时通过 vehicle-events 事件总线通知刷新
 *   - 后端不可用时自动降级到 Mock 数据（离线模式）
 *
 * v2.1: 支持多座舱切换，每个座舱有独立的车控状态
 */
"use client";

import { useState, useEffect, useRef } from "react";
import {
  Thermometer,
  Wind,
  Volume2,
  Music,
  Navigation as NavIcon,
  Gauge,
  Battery,
  Fuel,
  Play,
  Pause,
  SkipForward,
  SkipBack,
  Plus,
  Minus,
  Flame,
  Snowflake,
  Hand,
  MapPin,
  X,
  WifiOff,
  Loader2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { getVehicleStatus, sendVehicleCommand, updateVehicleLocation } from "@/lib/api";
import { onVehicleRefresh } from "@/lib/vehicle-events";
import { useAuth } from "@/stores/auth-store";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import type { VehicleStatus } from "@/types";

/** 离线时的 Mock 数据 */
const MOCK_STATUS: VehicleStatus = {
  climate: { temperature: 22, fan_speed: 3, mode: "auto", power: true },
  windows: { all: 0, front_left: 0, front_right: 0, rear_left: 0, rear_right: 0, sunroof: 0 },
  seats: {
    driver: { heat: 0, cool: 0, massage: false, position: "neutral" },
    passenger: { heat: 0, cool: 0, massage: false, position: "neutral" },
  },
  media: { playing: false, volume: 18, source: "local", track: "爱错 - 王力宏" },
  navigation: { destination: "", mode: "drive" },
  status: { tire_pressure: "正常", range_km: 420, fuel_percent: 58, battery_percent: 76, maintenance: "正常" },
};

const CLIMATE_MODES = [
  { key: "auto", label: "自动", icon: Wind },
  { key: "cool", label: "制冷", icon: Snowflake },
  { key: "heat", label: "制热", icon: Flame },
  { key: "vent", label: "通风", icon: Wind },
  { key: "defrost", label: "除霜", icon: Snowflake },
];

export function VehiclePanel() {
  const { cockpitId } = useAuth();
  const [status, setStatus] = useState<VehicleStatus | null>(null);
  const [offline, setOffline] = useState(false);
  const [navInput, setNavInput] = useState("");
  /** 正在执行的命令集合（支持多命令并行，不阻塞其他按钮） */
  const [executingCmds, setExecutingCmds] = useState<Set<string>>(new Set());
  const mountedRef = useRef(true);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // 初始化音频元素
  useEffect(() => {
    audioRef.current = new Audio();
    audioRef.current.loop = false;
    audioRef.current.addEventListener("ended", () => {
      // 自动播放下一首
      if (status?.media) {
        handleCommand("vehicle_media", { op: "next" });
      }
    });
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
    };
  }, []);

  // 根据媒体状态控制音频播放
  useEffect(() => {
    if (!audioRef.current || !status?.media) return;
    const media = status.media as any;
    const trackIndex = media.track_index ?? 0;
    const trackUrl = `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/audio/music/track_${String(trackIndex + 1).padStart(2, "0")}.wav`;

    if (media.playing) {
      if (audioRef.current.src !== trackUrl) {
        audioRef.current.src = trackUrl;
      }
      audioRef.current.volume = Math.min(1, (media.volume || 18) / 30);
      audioRef.current.play().catch(() => {});
    } else {
      audioRef.current.pause();
    }
  }, [status?.media?.playing, (status?.media as any)?.track_index, (status?.media as any)?.volume]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

/** 拉取车辆状态 — 从后端获取最新车控数据，失败时降级到 Mock 数据 */
  const fetchStatus = async () => {
    try {
      const s = await getVehicleStatus();
      if (mountedRef.current) {
        setStatus(s);
        setOffline(false);
        if (s.navigation?.destination) {
          setNavInput(s.navigation.destination);
        }
      }
    } catch {
      if (mountedRef.current) {
        setStatus(MOCK_STATUS);
        setOffline(true);
      }
    }
  };

useEffect(() => {
fetchStatus();
}, []);

// v2.1: 座舱切换时重新拉取车辆状态（每个座舱数据独立）
useEffect(() => {
fetchStatus();
}, [cockpitId]);

  // v2.2.2: GPS 定位已提取到全局 hook (use-gps-location.ts)，在根布局中统一管理
  // 此处仅保留位置更新后的状态刷新
  useEffect(() => {
    if (typeof navigator !== "undefined" && navigator.geolocation) {
      const fetchLocation = () => {
        navigator.geolocation.getCurrentPosition(
          async (position) => {
            try {
              await updateVehicleLocation(
                position.coords.latitude,
                position.coords.longitude
              );
              // 定位更新后重新拉取状态
              setTimeout(() => fetchStatus(), 500);
            } catch {
              // 静默失败
            }
          },
          () => {
            // 用户拒绝或定位失败，静默处理（后端会自动使用 IP 定位）
          },
          { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
        );
      };

      // 首次获取（全局 hook 也会更新，但这里需要刷新车辆面板状态）
      fetchLocation();

      // v2.2.3: 降低轮询频率到 5 分钟，仅刷新坐标缓存
      const interval = setInterval(fetchLocation, 300000);
      return () => clearInterval(interval);
    }
  }, []);

  // 订阅语音助手触发的车控状态刷新事件
  useEffect(() => {
    const unsubscribe = onVehicleRefresh(() => {
      // 延迟 500ms 等后端处理完成后再拉取
      setTimeout(() => fetchStatus(), 500);
    });
    return unsubscribe;
  }, []);

  /** 检查某个命令是否正在执行 */
  const isCmdLoading = (command: string, args: Record<string, any>) =>
    executingCmds.has(`${command}_${JSON.stringify(args)}`);

/**
   * 发送车控命令 — 向后端发送指令并刷新状态
   *
   * 支持多命令并行: 每个命令用 `command_args` 组合作为唯一 key，
   * 正在执行的命令会禁用对应按钮，但不阻塞其他按钮操作。
   *
   * @param command - 命令名称，如 vehicle_climate / vehicle_media / vehicle_navigation
   * @param args - 命令参数，如 { op: "temp_up" } 或 { destination: "上海虹桥" }
   */
  const handleCommand = async (command: string, args: Record<string, any>) => {
    const cmdKey = `${command}_${JSON.stringify(args)}`;
    // 标记当前命令正在执行（不阻塞其他按钮）
    setExecutingCmds(prev => new Set(prev).add(cmdKey));
    try {
      await sendVehicleCommand({ command, arguments: args });
      // 命令发送成功后，异步刷新状态（不阻塞按钮）
      fetchStatus();
      toast.success("操作成功", {
        description: getCommandDescription(command, args),
      });
    } catch (err) {
      toast.error("操作失败", {
        description: offline ? "当前为离线模式" : "请检查网络连接",
      });
    } finally {
      // 命令完成后立即释放按钮，不等 fetchStatus
      setExecutingCmds(prev => {
        const next = new Set(prev);
        next.delete(cmdKey);
        return next;
      });
    }
  };

/**
   * 生成命令执行成功后的 Toast 描述文案
   * 根据命令类型和参数返回用户可读的操作反馈
   */
  const getCommandDescription = (command: string, args: Record<string, any>): string => {
    if (command === "vehicle_climate") {
      if (args.op === "temp_up") return `温度已调高至 ${status?.climate.temperature || 22}°C`;
      if (args.op === "temp_down") return `温度已调低至 ${status?.climate.temperature || 22}°C`;
      if (args.op === "set_fan") return `风量已设为 ${args.fan_speed} 档`;
      if (args.op === "set_mode") return `模式已切换`;
    }
    if (command === "vehicle_media") {
      if (args.op === "play") return "开始播放";
      if (args.op === "pause") return "已暂停";
      if (args.op === "next") return "下一曲";
      if (args.op === "prev") return "上一曲";
    }
    if (command === "vehicle_navigation") {
      if (args.destination) return `导航至: ${args.destination}`;
      return "已取消导航";
    }
    return "操作已完成";
  };

  if (!status) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* 离线提示 */}
      {offline && (
        <div className="flex items-center gap-2 rounded-lg bg-amber-500/10 px-4 py-2 text-amber-400 text-sm">
          <WifiOff className="h-4 w-4" />
          <span>当前为模拟模式，部分功能可能不可用</span>
        </div>
      )}

      {/* 车辆状态概览条 */}
      <div className="grid grid-cols-4 gap-3">
        <StatusChip icon={Fuel} label="油量" value={`${status.status.fuel_percent}%`} color="text-orange-400" />
        <StatusChip icon={Battery} label="电量" value={`${status.status.battery_percent}%`} color="text-emerald-400" />
        <StatusChip icon={NavIcon} label="续航" value={`${status.status.range_km}km`} color="text-sky-400" />
        <StatusChip icon={Gauge} label="胎压" value={status.status.tire_pressure} color="text-violet-400" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {/* 空调控制 */}
        <Card className="glass">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-base">空调</CardTitle>
            <Thermometer className="h-5 w-5 text-primary" />
          </CardHeader>
          <CardContent className="space-y-4">
            {/* 大号温度显示 */}
            <div className="flex items-center justify-center gap-4 py-2">
              <Button
                size="icon"
                variant="outline"
                onClick={() => handleCommand("vehicle_climate", { op: "temp_down" })}
                disabled={isCmdLoading("vehicle_climate", { op: "temp_down" })}
                className="h-10 w-10 rounded-full"
              >
                <Minus className="h-5 w-5" />
              </Button>
              <div className="text-center">
                <span className="text-4xl font-bold text-primary">
                  {status.climate.temperature}
                </span>
                <span className="text-xl text-muted-foreground">°C</span>
              </div>
              <Button
                size="icon"
                variant="outline"
                onClick={() => handleCommand("vehicle_climate", { op: "temp_up" })}
                disabled={isCmdLoading("vehicle_climate", { op: "temp_up" })}
                className="h-10 w-10 rounded-full"
              >
                <Plus className="h-5 w-5" />
              </Button>
            </div>

            {/* 模式选择 */}
            <div className="grid grid-cols-5 gap-1">
              {CLIMATE_MODES.map((m) => {
                const Icon = m.icon;
                return (
                  <button
                    key={m.key}
                    onClick={() => handleCommand("vehicle_climate", { op: "set_mode", mode: m.key })}
                    disabled={isCmdLoading("vehicle_climate", { op: "set_mode", mode: m.key })}
                    className={cn(
                      "flex flex-col items-center gap-1 rounded-lg py-2 text-xs transition-all",
                      status.climate.mode === m.key
                        ? "bg-primary/20 text-primary font-medium"
                        : "bg-accent/30 text-muted-foreground hover:bg-accent/60"
                    )}
                  >
                    <Icon className="h-4 w-4" />
                    {m.label}
                  </button>
                );
              })}
            </div>

            {/* 风量调节 */}
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleCommand("vehicle_climate", { op: "set_fan", fan_speed: Math.max(1, status.climate.fan_speed - 1) })}
                disabled={isCmdLoading("vehicle_climate", { op: "set_fan", fan_speed: Math.max(1, status.climate.fan_speed - 1) }) || status.climate.fan_speed <= 1}
                className="h-8 w-8 p-0"
              >
                <Minus className="h-3 w-3" />
              </Button>
              <div className="flex-1 flex items-center gap-1">
                {Array.from({ length: 7 }, (_, i) => (
                  <div
                    key={i}
                    className={cn(
                      "h-6 flex-1 rounded-sm transition-all",
                      i < status.climate.fan_speed
                        ? "bg-primary/60"
                        : "bg-accent/30"
                    )}
                  />
                ))}
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleCommand("vehicle_climate", { op: "set_fan", fan_speed: Math.min(7, status.climate.fan_speed + 1) })}
                disabled={isCmdLoading("vehicle_climate", { op: "set_fan", fan_speed: Math.min(7, status.climate.fan_speed + 1) }) || status.climate.fan_speed >= 7}
                className="h-8 w-8 p-0"
              >
                <Plus className="h-3 w-3" />
              </Button>
            </div>
            <div className="text-center text-xs text-muted-foreground">
              风量 {status.climate.fan_speed} 档
            </div>
          </CardContent>
        </Card>

        {/* 座椅控制 */}
        <Card className="glass">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-base">座椅</CardTitle>
            <Hand className="h-5 w-5 text-primary" />
          </CardHeader>
          <CardContent className="space-y-3">
            {/* 加热 */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="flex items-center gap-1.5 text-muted-foreground">
                  <Flame className="h-4 w-4 text-orange-400" />
                  主驾加热
                </span>
                <span className="font-medium">
                  {status.seats.driver.heat > 0 ? `${status.seats.driver.heat}档` : "关闭"}
                </span>
              </div>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant={status.seats.driver.heat > 0 ? "default" : "outline"}
                  onClick={() => handleCommand("vehicle_seat", { op: "heat_on", position: "driver", level: 1 })}
                  disabled={isCmdLoading("vehicle_seat", { op: "heat_on", position: "driver", level: 1 }) || status.seats.driver.heat > 0}
                  className="flex-1"
                >
                  开启
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleCommand("vehicle_seat", { op: "heat_off", position: "driver" })}
                  disabled={isCmdLoading("vehicle_seat", { op: "heat_off", position: "driver" }) || status.seats.driver.heat === 0}
                  className="flex-1"
                >
                  关闭
                </Button>
              </div>
            </div>

            {/* 按摩 */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="flex items-center gap-1.5 text-muted-foreground">
                  <Hand className="h-4 w-4 text-violet-400" />
                  主驾按摩
                </span>
                <span className="font-medium">
                  {status.seats.driver.massage ? "开启中" : "关闭"}
                </span>
              </div>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant={status.seats.driver.massage ? "default" : "outline"}
                  onClick={() => handleCommand("vehicle_seat", { op: "massage_on", position: "driver", level: 1 })}
                  disabled={isCmdLoading("vehicle_seat", { op: "massage_on", position: "driver", level: 1 }) || status.seats.driver.massage}
                  className="flex-1"
                >
                  开启
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleCommand("vehicle_seat", { op: "massage_off", position: "driver" })}
                  disabled={isCmdLoading("vehicle_seat", { op: "massage_off", position: "driver" }) || !status.seats.driver.massage}
                  className="flex-1"
                >
                  关闭
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 媒体控制 */}
        <Card className="glass">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-base">音乐</CardTitle>
            <Music className="h-5 w-5 text-primary" />
          </CardHeader>
          <CardContent className="space-y-3">
            {/* 当前播放 */}
            <div className="flex items-center justify-between">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">
                  {(status.media as any).track || "未播放"}
                </p>
                <p className="text-xs text-muted-foreground">
                  {status.media.playing ? "播放中" : "已暂停"}
                </p>
              </div>
              <span className="flex items-center gap-1 text-sm">
                <Volume2 className="h-4 w-4" />
                {status.media.volume}
              </span>
            </div>

            {/* 播放控制 */}
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleCommand("vehicle_media", { op: "prev" })}
                disabled={isCmdLoading("vehicle_media", { op: "prev" })}
                className="h-9 w-9 p-0"
              >
                <SkipBack className="h-4 w-4" />
              </Button>
              <Button
                size="sm"
                variant={status.media.playing ? "default" : "outline"}
                onClick={() => handleCommand("vehicle_media", { op: status.media.playing ? "pause" : "play" })}
                disabled={isCmdLoading("vehicle_media", { op: status.media.playing ? "pause" : "play" })}
                className="flex-1 h-9"
              >
                {status.media.playing ? <Pause className="h-4 w-4 mr-1" /> : <Play className="h-4 w-4 mr-1" />}
                {status.media.playing ? "暂停" : "播放"}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleCommand("vehicle_media", { op: "next" })}
                disabled={isCmdLoading("vehicle_media", { op: "next" })}
                className="h-9 w-9 p-0"
              >
                <SkipForward className="h-4 w-4" />
              </Button>
            </div>

            {/* 音量条 */}
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleCommand("vehicle_media", { op: "set_volume", volume: Math.max(0, status.media.volume - 2) })}
                disabled={isCmdLoading("vehicle_media", { op: "set_volume", volume: Math.max(0, status.media.volume - 2) })}
                className="h-7 w-7 p-0"
              >
                <Minus className="h-3 w-3" />
              </Button>
              <div className="flex-1 h-2 bg-accent rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary transition-all"
                  style={{ width: `${(status.media.volume / 30) * 100}%` }}
                />
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleCommand("vehicle_media", { op: "set_volume", volume: Math.min(30, status.media.volume + 2) })}
                disabled={isCmdLoading("vehicle_media", { op: "set_volume", volume: Math.min(30, status.media.volume + 2) })}
                className="h-7 w-7 p-0"
              >
                <Plus className="h-3 w-3" />
              </Button>
            </div>

            {/* 播放列表 */}
            {(status.media as any).playlist && (
              <div className="space-y-1 max-h-32 overflow-y-auto">
                <p className="text-xs text-muted-foreground">播放列表</p>
                {((status.media as any).playlist as string[]).map((track, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleCommand("vehicle_media", { op: "play_track", track: idx })}
                    disabled={isCmdLoading("vehicle_media", { op: "play_track", track: idx })}
                    className={cn(
                      "w-full text-left text-xs px-2 py-1.5 rounded truncate transition-colors flex items-center gap-2",
                      (status.media as any).track_index === idx
                        ? "bg-primary/20 text-primary font-medium"
                        : "hover:bg-accent/50 text-muted-foreground"
                    )}
                  >
                    {(status.media as any).track_index === idx && (
                      <span className="flex items-center">
                        {status.media.playing ? <Volume2 className="h-3 w-3" /> : <Pause className="h-3 w-3" />}
                      </span>
                    )}
                    <span>{idx + 1}. {track}</span>
                  </button>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* 导航 */}
        <Card className="glass">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-base">导航</CardTitle>
            <NavIcon className="h-5 w-5 text-primary" />
          </CardHeader>
          <CardContent className="space-y-3">
            {/* 当前目的地 */}
            <div className="flex items-center gap-2 text-sm">
              <MapPin className="h-4 w-4 text-primary shrink-0" />
              <span className="text-muted-foreground truncate">
                {status.navigation.destination || "未设置目的地"}
              </span>
            </div>

            {/* 输入目的地 */}
            <div className="flex gap-2">
              <Input
                placeholder="输入目的地..."
                value={navInput}
                onChange={(e) => setNavInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && navInput.trim()) {
                    handleCommand("vehicle_navigation", { destination: navInput.trim(), mode: "drive" });
                  }
                }}
                className="flex-1"
              />
              <Button
                size="sm"
                onClick={() => {
                  if (navInput.trim()) {
                    handleCommand("vehicle_navigation", { destination: navInput.trim(), mode: "drive" });
                  }
                }}
                disabled={isCmdLoading("vehicle_navigation", { destination: navInput.trim(), mode: "drive" }) || !navInput.trim()}
              >
                开始
              </Button>
            </div>

            {/* 取消导航 */}
            {status.navigation.destination && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setNavInput("");
                  handleCommand("vehicle_navigation", { destination: "", mode: "drive" });
                }}
                disabled={isCmdLoading("vehicle_navigation", { destination: "", mode: "drive" })}
                className="w-full"
              >
                <X className="h-4 w-4 mr-1" />
                取消导航
              </Button>
            )}
          </CardContent>
        </Card>

        {/* 车窗控制 */}
        <Card className="glass">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-base">车窗</CardTitle>
            <Wind className="h-5 w-5 text-primary" />
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-3 gap-2 text-sm">
              {[
                { key: "front_left", label: "左前" },
                { key: "front_right", label: "右前" },
                { key: "rear_left", label: "左后" },
                { key: "rear_right", label: "右后" },
                { key: "sunroof", label: "天窗" },
              ].map((w) => (
                <div key={w.key} className="flex flex-col items-center gap-1 rounded-lg bg-accent/30 py-2">
                  <span className="text-xs text-muted-foreground">{w.label}</span>
                  <span className="font-medium text-sm">{status.windows[w.key] ?? 0}%</span>
                </div>
              ))}
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleCommand("vehicle_window", { op: "open", position: "all" })}
                disabled={isCmdLoading("vehicle_window", { op: "open", position: "all" })}
                className="flex-1"
              >
                全开
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleCommand("vehicle_window", { op: "close", position: "all" })}
                disabled={isCmdLoading("vehicle_window", { op: "close", position: "all" })}
                className="flex-1"
              >
                全关
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

/** 状态概览条中的单项组件 */
function StatusChip({
  icon: Icon,
  label,
  value,
  color,
}: {
  icon: any;
  label: string;
  value: string;
  color: string;
}) {
  return (
    <div className="flex items-center gap-2 rounded-lg bg-card/50 border border-border px-3 py-2">
      <Icon className={cn("h-4 w-4", color)} />
      <div className="flex flex-col">
        <span className="text-xs text-muted-foreground">{label}</span>
        <span className="text-sm font-medium">{value}</span>
      </div>
    </div>
  );
}
