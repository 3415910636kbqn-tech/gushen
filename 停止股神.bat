@echo off
title 停止股神
echo 正在停止股神全部服务...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /c:":3000" ^| findstr /c:"LISTENING"') do (taskkill /f /pid %%a >nul 2>&1)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /c:":8000" ^| findstr /c:"LISTENING"') do (taskkill /f /pid %%a >nul 2>&1)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /c:":6379" ^| findstr /c:"LISTENING"') do (taskkill /f /pid %%a >nul 2>&1)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /c:":27017" ^| findstr /c:"LISTENING"') do (taskkill /f /pid %%a >nul 2>&1)
echo.
echo 股神已全部停止
pause