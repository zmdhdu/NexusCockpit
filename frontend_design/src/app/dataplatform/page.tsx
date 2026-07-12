import { redirect } from "next/navigation";

/** /dataplatform 已合并到 /dashboard 运营总览，自动跳转 */
export default function DataPlatformPage() {
  redirect("/dashboard");
}
