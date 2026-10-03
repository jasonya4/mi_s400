@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo   S400 離線歷史資料同步與試探 (唯讀，不刪除秤內資料)
echo   * 關閉手機藍牙或米家 App
echo   * 看到搜尋提示後站上體脂計
echo ============================================================
.\.venv\Scripts\python.exe tools\probe_offline.py
pause
