# 股神 - 一键停止
Write-Host "正在停止股神全部服务 ..." -ForegroundColor Yellow
foreach ($port in 3000, 8000, 6379, 27017) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Host "停止端口 $port 的进程 $($_.OwningProcess)" -ForegroundColor Gray
        Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
    }
}
Start-Sleep -Seconds 2
Write-Host ""
Write-Host "股神已全部停止" -ForegroundColor Green
Write-Host ""
Read-Host "按回车键关闭本窗口"