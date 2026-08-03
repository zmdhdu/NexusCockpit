# ============================================================
# NexusCockpit Stop All Services Script (P2-1 落地)
# 停止后台运行的 Backend / Gateway / Frontend 进程
#
# 用法:
#   .\scripts\stop-all.ps1
# ============================================================

$ErrorActionPreference = "SilentlyContinue"

Write-Host "========================================" -ForegroundColor Yellow
Write-Host "  Stopping NexusCockpit Services..." -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow
Write-Host ""

# --- 1. Backend (uvicorn / Python) ---
$backendProcs = Get-Process -Name "python*", "uvicorn*" -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowTitle -eq "" -or $_.Path -match "uvicorn|nexus" }
$stopped = 0
foreach ($proc in $backendProcs) {
    try {
        $cmdLine = (Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.Id)").CommandLine
        if ($cmdLine -match "uvicorn.*nexus") {
            Write-Host "  Stopping Backend PID $($proc.Id)..." -ForegroundColor Gray
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            $stopped++
        }
    } catch {
        # 无法检查命令行，跳过
    }
}

# 如果上面的方法没找到，尝试按端口查找
if ($stopped -eq 0) {
    $portProcs = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($pid in $portProcs) {
        Write-Host "  Stopping Backend (port 8000) PID $pid..." -ForegroundColor Gray
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        $stopped++
    }
}
Write-Host "[1/3] Backend stopped ($stopped process(es))." -ForegroundColor $(if($stopped){'Green'}else{'DarkGray'})

# --- 2. Gateway (Go) ---
$stopped = 0
$portProcs = Get-NetTCPConnection -LocalPort 9090 -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique
foreach ($pid in $portProcs) {
    Write-Host "  Stopping Gateway (port 9090) PID $pid..." -ForegroundColor Gray
    Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
    $stopped++
}
# Also kill any 'go run' processes
$goProcs = Get-Process -Name "go*", "nexus_gate*" -ErrorAction SilentlyContinue
foreach ($proc in $goProcs) {
    Write-Host "  Stopping Gateway PID $($proc.Id)..." -ForegroundColor Gray
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    $stopped++
}
Write-Host "[2/3] Gateway stopped ($stopped process(es))." -ForegroundColor $(if($stopped){'Green'}else{'DarkGray'})

# --- 3. Frontend (Next.js / Node) ---
$stopped = 0
$portProcs = Get-NetTCPConnection -LocalPort 3000 -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique
foreach ($pid in $portProcs) {
    Write-Host "  Stopping Frontend (port 3000) PID $pid..." -ForegroundColor Gray
    Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
    $stopped++
}
# Also kill any 'next dev' processes
$nodeProcs = Get-Process -Name "node*" -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -and $_.Path -match "next" }
foreach ($proc in $nodeProcs) {
    Write-Host "  Stopping Frontend PID $($proc.Id)..." -ForegroundColor Gray
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    $stopped++
}
Write-Host "[3/3] Frontend stopped ($stopped process(es))." -ForegroundColor $(if($stopped){'Green'}else{'DarkGray'})

Write-Host ""
Write-Host "========================================" -ForegroundColor Yellow
Write-Host "  All services stopped." -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Yellow
