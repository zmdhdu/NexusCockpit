import { redirect } from "next/navigation";

/**
 * 根页面 — 按角色自动跳转
 *
 * 由于 Next.js Server Component 无法读取 localStorage 中的 JWT，
 * 这里统一跳转到座舱控制页，由客户端组件再根据角色决定是否跳转到管理页面。
 */
export default function Home() {
  redirect("/cockpit");
}
