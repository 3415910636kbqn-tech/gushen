# 股神 - TradingAgents 中文增强版 一键启动
# 双击桌面快捷方式即可，服务在后台运行
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force $logDir -ErrorAction SilentlyContinue | Out-Null

function Test-Port([int]$port) {
    return [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  股神 - TradingAgents 中文增强版" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 1. MongoDB
if (-not (Test-Port 27017)) {
    Write-Host "[1/4] 启动 MongoDB ..." -ForegroundColor Yellow
    Start-Process -FilePath (Join-Path $root "vendors\mongodb\bin\mongod.exe") `
        -ArgumentList "--dbpath", (Join-Path $root "data\mongodb\db"), "--port", "27017", "--bind_ip", "127.0.0.1", "--auth" `
        -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir "mongod.out.log") -RedirectStandardError (Join-Path $logDir "mongod.err.log")
    Start-Sleep -Seconds 5
} else {
    Write-Host "[1/4] MongoDB 已在运行" -ForegroundColor Green
}

# 2. Redis
if (-not (Test-Port 6379)) {
    Write-Host "[2/4] 启动 Redis ..." -ForegroundColor Yellow
    Start-Process -FilePath (Join-Path $root "vendors\redis\redis-server.exe") `
        -ArgumentList "--port", "6379", "--requirepass", "tradingagents123", "--dir", (Join-Path $root "data\redis") `
        -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir "redis.out.log") -RedirectStandardError (Join-Path $logDir "redis.err.log")
    Start-Sleep -Seconds 3
} else {
    Write-Host "[2/4] Redis 已在运行" -ForegroundColor Green
}

# 3. 后端（生产模式：API + 前端页面，单端口 8000）
if (-not (Test-Port 8000)) {
    Write-Host "[3/4] 启动后端，首次启动需 30-60 秒 ..." -ForegroundColor Yellow
    $env:PYTHONIOENCODING = "utf-8"; $env:PYTHONUTF8 = "1"; $env:PYTHONUNBUFFERED = "1"
    Start-Process -FilePath (Join-Path $root "env\Scripts\python.exe") `
        -ArgumentList "serve_prod.py" -WorkingDirectory $root -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDir "backend.out.log") -RedirectStandardError (Join-Path $logDir "backend.err.log")
} else {
    Write-Host "[3/4] 后端已在运行" -ForegroundColor Green
}

# 4. 等待后端就绪
Write-Host "[4/4] 等待服务就绪 ..." -ForegroundColor Yellow
$ready = $false
for ($i = 0; $i -lt 40; $i++) {
    try {
        $null = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/health" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        $ready = $true
        break
    } catch {
        Start-Sleep -Seconds 3
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
if ($ready) {
    Write-Host "  股神已就绪！" -ForegroundColor Green
} else {
    Write-Host "  后端仍在初始化，稍后请手动刷新" -ForegroundColor Yellow
}
Write-Host "  网址: http://localhost:8000" -ForegroundColor White
Write-Host "  账号: admin （密码请用你改过的）" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Start-Process "http://localhost:8000"
Write-Host "提示：关闭本窗口不影响服务运行" -ForegroundColor DarkGray
Write-Host "停止服务：双击桌面【停止股神】" -ForegroundColor DarkGray
Write-Host ""
Read-Host "按回车键关闭本窗口"