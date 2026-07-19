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

// v2.3: 日志文件输出 - 写入 logs/frontend_logs/ 文件（仅开发环境）
const fs = require('fs');
const path = require('path');

// 原生时间戳格式化，避免依赖 date-fns
function timestamp() {
  const d = new Date();
  const pad = (n, l = 2) => String(n).padStart(l, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}`;
}

function fileStamp() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
}

function stringifyArg(arg) {
  if (typeof arg === 'object') {
    try { return JSON.stringify(arg); } catch { return String(arg); }
  }
  return String(arg);
}

if (process.env.NODE_ENV !== 'production') {
  // __dirname = NexusCockpit/frontend_design，上一级即为 NexusCockpit 项目根目录
  const logDir = path.join(__dirname, '..', 'logs', 'frontend_logs');
  fs.mkdirSync(logDir, { recursive: true });
  const logFile = path.join(logDir, `frontend_${fileStamp()}.log`);
  const logStream = fs.createWriteStream(logFile, { flags: 'a' });

  const originalLog = console.log.bind(console);
  const originalError = console.error.bind(console);
  const originalWarn = console.warn.bind(console);

  console.log = (...args) => {
    const msg = args.map(stringifyArg).join(' ');
    const line = `[${timestamp()}] ${msg}`;
    originalLog(line);
    logStream.write(line + '\n');
  };

  console.error = (...args) => {
    const msg = args.map(stringifyArg).join(' ');
    const line = `[${timestamp()}] ERROR ${msg}`;
    originalError(line);
    logStream.write(line + '\n');
  };

  console.warn = (...args) => {
    const msg = args.map(stringifyArg).join(' ');
    const line = `[${timestamp()}] WARN ${msg}`;
    originalWarn(line);
    logStream.write(line + '\n');
  };

  originalLog(`[NexusCockpit] Frontend logging to: ${logFile}`);
}

module.exports = nextConfig;
