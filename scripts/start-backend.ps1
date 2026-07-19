# ============================================================
# NexusCockpit Backend Startup Script
# 启动后端服务，同时将终端所有输出写入日志文件
#
# 用法:
#   .\scripts\start-backend.ps1
#
# 日志文件位置: logs\backend_logs\backend_YYYYMMDD_HHMMSS.log
# ============================================================

$ErrorActionPreference = "SilentlyContinue"

# 获取项目根目录
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$backendDir = Join-Path $projectRoot "backend_design"
$logDir = Join-Path $projectRoot "logs" "backend_logs"

# 创建日志目录
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

# 生成带时间戳的日志文件名
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $logDir "backend_$timestamp.log"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  NexusCockpit Backend Starting..." -ForegroundColor Cyan
Write-Host "  Log file: $logFile" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 切换到后端目录
Set-Location $backendDir

# 启动 uvicorn，所有终端输出通过 Tee-Object 同时写入文件
# -ErrorAction SilentlyContinue 防止 Ctrl+C 时报错
uvicorn nexus.main:app --host 0.0.0.0 --port 8000 --reload 2>&1 | Tee-Object -FilePath $logFile -Append

Write-Host ""
Write-Host "Backend stopped. Log saved to: $logFile" -ForegroundColor Yellow
