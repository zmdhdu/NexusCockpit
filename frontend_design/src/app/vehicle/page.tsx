import { redirect } from "next/navigation";

/** /vehicle 已合并到 /cockpit，自动跳转 */
export default function VehiclePage() {
  redirect("/cockpit");
}
