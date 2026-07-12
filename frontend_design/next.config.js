/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // v2.1: Docker standalone 构建（生成独立运行包，减小镜像体积）
  output: "standalone",
  // 注意: 前端通过 axios baseURL 和 fetch 直连后端 (http://localhost:8080)，
  // 不依赖 Next.js rewrites 代理。如需启用代理避免 CORS，请将 api.ts 的
  // baseURL 改为 "/api" 并取消下方 rewrites 的注释。
  //
  // async rewrites() {
  //   return [
  //     {
  //       source: "/api/:path*",
  //       destination: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080"}/:path*`,
  //     },
  //   ];
  // },
};

module.exports = nextConfig;
