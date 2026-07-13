/**
 * Copyright (c) 2026 zhangmengdi (NexusCockpit)
 * Licensed under the MIT License. See LICENSE in the project root for details.
 * Source: https://github.com/zmdhdu/NexusCockpit
 */

import { redirect } from "next/navigation";

/** /vehicle 已合并到 /cockpit，自动跳转 */
export default function VehiclePage() {
  redirect("/cockpit");
}
