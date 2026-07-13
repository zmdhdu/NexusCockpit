/**
 * Copyright (c) 2026 zhangmengdi (NexusCockpit)
 * Licensed under the MIT License. See LICENSE in the project root for details.
 * Source: https://github.com/zmdhdu/NexusCockpit
 */

import { redirect } from "next/navigation";

/** /dataplatform 已合并到 /dashboard 运营总览，自动跳转 */
export default function DataPlatformPage() {
  redirect("/dashboard");
}
