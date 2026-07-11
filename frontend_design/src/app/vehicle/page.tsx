import { VehiclePanel } from "@/components/vehicle/vehicle-panel";
import { VoiceAssistantBar } from "@/components/vehicle/voice-assistant-bar";

export default function VehiclePage() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">智能座舱</h1>
        <p className="text-sm text-muted-foreground">
          语音控制 · 快捷操作 · 实时状态
        </p>
      </div>
      {/* 语音助手栏 — 置顶方便用户快速操作 */}
      <VoiceAssistantBar />
      {/* 车控面板 */}
      <VehiclePanel />
    </div>
  );
}
