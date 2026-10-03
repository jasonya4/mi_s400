# 小米體脂計 S400 (MJTZC01YM) Win11 數據記錄與逆向解析系統

本專案實作在 Windows 11 下，透過藍牙 Low Energy (BLE) 與小米體脂計 S400 進行 GATT 通訊、米家 v2 認證握手與 CMTP 封包解密，自動擷取即時體重、穩定數據與雙頻 BIA 阻抗，並結合使用者參數逆向換算體脂、肌肉量、內臟脂肪等 10+ 項身體數據，自動寫入本機 SQLite 資料庫與 CSV 檔案。

---

## 專案結構

```text
mi_s400/
├── config.yaml               # 設備 MAC、BindKey、Token 與使用者基本資料
├── config.example.yaml       # 設定檔範本
├── run.bat                   # 一鍵啟動常駐監聽服務
├── history.bat               # 一鍵查看歷史量測記錄
├── dashboard.bat             # 一鍵開啟網頁圖表儀表板
├── probe_offline.bat         # 離線歷史數據試探工具 (方法 A)
├── get_token.bat             # 小米雲端 Token / BindKey 提取工具
├── main.py                   # 程式入口主流程
├── src/
│   ├── storage.py            # SQLite 與 CSV 雙軌資料持久化
│   ├── user_manager.py       # 多使用者體重自動匹配與 BIA 體脂逆向計算
│   └── notifier.py           # Windows 11 原生通知推播
├── data/
│   ├── measurements.db       # SQLite 資料庫
│   └── measurements.csv      # CSV 記錄檔
└── tools/
    ├── probe_offline.py      # MIoT 離線封包試探程式
    └── token_extractor/      # 開源 Token Extractor
```

---

## 快速使用

### 1. 啟動監聽記錄
雙擊執行 [`run.bat`](file:///d:/jason/github/mi_s400/run.bat)，或在命令提示字元執行：
```powershell
.\run.bat
```
看到提示後，**脫襪雙腳站上體脂計**喚醒藍牙。
* 體脂計喚醒後，程式會自動連線並在終端顯示即時跳動體重。
* 當數值穩定並測得雙頻阻抗後，程式會自動計算各項數據，印出完整表格、儲存並送出 Windows 通知。

### 2. 檢視歷史記錄與網頁圖表儀表板
* **終端機快速查看**：
  雙擊執行 [`history.bat`](file:///d:/jason/github/mi_s400/history.bat) 或在命令提示字元執行 `.\history.bat`。
* **網頁趨勢折線圖 (Web Dashboard)**：
  雙擊執行 [`dashboard.bat`](file:///d:/jason/github/mi_s400/dashboard.bat)，或直接在 Chrome 中開啟 [`index.html`](file:///d:/jason/github/mi_s400/index.html)。
  * 動態自資料庫提取數據，每頁以時間靠近排序呈現 **25 筆**。
  * 提供 **Next (下一頁 / 較舊 25 筆)** 與 **Prev (上一頁 / 較新 25 筆)** 分頁按鈕。
  * 各指標以不同顏色獨立折線呈現，並支援圖例自由開關與雙 Y 軸展示。

---

## 部署至 GitHub Pages

本專案之網頁圖表支援直接部署於 GitHub：
1. 將專案推送（Push）至您的 GitHub 儲存庫。
2. 進入 GitHub 專案頁面之 **Settings** $\rightarrow$ **Pages**。
3. **Build and deployment** 來源選擇 **Deploy from a branch**，分支選擇 `main` / `root`。
4. 儲存後即可獲得公開網址（例如 `https://<username>.github.io/mi_s400/`），在任何裝置的 Web Chrome 上直接開啟查看最新折線圖！

---

## 逆向解析說明

1. **認證協定**：
   * 採用米家 v2 GATT 認證協定，透過 AVDTP/CMTP 特徵值與體脂計交換隨機 Nonce，以 HKDF-SHA256 衍生會話金鑰（Session Keys），並使用 AES-CCM 解密即時資料流。
2. **阻抗與生理演算法**：
   * S400 硬體輸出為 50kHz 與 250kHz 雙頻阻抗。
   * 程式透過經驗擬合公式（以開源單頻公式為基底結合 App 數值校正），估算出體脂率、肌肉量、內臟脂肪等級、基礎代謝（BMR）與骨量（僅供趨勢參考，非官方閉源演算法）。
