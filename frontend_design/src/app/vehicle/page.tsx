import { VehiclePanel } from "@/components/vehicle/vehicle-panel";

export default function VehiclePage() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">车控面板</h1>
        <p className="text-sm text-muted-foreground">
          可视化控制车辆各子系统
        </p>
      </div>
      <VehiclePanel />
    </div>
  );
}
