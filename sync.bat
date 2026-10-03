@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo   S400 離線歷史數據一鍵同步工具
echo   * 請先關閉手機藍牙或米家 App
echo   * 看到搜尋提示後，單腳輕踩體脂計喚醒藍牙廣播
echo ============================================================
.\.venv\Scripts\python.exe tools\probe_offline.py
pause
