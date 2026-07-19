# ============================================================
# NexusCockpit Frontend Startup Script
# 启动前端服务，同时将终端所有输出写入日志文件
#
# 用法:
#   .\scripts\start-frontend.ps1
#
# 日志文件位置: logs\frontend_logs\frontend_YYYYMMDD_HHMMSS.log
# ============================================================

$ErrorActionPreference = "SilentlyContinue"

# 获取项目根目录
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$frontendDir = Join-Path $projectRoot "frontend_design"
$logDir = Join-Path $projectRoot "logs" "frontend_logs"

# 创建日志目录
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

# 生成带时间戳的日志文件名
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $logDir "frontend_$timestamp.log"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  NexusCockpit Frontend Starting..." -ForegroundColor Cyan
Write-Host "  Log file: $logFile" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 切换到前端目录
Set-Location $frontendDir

# 启动 Next.js dev server，所有终端输出通过 Tee-Object 同时写入文件
npm run dev 2>&1 | Tee-Object -FilePath $logFile -Append

Write-Host ""
Write-Host "Frontend stopped. Log saved to: $logFile" -ForegroundColor Yellow
