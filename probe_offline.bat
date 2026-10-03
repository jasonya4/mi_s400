@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo   S400 離線資料試探 (唯讀，不會刪除秤內資料)
echo   1. 請先關閉手機藍牙或米家 App
echo   2. 看到「正在搜尋」後站上體脂計
echo ============================================================
.\.venv\Scripts\python.exe tools\probe_offline.py
pause
