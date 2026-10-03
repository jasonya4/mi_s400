@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo   正在啟動 Xiaomi 體脂計 S400 記錄服務 (常駐監聽模式)
echo   按 Ctrl+C 可停止服務
echo ============================================================
.\.venv\Scripts\python.exe main.py
pause
