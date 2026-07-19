# Windows 打包指南 — margin-maintenance-tracker

本文件給 **Windows 電腦上的 Claude Code**（或依此文件手動操作的人）使用，目的是把本專案打包成 Windows 可雙擊執行的 `.exe`，並可選配再包成安裝程式。

> **重要前提**：本專案在 macOS 開發並驗證完成（現價 / N 日均價 / 融資餘額 / 維持率皆已跑通）。但 **Windows `.exe` 必須在 Windows 機器上打包**——PyInstaller 不支援跨平台交叉編譯，macOS 無法產出 Windows `.exe`。因此以下所有步驟都要在這台 Windows 機器上執行。

---

## 前置需求

- 作業系統：Windows 10 / 11
- Python：**3.11 以上**（打開命令提示字元或 PowerShell 執行 `python --version` 確認；若無 Python 請先至 https://www.python.org/downloads/ 安裝，安裝時務必勾選「Add python.exe to PATH」）
- 本文件假設你已在**專案根目錄**（也就是本檔 `BUILD_WINDOWS.md` 所在的資料夾）開啟終端機執行以下指令
- 全程指令以 PowerShell 語法為主；若使用命令提示字元（cmd.exe），啟用虛擬環境的指令略有不同，已在步驟中註明

---

## 步驟 1：建立虛擬環境

```powershell
python -m venv .venv
```

啟用虛擬環境：

```powershell
# PowerShell
.venv\Scripts\Activate.ps1

# 或命令提示字元 (cmd.exe)
.venv\Scripts\activate.bat
```

啟用成功後，提示字元前方會出現 `(.venv)` 字樣。

> 若 PowerShell 出現「無法載入，因為這個系統上已停用指令碼執行」錯誤，執行：
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
> ```
> 再重新啟用虛擬環境。

---

## 步驟 2：安裝依賴

```powershell
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller
```

> `pyinstaller` 僅用於打包，不列在 `requirements.txt` 的執行期依賴中，此處手動額外安裝。

---

## 步驟 3：本機先驗證（打包前）

在打包前，先確認專案在 Windows 上能正常運作：

```powershell
python run.py
```

終端機應顯示 uvicorn 啟動訊息（監聽 `127.0.0.1:8000`）。接著打開瀏覽器輸入：

```
http://127.0.0.1:8000
```

在查詢框輸入股票代號 `2330`，確認能查出現價、N 日均價、融資餘額與維持率（需要網路連線，即時向 TWSE / TPEx / Yahoo 抓資料）。

確認無誤後，回到終端機按 `Ctrl+C` 停止服務，再進行下一步打包。

---

## 步驟 4：PyInstaller 打包（onefile）

執行以下完整指令（**建議整段複製貼上**，中間不要換行拆開）：

```powershell
pyinstaller --onefile --name margin-maintenance-tracker --add-data "static;static" --add-data "app/data;app/data" --collect-submodules uvicorn --hidden-import uvicorn.logging --hidden-import uvicorn.loops.auto --hidden-import uvicorn.protocols.http.auto --hidden-import uvicorn.protocols.websockets.auto --hidden-import uvicorn.lifespan.on --noconfirm launcher.py
```

### 指令參數說明

| 參數 | 說明 |
|---|---|
| `--onefile` | 打包成單一 `.exe` 檔案 |
| `--name margin-maintenance-tracker` | 產出檔名為 `margin-maintenance-tracker.exe` |
| `--add-data "static;static"` | 把前端靜態檔（`static/` 目錄）打包進 exe。**注意：Windows 上 `--add-data` 的來源與目的地之間用「分號 `;`」分隔**，這點與 macOS/Linux 上使用「冒號 `:`」不同（例如 macOS 會寫成 `"static:static"`），若沿用 macOS 語法在 Windows 上會打包失敗，務必用分號 |
| `--add-data "app/data;app/data"` | 把融資成本種子檔（`app/data/margin_cost_seed.json`，加權融資成本的起算基準）打包進 exe。缺這行的話，融資成本會全部退回 N 日均價簡易估計。同樣用分號分隔 |
| `--collect-submodules uvicorn` | 完整收錄 uvicorn 子模組，避免打包後缺元件 |
| `--hidden-import uvicorn.logging` 等 | uvicorn 部分模組是動態載入，PyInstaller 靜態分析抓不到，需手動補 `--hidden-import` |
| `--noconfirm` | 若 `dist/` 或 `build/` 已存在舊產物，直接覆蓋不詢問 |
| `launcher.py` | 打包進入點檔案（**不是** `run.py`；`launcher.py` 負責啟動 server + 自動開瀏覽器，是給終端使用者用的進入點） |

### 產出位置

打包完成後，可執行檔會產生在：

```
dist\margin-maintenance-tracker.exe
```

雙擊該檔案即會：
1. 在背景啟動本機 server（監聽 `127.0.0.1` 上的某個埠號）
2. 自動偵測 `/api/health` 就緒
3. 自動開啟預設瀏覽器並導向服務網址

> 打包過程會另外產生 `build\` 資料夾與 `margin-maintenance-tracker.spec` 檔案，這些是中間產物，不影響最終 `dist\margin-maintenance-tracker.exe` 的運作，可保留備查或刪除皆可。

---

## 步驟 5（選配）：用 Inno Setup 包成安裝程式

如果希望交付「安裝程式」而非單一 exe（可建立開始選單捷徑、桌面捷徑、解除安裝功能），可使用 [Inno Setup](https://jrsoftware.org/isinfo.php)（免費）。

1. 下載並安裝 Inno Setup（含 Inno Setup Compiler，簡稱 ISCC）
2. 在專案根目錄建立 `installer.iss`，內容如下（最小範本，可依需求調整）：

```ini
; installer.iss — margin-maintenance-tracker 安裝程式範本
[Setup]
AppName=融資維持率查詢工具
AppVersion=1.0.0
AppPublisher=margin-maintenance-tracker
DefaultDirName={autopf}\MarginMaintenanceTracker
DefaultGroupName=融資維持率查詢工具
OutputDir=installer_output
OutputBaseFilename=margin-maintenance-tracker-setup
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "dist\margin-maintenance-tracker.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\融資維持率查詢工具"; Filename: "{app}\margin-maintenance-tracker.exe"
Name: "{group}\解除安裝"; Filename: "{uninstallexe}"
Name: "{autodesktop}\融資維持率查詢工具"; Filename: "{app}\margin-maintenance-tracker.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "建立桌面捷徑"; GroupDescription: "額外圖示:"

[Run]
Filename: "{app}\margin-maintenance-tracker.exe"; Description: "立即啟動"; Flags: nowait postinstall skipifsilent
```

3. 用 Inno Setup Compiler 開啟 `installer.iss`，點選「Compile」（或用命令列 `ISCC installer.iss`）
4. 產出的安裝程式會在 `installer_output\margin-maintenance-tracker-setup.exe`，可交付給終端使用者直接安裝

> 此步驟為選配，若只需要單一可攜式 exe，做到步驟 4 即可交付。

---

## 重要提醒

- **Mac 無法交叉編譯 Windows exe**：本打包流程（步驟 1–5）必須在 Windows 機器上執行，macOS 端只能提供原始碼與本文件。
- **`launcher.py` 已設計為 frozen 相容**：啟動 uvicorn 時是「傳入 app 物件」（`uvicorn.run(app, ...)`），而非用字串 `"app.main:app"` 動態 import；因為 PyInstaller 打包後的 frozen 環境無法用字串路徑動態載入模組，若沿用字串寫法會在 exe 啟動時失敗。此設計已內建於 `launcher.py`，打包時不需額外處理，但若之後修改 `launcher.py` 請勿改回字串 import 寫法。
- **若打包後的 exe 啟動時報缺模組（`ModuleNotFoundError`）**：多半是動態載入的子模組沒被 PyInstaller 靜態分析抓到。解法是在打包指令中補上對應的 `--hidden-import 模組名稱`，例如缺 `uvicorn.protocols.websockets.wsproto_impl` 就補：
  ```powershell
  --hidden-import uvicorn.protocols.websockets.wsproto_impl
  ```
  補完後重新執行步驟 4 的完整指令即可。
- **需要連網**：本工具即時向 TWSE（證交所）、TPEx（櫃買中心）、Yahoo Finance 抓取資料，Windows 執行環境務必能連上外網，否則查詢會顯示「無資料」。
- **防毒軟體誤判**：PyInstaller 打包的 onefile exe 有時會被部分防毒軟體誤判為可疑檔案（常見於未簽章的自製 exe）。若發生，屬已知的 PyInstaller 通病，可將 exe 加入防毒軟體白名單，或後續考慮加上程式碼簽章（不在本次交付範圍）。

---

## 疑難排解

| 問題現象 | 可能原因 | 解法 |
|---|---|---|
| `pyinstaller: command not found` / 找不到指令 | 未安裝或虛擬環境未啟用 | 確認 `(.venv)` 已顯示於提示字元前，重新 `pip install pyinstaller` |
| 打包成功但雙擊 exe 閃退、無視窗無瀏覽器 | 內部例外未輸出到畫面 | 改用終端機執行 `dist\margin-maintenance-tracker.exe`（不要用雙擊），觀察終端機印出的錯誤訊息 |
| 啟動後瀏覽器打開但顯示「無法連上此網站」 | server 尚未就緒就開瀏覽器，或 port 被占用 | `launcher.py` 內建等待 `/api/health` 就緒與自動找空閒 port 邏輯；若仍失敗，稍等數秒手動重整瀏覽器，或檢查是否有舊的 exe 進程未關閉（工作管理員結束後重試） |
| `ModuleNotFoundError: No module named 'uvicorn.xxx'` | uvicorn 動態載入模組未被收錄 | 補 `--hidden-import uvicorn.xxx` 後依步驟 4 重新打包（見上方「重要提醒」） |
| 打包後前端頁面空白 / 404 | `--add-data` 分隔符寫錯或路徑打錯 | Windows 必須用分號 `"static;static"`，且需在**專案根目錄**執行打包指令，確認 `static\` 資料夾確實存在於根目錄 |
| `pip install -r requirements.txt` 失敗，出現版本衝突 | Python 版本過舊或 pip 過舊 | 確認 `python --version` 為 3.11 以上；執行 `pip install --upgrade pip` 後重試 |
| 中文路徑或使用者名稱導致打包失敗 | PyInstaller 對非 ASCII 路徑偶有相容性問題 | 將專案資料夾移到不含中文的路徑（如 `C:\projects\margin-maintenance-tracker`）後重新打包 |
| 打包後執行變得很慢（每次啟動要等好幾秒） | `--onefile` 模式每次執行需先解壓縮到暫存目錄，屬正常現象 | 若需要更快啟動速度，可改用 `--onedir`（產出資料夾而非單一檔案），但交付形式改變，需額外評估是否符合需求 |

---

## 完成後的交付內容

打包完成後，建議交付以下任一形式：

- **最小交付**：`dist\margin-maintenance-tracker.exe` 單一檔案，使用者雙擊即可執行（需連網）
- **完整交付（選配）**：`installer_output\margin-maintenance-tracker-setup.exe` 安裝程式，使用者執行後建立開始選單/桌面捷徑

兩者皆不需要使用者另外安裝 Python 或任何依賴，因為所有依賴已封裝於 exe 內。
