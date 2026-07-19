# ============================================================
# NexusCockpit Go Gateway Startup Script
# 启动 Go 网关，同时将终端所有输出写入日志文件
#
# 用法:
#   .\scripts\start-gateway.ps1
#
# 日志文件位置: logs\go_logs\gateway_YYYYMMDD_HHMMSS.log
# ============================================================

$ErrorActionPreference = "SilentlyContinue"

# 获取项目根目录
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$gatewayDir = Join-Path $projectRoot "backend_design" "nexus_gate"
$logDir = Join-Path $projectRoot "logs" "go_logs"

# 创建日志目录
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

# 生成带时间戳的日志文件名
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $logDir "gateway_$timestamp.log"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  NexusCockpit Go Gateway Starting..." -ForegroundColor Cyan
Write-Host "  Log file: $logFile" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 切换到网关目录
Set-Location $gatewayDir

# 启动 Go 网关，所有终端输出通过 Tee-Object 同时写入文件
go run ./cmd/ 2>&1 | Tee-Object -FilePath $logFile -Append

Write-Host ""
Write-Host "Gateway stopped. Log saved to: $logFile" -ForegroundColor Yellow
