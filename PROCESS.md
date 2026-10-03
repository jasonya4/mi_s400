# 小米體脂計 S400 (MJTZC01YM) Win11 數據逆向解析與儀表板全流程記錄

本文件完整記錄在 **Windows 11** 環境下，如何從零開始逆向解析 **小米體脂計 S400（型號：MJTZC01YM）** 的藍牙低功耗（BLE）加密協議，校正雙頻 BIA 生理演算法，建立本地資料庫，並製作符合米家 App 官方分級標準的動態網頁趨勢折線圖，最終發布至 GitHub 的完整過程。

---

## 目錄
1. [專案架構與背景目標](#1-專案架構與背景目標)
2. [階段一：設備金鑰與憑證提取](#2-階段一設備金鑰與憑證提取)
3. [階段二：BLE 通訊與米家 v2 協定逆向解密](#3-階段二ble-通訊與米家-v2-協定逆向解密)
4. [階段三：雙頻 BIA 生理演算法校準 (對齊官方 App)](#4-階段三雙頻-bia-生理演算法校準-對齊官方-app)
5. [階段四：本地數據庫與多使用者持久化](#5-階段四本地數據庫與多使用者持久化)
6. [階段五：動態 Web 折線圖儀表板開發](#6-階段五動態-web-折線圖儀表板開發)
7. [階段六：GitHub 部署與 GitHub Pages 啟用教學](#7-階段六github-部署與-github-pages-啟用教學)

---

## 1. 專案架構與背景目標

* **硬體設備**：小米體脂計 S400 (Xiaomi Body Composition Scale S400，代號 `yunmai.scales.ms104`，型號 `MJTZC01YM`)。
* **主要特性**：
  * 雙頻高低阻抗生物電阻分析（50kHz 細胞外液 + 250kHz 穿透細胞膜）。
  * 全程藍牙廣播與連線加密（MiBeacon V4/V5 + 米家 v2 GATT CMTP 加密通道）。
* **達成目標**：
  * 在 Windows 11 下透過原生藍牙自動攔截測量封包。
  * 還原即時跳動體重、穩定數據與雙頻阻抗。
  * 經由臨床演算法輸出體脂率、肌肉量、內臟脂肪、代謝年齡等完整指標。
  * 開發前端動態圖表，每頁 25 筆，具備 Next / Prev 分頁，支援在 Web Chrome 及 GitHub Pages 上直接開啟。

---

## 2. 階段一：設備金鑰與憑證提取

不同於舊款小米體脂計（Mi Scale 2）使用未加密廣播，S400 強制進行金鑰握手。

1. **提取工具**：引入開源工具 `Xiaomi-cloud-tokens-extractor`。
2. **獲取金鑰流程**：
   * 執行本專案提供的 `get_token.bat`。
   * 輸入米家綁定的小米帳號、密碼及伺服器區域（台灣為 `tw`，大陸為 `cn`）。
   * 自回傳的設備清單中獲取三項關鍵參數：
     * **MAC 地址**：例如 `AA:BB:CC:DD:EE:FF`
     * **BindKey**：32 字元（16 bytes）十六進位金鑰
     * **Token**：12 bytes 雲端登入金鑰
3. **儲存設定**：將上述資料填入本機 `config.yaml`（該檔案已加入 `.gitignore` 以防機密外洩，專案中保留 `config.example.yaml` 作為範本）。

---

## 3. 階段二：BLE 通訊與米家 v2 協定逆向解密

在 Windows 11 下調用原生 WinRT 藍牙 API（使用 `bleak` 函式庫）：

1. **主動連線架構（Active GATT Session）**：
   * 站上體脂計時，硬體喚醒廣播（UUID `0xFE95`）。
   * PC 端自動發起連線，訂閱 GATT 特徵值（UPNP `0x10`, AVDTP `0x19`, CMTP `0x1B`）。
2. **認證握手（Handshake）**：
   * 透過 AVDTP 與體脂計交換隨機數（Random Nonce）。
   * 經由 `HKDF-SHA256` 結合設備 Token 衍生出當次會話的會話金鑰（`dev_key`, `app_key`, `dev_iv`, `app_iv`）。
3. **CMTP 封包拼裝與 AES-CCM 解密**：
   * 監聽 CMTP 特徵值的通知數據，依照序號重組多幀數據。
   * 使用 AES-CCM 解密得到明文 CSV 封包：
     * **即時幀（Live Frame）**：`"weight_x10,stable_flag"`（例如 `"792,0"` 表示 79.2kg，測量中）。
     * **最終幀（Final Dump）**：包含體重、穩定狀態、內部 RTC 時間戳、低頻阻抗（50kHz）與高頻阻抗（250kHz）。

---

## 4. 階段三：體脂演算法（經驗擬合，非官方演算法）

> [!WARNING]
> 本專案的體脂公式**不是**小米官方演算法，而是「舊開源公式 + 用少量 App 數值手動擬合」的結果。數值僅供趨勢參考，可能與米家 App 有落差。

### 4.1 起點：開源舊公式
`xiaomi-s400-live` 內建的公式移植自舊款單頻體脂計（Mi Scale 2，`mnm-matin/miscale`），只使用一個阻抗值。拿來算 S400 時，和米家 App 差距明顯：

| 指標 | 舊開源公式 (77.9 kg) | 米家 App 顯示 |
| :--- | :---: | :---: |
| 體脂率 | 25.1 % | 23.4 % |
| 肌肉量 | 55.4 kg | 57.4 kg |
| 水分率 | 51.4 % | 57.4 % |
| 基礎代謝 | 1474 kcal | 1681 kcal |
| 內臟脂肪 | 16.7 | 8 |
| 體質年齡 | 37 歲 | 46 歲 |

### 4.2 實際做的調整（目前版本 `src/user_manager.py`）
| 指標 | 調整方式 | 性質 |
| :--- | :--- | :--- |
| 瘦體重 LBM | 舊公式結果 **+0.47 kg 固定偏移** | 用 1 筆資料擬合 |
| 體脂率 | `(體重 − LBM) / 體重` | 由 LBM 推導 |
| 水分率 | `LBM × 0.749 / 體重` | 係數為擬合值 |
| 基礎代謝 | Harris-Benedict 修訂版 − 8 kcal | 偏移為擬合值 |
| 內臟脂肪 | `(體脂 − 10)×0.35 + (BMI − 20)×0.55` | **自訂公式**，為了湊出 App 的 8 |
| 體質年齡 | `年齡 − (肌肉比例 − 0.70)×80` | **自訂公式**，為了湊出 App 的 46 |
| 評級標籤 | BMI 24~27.9 偏高、內臟脂肪 8~10 警戒等 | 依 App 顯示整理 |
| 身體類型 | BMI ≥ 25 且體脂 ≥ 23% → 肥胖 | 依 App 顯示整理 |

### 4.3 已知限制
* 只用**一筆** App 對照資料擬合，體重或體組成變化大時誤差可能變大。
* 對照資料可能配對錯誤：App 顯示 BMI 26.2（對應 79.2 kg），但擬合時把那組 App 數值當成 77.9 kg 那筆的結果。
* S400 回傳的兩個阻抗值目前只用了一個，尚未善用雙頻資訊。
* 要真正校準，需要累積 5~10 筆「同一次量測」的 App 數值與阻抗對照，再做迴歸。

---

## 4.5 進行中：離線歷史資料（siid 9）

S400 會在機身暫存未同步的量測。官方 MIoT 規格（[home.miot-spec.com/spec/yunmai.scales.ms104](https://home.miot-spec.com/spec/yunmai.scales.ms104)）列出相關服務：

| 服務 | 項目 | 說明 |
| :--- | :--- | :--- |
| siid 8 線上資料 | event 1 / event 2 | 即時體重 / 體脂測量過程（目前收到的就是這類） |
| siid 9 離線資料 | action 1 | Request to report offline data |
| | action 2 | End of reception（可能會清除秤內暫存，試探時**不送**） |
| | event 1 / event 2 | 逐筆回報 / 回報筆數 |
| siid 13 連線後同步 | action 1 / property 6 | sync / 離線訊息筆數 |

已解析出的明文格式（用實際收到的封包驗證，長度與規格編號都吻合）：
```text
5d | 20 | 0e 00 | 07 | 08   | 02 00 | 01     | 02 00 | 50 a0              | <80 bytes ASCII>
LL | ?  | seq   | op | siid | eiid  | nparam | piid  | type<<12 | length  | 值
```
→ `siid 8 / event 2 / piid 2` = 線上資料 / 體脂測量過程事件。

### 實測重大突破（首度成功實現雙向 MIoT 通訊）
在 2026-10-04 實測中，成功完成主機與 S400 之間的雙向指令交互：
1. **TX / RX 通道分離架構確立**：
   * **TX（主機發送控制）**：特徵值 `VEND1A`（`0000001a-...`）。秤端成功回覆 `RCV_RDY`（`00000101`）與 `RCV_OK`（`00000100`）。
   * **RX（秤端回報監聽）**：特徵值 `CMTP`（`0000001b-...`）。秤端在此通道推送加密封包。
2. **MIoT OpCode 與解密雙向驗證**：
   * 主機送出 `op 0x00 (get_property)` 查詢 `siid 13 / piid 6`（離線訊息筆數）。
   * 秤端成功回傳 `op 0x01 (get_property_rsp)`，解密確認狀態碼 `code=0`（成功），回報目前離線暫存筆數為 `0`！
3. **官方 MIoT 規格完整解析（`yunmai-ms104:1`）**：
   * `siid 13 / piid 6 (offline-msg-cnt)`：可讀屬性，回傳秤內累積未同步筆數。
   * `siid 9 / action 1 (request-offline-data)`：入參 `piid 4 (only-upload-count = 0)`，告知體脂計回傳全部歷史資料。
   * `siid 9 / event 1 (report-offline-data)`：出參 `piid 1`，格式與線上測量完全相同（80 bytes ASCII CSV 字串）。
   * `siid 9 / action 2 (end-of-reception)`：**試探腳本嚴格排除此指令**，絕不主動清空秤內資料。

### 離線資料驗證標準測試流程（SOP）
* **原理**：若量測時電腦或手機已連線，S400 會走線上模式（Online Mode, `siid 8`）即時串流體重，不會寫入離線暫存。必須在「離線無連線」狀態下量測，才會存入 Flash。
* **測試步驟**：
  1. 關閉手機藍牙，確保 `run.bat` 與 `probe_offline.bat` 皆處於關閉狀態。
  2. 裸足踩上 S400 進行完整量測（等候體重與體脂阻抗測試進度條完成）。
  3. 下秤，等候 5 秒讓 S400 螢幕自然熄滅（此時資料已寫入秤內 Flash 暫存）。
  4. 電腦開啟 Windows 藍牙，雙擊執行 `probe_offline.bat`。
  5. 輕踩一下 S400 喚醒廣播，腳本將自動查詢離線筆數（應顯示 $\ge 1$ 筆）並發送 `action 9.1` 抓回歷史數據！

---

## 5. 階段四：本地數據庫與多使用者持久化

1. **SQLite 資料庫（`data/measurements.db`）**：
   * 建立結構化欄位保存歷次測量數據（時間戳、體重、雙頻阻抗、各項生理指標、原始十六進位封包）。
2. **CSV 雙軌備份（`data/measurements.csv`）**：
   * 每次測量完成自動追加，便於使用 Excel 或 Google 試算表檢視。
3. **自動匯出前端檔案**：
   * 測量完成後，自動更新 `data/measurements.json` 與 `data/measurements.js`，供前端視覺化儀表板讀取。

---

## 6. 階段五：動態 Web 折線圖儀表板開發

在專案根目錄建立 [`index.html`](file:///d:/jason/github/mi_s400/index.html)，具備以下特點：

1. **Apache ECharts 多色彩折線圖**：
   * 水平軸（X 軸）：時間戳（`YYYY-MM-DD HH:mm`）。
   * 垂直軸（Y 軸）：各項數據指標，右側專屬 Y 軸支援基礎代謝率（kcal）。
   * 各指標獨立色彩：
     * 體重（鮮藍色 `#3b82f6`）
     * 體脂率（活力橙 `#f97316`）
     * 肌肉量（翡翠綠 `#10b981`）
     * 水分率（天藍色 `#06b6d4`）
     * BMI（紫色 `#8b5cf6`）
     * 內臟脂肪（紅色 `#ef4444`）
     * 基礎代謝（琥珀金 `#eab308`，右軸）
     * 代謝年齡（玫粉色 `#ec4899`）
2. **動態提取與 25 筆分頁（Next / Prev）**：
   * 預設以最新時間優先排序，每頁載入 **25 筆**。
   * 超過 25 筆時，可點擊 **`較舊 25 筆 (Next) ▶`** 或 **`◀ 較新 25 筆 (Prev)`** 翻頁瀏覽。
3. **免伺服器與跨域防護（Chrome 友善設計）**：
   * 採用雙軌載入：
     * 在 GitHub Pages（HTTP/HTTPS）環境：使用 `fetch('data/measurements.json')`。
     * 在本機以 Chrome 點開 `index.html`（`file:///`）：透過預先載入的 `data/measurements.js` 自動填入數據，完全不被 Chrome 本地檔案 CORS 政策阻擋。

---

## 7. 階段六：GitHub 部署與 GitHub Pages 啟用教學

### 步驟 A：將專案推送至 GitHub
在專案根目錄中執行：
```powershell
# 1. 初始化 Git 儲存庫並加入檔案
git init
git add .
git commit -m "feat: 小米體脂計 S400 逆向記錄系統與動態折線圖儀表板"

# 2. 透過 GitHub CLI 建立並推送到遠端儲存庫
gh repo create mi_s400 --public --source=. --remote=origin --push
```

### 步驟 B：啟用 GitHub Pages (讓 Chrome 直接線上讀取)
1. 開啟瀏覽器進入儲存庫：`https://github.com/jasonya4/mi_s400`
2. 點擊頂部 **Settings**（設定） $\rightarrow$ 左側選單點擊 **Pages**。
3. 在 **Build and deployment** 區塊：
   * **Source** 選擇：`Deploy from a branch`
   * **Branch** 選擇：`main`，資料夾選擇 `/ (root)`。
   * 點擊 **Save**。
4. 等候約 1 分鐘，頁面頂部將顯示專屬網址：
   > 🌐 **`https://jasonya4.github.io/mi_s400/`**
5. 現在您可以在任何電腦或手機的 Web Chrome 瀏覽器直接開啟該網址，即時查閱最新體脂趨勢折線圖！

---

## 日常操作指令總結

| 功能 | 操作方式 | 說明 |
| :--- | :--- | :--- |
| **開始量測記錄** | 雙擊 `run.bat` | 啟動 BLE 背景監聽，雙腳站上體脂計即可自動記錄 |
| **查看終端歷史** | 雙擊 `history.bat` | 在命令提示字元列印最近 10 筆數據 |
| **開啟圖表儀表板** | 雙擊 `dashboard.bat` | 自動更新數據並在 Chrome 中開啟趨勢折線圖 |
| **重新提取金鑰** | 雙擊 `get_token.bat` | 若體脂計在米家 App 重新配對過，可重新提取金鑰 |
