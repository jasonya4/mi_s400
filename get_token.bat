@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ====================================================
echo  Xiaomi Cloud Tokens Extractor (小米雲端金鑰提取器)
echo ====================================================
echo.
echo 提示：
echo 1. 帳號可輸入 小米 ID、Email 或 綁定手機號。
echo 2. 伺服器區域（Server）：
echo    - 台灣帳號請填：tw
echo    - 中國大陸帳號請填：cn
echo    - 新加坡請填：sg
echo    - 歐洲請填：de
echo    - 美國請填：us
echo.
.\.venv\Scripts\python.exe .\tools\token_extractor\token_extractor.py
echo.
pause
