# ============================================================
# NexusCockpit All-in-One Startup Script (P2-1 落地)
# 在后台依次启动 Backend (Python) + Gateway (Go) + Frontend (Next.js)
#
# 用法:
#   .\scripts\start-all.ps1              # 启动全部
#   .\scripts\start-all.ps1 -NoGateway   # 跳过 Go 网关
#
# 日志位置:
#   logs\backend_logs\backend_YYYYMMDD_HHMMSS.log
#   logs\go_logs\gateway_YYYYMMDD_HHMMSS.log
#   logs\frontend_logs\frontend_YYYYMMDD_HHMMSS.log
# ============================================================

param(
    [switch]$NoGateway,
    [switch]$NoFrontend
)

$ErrorActionPreference = "SilentlyContinue"

# 获取项目根目录
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir

$backendDir = Join-Path $projectRoot "backend_design"
$gatewayDir = Join-Path $projectRoot "backend_design" "nexus_gate"
$frontendDir = Join-Path $projectRoot "frontend_design"

$backendLogDir = Join-Path $projectRoot "logs" "backend_logs"
$gatewayLogDir = Join-Path $projectRoot "logs" "go_logs"
$frontendLogDir = Join-Path $projectRoot "logs" "frontend_logs"

# 确保日志目录存在
foreach ($dir in @($backendLogDir, $gatewayLogDir, $frontendLogDir)) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  NexusCockpit All Services Starting..." -ForegroundColor Cyan
Write-Host "  Timestamp: $timestamp" -ForegroundColor Gray
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# --- 1. Backend (Python uvicorn) ---
$backendLog = Join-Path $backendLogDir "backend_$timestamp.log"
Write-Host "[1/3] Starting Backend (uvicorn :8000)..." -ForegroundColor Green
Write-Host "      Log: $backendLog" -ForegroundColor Gray
$backendProc = Start-Process -FilePath "uvicorn" `
    -ArgumentList "nexus.main:app", "--host", "0.0.0.0", "--port", "8000" `
    -WorkingDirectory $backendDir `
    -RedirectStandardOutput $backendLog `
    -RedirectStandardError $backendLog `
    -PassThru -WindowStyle Hidden
Write-Host "      PID: $($backendProc.Id)" -ForegroundColor Yellow
Start-Sleep -Seconds 3

# --- 2. Gateway (Go) ---
if (-not $NoGateway) {
    $gatewayLog = Join-Path $gatewayLogDir "gateway_$timestamp.log"
    Write-Host "[2/3] Starting Gateway (Go :9090)..." -ForegroundColor Green
    Write-Host "      Log: $gatewayLog" -ForegroundColor Gray
    $envFile = Join-Path $projectRoot ".env.local"
    $gatewayProc = Start-Process -FilePath "go" `
        -ArgumentList "run", "./cmd/", "--env", $envFile `
        -WorkingDirectory $gatewayDir `
        -RedirectStandardOutput $gatewayLog `
        -RedirectStandardError $gatewayLog `
        -PassThru -WindowStyle Hidden
    Write-Host "      PID: $($gatewayProc.Id)" -ForegroundColor Yellow
    Start-Sleep -Seconds 2
} else {
    Write-Host "[2/3] Gateway skipped (-NoGateway)" -ForegroundColor DarkGray
}

# --- 3. Frontend (Next.js) ---
if (-not $NoFrontend) {
    $frontendLog = Join-Path $frontendLogDir "frontend_$timestamp.log"
    Write-Host "[3/3] Starting Frontend (Next.js :3000)..." -ForegroundColor Green
    Write-Host "      Log: $frontendLog" -ForegroundColor Gray
    $frontendProc = Start-Process -FilePath "npm" `
        -ArgumentList "run", "dev" `
        -WorkingDirectory $frontendDir `
        -RedirectStandardOutput $frontendLog `
        -RedirectStandardError $frontendLog `
        -PassThru -WindowStyle Hidden
    Write-Host "      PID: $($frontendProc.Id)" -ForegroundColor Yellow
} else {
    Write-Host "[3/3] Frontend skipped (-NoFrontend)" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  All services started in background." -ForegroundColor Green
Write-Host "  Use .\scripts\stop-all.ps1 to stop." -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
