# ============================================================
# NexusCockpit Auto-Start Registration Script (P2-1 落地)
# 注册 Windows Task Scheduler 任务，实现开机/登录自动启动
#
# 用法:
#   .\scripts\install-autostart.ps1           # 注册自启任务
#   .\scripts\install-autostart.ps1 -Remove     # 移除自启任务
#
# 任务名称: NexusCockpitAutoStart
# 触发器: 用户登录时自动运行 start-all.ps1
# ============================================================

param(
    [switch]$Remove
)

$taskName = "NexusCockpitAutoStart"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$startAllScript = Join-Path $scriptDir "start-all.ps1"

if ($Remove) {
    Write-Host "Removing Task Scheduler entry: $taskName" -ForegroundColor Yellow
    try {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction Stop
        Write-Host "Task '$taskName' removed successfully." -ForegroundColor Green
    } catch {
        Write-Host "Task '$taskName' not found or already removed." -ForegroundColor DarkGray
    }
    return
}

# 检查 start-all.ps1 是否存在
if (-not (Test-Path $startAllScript)) {
    Write-Host "ERROR: start-all.ps1 not found at: $startAllScript" -ForegroundColor Red
    exit 1
}

# 检查是否已有同名任务
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Task '$taskName' already exists. Removing and re-registering..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
}

# 构造 PowerShell 启动命令
$psCommand = "-NoProfile -ExecutionPolicy Bypass -File `"$startAllScript`""

# 创建 Task Scheduler 任务
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument $psCommand `
    -WorkingDirectory $projectRoot

# 触发器: 用户登录时触发
$trigger = New-ScheduledTaskTrigger -AtLogOn

# 设置: 允许任务在后台运行
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

# 注册任务 (以当前用户身份运行，无需密码)
$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

Write-Host "Registering Task Scheduler entry: $taskName" -ForegroundColor Cyan
Write-Host "  Trigger: At user logon" -ForegroundColor Gray
Write-Host "  Action:  powershell.exe -File $startAllScript" -ForegroundColor Gray
Write-Host "  WorkDir: $projectRoot" -ForegroundColor Gray

try {
    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Force | Out-Null

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "  Auto-start task registered!" -ForegroundColor Green
    Write-Host "  Task Name: $taskName" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Services will auto-start on next logon." -ForegroundColor Gray
    Write-Host "  To start now:  Get-ScheduledTask '$taskName' | Start-ScheduledTask" -ForegroundColor Gray
    Write-Host "  To remove:    .\scripts\install-autostart.ps1 -Remove" -ForegroundColor Gray
    Write-Host "========================================" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Failed to register task: $_" -ForegroundColor Red
    exit 1
}
