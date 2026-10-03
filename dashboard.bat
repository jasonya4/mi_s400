@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在更新最新數據檔...
.\.venv\Scripts\python.exe -c "from src.storage import StorageManager; StorageManager().export_data_files()"
echo 正在瀏覽器中開啟圖表儀表板...
start "" "index.html"
