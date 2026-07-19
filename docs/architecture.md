# 系統架構文件 — margin-maintenance-tracker

## 專案類型
- 主要：web-fullstack（FastAPI 後端 + 純前端單頁，後端 serve static）
- 次要：data-science（資料抓取 adapter + 維持率計算）
- 根目錄：`src/margin-maintenance-tracker/`（下稱 `$PRJ`）

## 1. 分層架構
- L5 前端（static/）：純 HTML/CSS/JS 單頁，由 FastAPI serve；查詢表單 / 結果卡片 / 降級 / N值調整 / 警戒著色
- L4 API 端點層（app/routes/）：`/api/maintenance`、`/api/industry`(選配)、`/api/health`、static mount
- L3 服務/計算層（app/services/）：maintenance_service(編排)、average(N日均價+fallback)、calculator(公式+警戒)、industry_service(選配)
- L2 Adapter 層（app/adapters/）：price(MIS)、history_official(STOCK_DAY/tradingStock)、history_yahoo、margin(MI_MARGN/tpex)、market(探測)。**唯一對外 httpx 出口**
- L1 基礎設施（app/config.py, http_client.py, utils/, models.py）：常數/URL/Header、共用 httpx client、日期(ROC/AD)、交易時段、代號驗證、降級 helper、Pydantic schema

### 資料流（單股主流程）
使用者輸入代號+N → 前端 `GET /api/maintenance?code=2330&n=20` → routes/maintenance → services/maintenance_service.get_stock_maintenance：
1. validate_stock_code（91 開頭 → 422）
2. detect_market（探測 tse/otc）
3. asyncio.gather 並行且各自 try/except 降級：a) fetch_price b) get_n_day_average（官方失敗→Yahoo） c) fetch_margin（取不到→無資料）
4. compute_maintenance_ratio(price, n_avg, 0.6)
5. classify_warning(ratio)
6. 組 MaintenanceResponse（每欄位獨立 status，缺一不整體失敗）
→ 前端 render 結果卡片 / 逐欄位降級

## 2. 目錄結構
```
$PRJ/
├── app/
│   ├── main.py                # create_app：掛 router + mount static + lifespan + 全域 exception handler
│   ├── config.py              # MARGIN_RATE=0.6 DEFAULT_N=20 N_MIN=1 N_MAX=250 WARN_THRESHOLD=130 HTTP_TIMEOUT=8 URL/Header resolve_base_dir()
│   ├── http_client.py         # 共用 httpx.AsyncClient 生命週期
│   ├── models.py              # Pydantic：FieldStatus/PriceBlock/AverageBlock/MarginBlock/RatioBlock/MaintenanceResponse/IndustryResponse/ErrorResponse
│   ├── routes/{maintenance,industry,health}.py
│   ├── adapters/{price,history_official,history_yahoo,margin,market}.py
│   ├── services/{maintenance_service,average,calculator,industry_service}.py
│   └── utils/{dates,trading_session,codes,errors}.py
├── static/
│   ├── index.html
│   ├── css/style.css
│   └── js/{api,render,app}.js
├── tests/  (conftest + 各層 test_*.py)
├── docs/  (requirements-spec.md, data-sources-verified.md, architecture.md)
├── log/
├── run.py            # 開發進入點 uvicorn app.main:app
├── launcher.py       # PyInstaller exe 進入點：起 server + 開瀏覽器 + 找空閒 port
├── requirements.txt
├── pyproject.toml
├── BUILD_WINDOWS.md
└── README.md
```
單頁 serve：main.py 用 `app.mount("/", StaticFiles(directory=resolve_base_dir()/"static", html=True))` 掛最後（router 先註冊），前端全走同源 `/api/*` 天然解 CORS。打包時 static 以 `--add-data`，路徑以 `sys._MEIPASS` 解析（config.resolve_base_dir）。

## 3. Function 拆解（35 個，型別 typing 表示；adapter 皆 async；對外請求皆 try/except → 降級結構，不裸拋）

### L1 基礎
- **FN-001 config**（app/config.py）：常數 + `Settings` + `resolve_base_dir()->Path`（判斷 `sys._MEIPASS` 或專案根）。相依無。F-005/002/009
- **FN-002 get_http_client/close_http_client**（app/http_client.py）：單例 AsyncClient(timeout=8, headers=DEFAULT_HEADERS)，lifespan 建立/關閉。相依 001
- **FN-003 Pydantic schema**（app/models.py）：FieldStatus(ok/no_data/uncomputable)、各 Block、MaintenanceResponse、IndustryResponse、ErrorResponse。每 block 含 status/source/as_of。F-006/002/003/004/005
- **FN-004 roc_to_date/date_to_roc/date_to_ad_slash/date_to_ymd**（utils/dates.py）：ROC↔AD；`date_to_ad_slash->"2026/07/01"`(TPEx)；`date_to_ymd->"20260701"`(TWSE)。F-003/004
- **FN-005 months_to_fetch**（utils/dates.py）：`(n,today)->list[date]`，回推足以覆蓋 N 交易日的月份（ceil(n/18)+1，最少 2 個月）。F-003
- **FN-006 detect_session**（utils/trading_session.py）：`(now|None)->"intraday"|"closed"`，Asia/Taipei 09:00–13:30 且週一~五。F-002
- **FN-007 validate_stock_code**（utils/codes.py）：正規化 4 碼數字；91 開頭 raise CodeError；非法 raise。F-001/007
- **FN-008 降級 helper**（utils/errors.py）：`no_data/uncomputable/safe_block(coro)` 統一產生降級結構並捕例外。F-002/004/005/006

### L2 Adapter
- **FN-009 detect_market**（adapters/market.py）：先試 `tse_{code}.tw` MIS，msgArray 非空即 tse；否則試 otc；皆空 None。採探測法（免維護對照表），結果單次請求內傳遞不重複探測。相依 001/002
- **FN-010 fetch_price**（adapters/price.py）：MIS `getStockInfo?ex_ch={market}_{code}.tw`（帶 Referer）；取 z；`z=="-"` fallback (a+b)/2 中間價→y 昨收，標 fallback；price_type 依 session；name 取 n。→PriceBlock。相依 001/006/008
- **FN-011 fetch_history_twse**（adapters/history_official.py）：STOCK_DAY(date=YYYYMM01)，data[] 日期 idx0(ROC)/收盤 idx6，去逗號，"--" 略過。→list[(date,float)] 升序。相依 001/004
- **FN-012 fetch_history_tpex**（adapters/history_official.py）：tradingStock(date=YYYY/MM/DD 西元)，tables[0].data[] 日期 idx0/收盤 idx6。相依 001/004
- **FN-013 fetch_history_official**（adapters/history_official.py）：依 market 選 011/012，對 months_to_fetch 逐月合併去重排序；全空回 []。相依 005/011/012
- **FN-014 fetch_history_yahoo**（adapters/history_yahoo.py）：SFX=TW/TWO，chart range=3mo&interval=1d，zip timestamp+close 過濾 null，epoch→台北 date。相依 001
- **FN-015 fetch_margin**（adapters/margin.py）：上市 MI_MARGN(selectType=ALL) tables[1] 逐檔比對代號 idx0 取今日餘額 idx6，當日無表回退最多 5 交易日；上櫃 tpex margin(date=YYYY/MM/DD) tables[0].data 代號 idx0/資餘額 idx6，取不到→no_data。→MarginBlock。相依 001/004/008

### L3 服務/計算
- **FN-016 get_n_day_average**（services/average.py）：先 fetch_history_official，空/不足則 fetch_history_yahoo(標 source=Yahoo)；取最近 N 筆→compute_average；不足 N insufficient=True+note；皆無→no_data。→AverageBlock。相依 013/014/017/008
- **FN-017 compute_average**（services/average.py）：純函式，尾端 N 筆算術平均(四捨五入2位)，空→(None,[])。相依無
- **FN-018 compute_maintenance_ratio**（services/calculator.py）：純函式 `price/(n_avg*rate)*100` 四捨五入2位；n_avg None/0 或 price None → None（不除，避免 Inf/NaN）。相依 001
- **FN-019 classify_warning**（services/calculator.py）：`<130 danger`、130–166 warn、`>166 safe`、None→na。相依 001
- **FN-020 get_stock_maintenance**（services/maintenance_service.py）：主編排。validate→clamp N(1~250)→detect_session→detect_market(None→422 not_found)→asyncio.gather(price,average,margin, return_exceptions=True) 各自降級→ratio+warning→組 MaintenanceResponse(含 formula 三值+generated_at)。相依 002/006/007/009/010/015/016/018/019/008
- **FN-021 compute_industry_maintenance**（services/industry_service.py，選配）：以融資清單為成分股(排除 91)，逐檔取現價/均價/資餘，套 `Σ(收盤×資餘)/Σ(均價×資餘×0.6)×100`，缺資料排除計 excluded，上市/上櫃分開，Semaphore 節流。相依 010/015/016/007

### L4 端點
- **FN-022 create_app+lifespan+static mount**（app/main.py）：建 app，lifespan get/close client，include_router 三個(先)，最後 mount static，全域 exception handler 回 ErrorResponse JSON(不裸 500)。相依 001/002/023/024/025
- **FN-023 route_maintenance**（routes/maintenance.py）：query code/n=DEFAULT_N；薄 handler→get_stock_maintenance；代號錯→422。相依 020/003/002
- **FN-024 route_health**（routes/health.py）：回 `{status,service,time}`。相依無
- **FN-025 route_industry**（routes/industry.py，選配）：query market/n→compute_industry_maintenance。相依 021

### L5 前端
- **FN-026 index.html**：表單(代號 input、N input 預設20、查詢鈕)、loading、`#result`、`#error`、免責說明「融資成本以 N 日均價推估，非真實成本」、選配產業區。相依無
- **FN-027 apiGetMaintenance/apiGetIndustry**（js/api.js）：同源 fetch `/api/*`，non-2xx 解析 ErrorResponse 拋出。相依無
- **FN-028 renderResult**（js/render.js）：卡片—代號/名稱、現價(即時/收盤標籤)、N日均價(區間+不足註記)、融資餘額(日期)、維持率大字、公式三值、來源+時間戳；逐欄位讀 status 降級(no_data→無資料、uncomputable→無法計算)。相依 030
- **FN-029 renderError/showLoading**（js/render.js）：整體錯誤與 loading，disable 按鈕防重送。相依無
- **FN-030 warningClass**（js/render.js）：danger→紅(<130% 追繳)、warn→橘、safe→綠、na→灰。相依 031
- **FN-031 style.css**：卡片、維持率大字、警戒色、即時/收盤標籤、loading。相依無
- **FN-032 bootstrap**（js/app.js）：綁 submit/N 變更、前端驗證、showLoading→api→render。相依 027/028/029

### 進入點/打包
- **FN-033 run.py**：uvicorn app.main:app（127.0.0.1:8000）。開發啟動 `uv run run.py`。相依 022
- **FN-034 launcher.main**（launcher.py）：起 uvicorn(thread)+探測 /api/health 就緒後 webbrowser.open+找空閒 port；跨平台(標準庫)；static 以 resolve_base_dir。相依 001/022
- **FN-035 依賴/打包文件**：requirements.txt(fastapi/uvicorn[standard]/httpx/pydantic)、pyproject.toml、BUILD_WINDOWS.md(PyInstaller onefile `--add-data "static;static"` Windows 分號、`--name margin-maintenance-tracker`、進入點 launcher.py、venv、選配 Inno Setup、明示 exe 須在 Windows 產出)、README.md。相依 034

## 4. 並行開發批次
- **批1 基礎(無相依)**：FN-001~008 ‖ 前端 FN-026/031/027（契約已定）
- **批2 Adapter**：FN-009~015 ‖ 前端 FN-029/030
- **批3 服務/計算**：FN-016~019 ‖ 前端 FN-028/032
- **批4 編排/端點**：FN-020/022/023/024 + 選配 FN-021/025
- **批5 進入點/打包**：FN-033/034/035

批2 五個 adapter 完全獨立並行；前端鏈與後端全程平行；選配 FN-021/025 排最後不阻塞 MVP。

## 5. 錯誤降級策略（集中於 utils/errors.py）
原則：**單股查詢永不回 500；子資料失敗只降級該欄位。**
- 代號格式錯/91 → 422 ErrorResponse
- 探測不到市場 → 422 not_found
- 現價 z="-" → fallback 中間價/昨收 標 fallback
- 現價端點失敗 → PriceBlock no_data，其餘照常
- 官方歷史全失敗 → 自動 Yahoo fallback 標 source
- 歷史全無 → AverageBlock no_data
- 歷史不足 N → insufficient+note
- N日均價 0/None → Ratio uncomputable(非 NaN/Inf)
- 融資取不到(尤上櫃) → MarginBlock no_data，不影響維持率
- adapter 拋例外 → gather(return_exceptions=True)+safe_block 捕捉降級
- 未預期例外 → 全域 handler → ErrorResponse JSON(不外洩堆疊)
- 逾時 → httpx timeout=8s → no_data

## 6. API 契約
### GET /api/maintenance?code=2330&n=20 (200)
```json
{ "code":"2330","name":"台積電","market":"tse","session":"intraday","n_requested":20,
  "price":{"value":2440.0,"price_type":"即時","is_fallback":false,"prev_close":2435.0,"as_of":"13:25:07 / 20260715","source":"TWSE-MIS","status":"ok"},
  "average":{"value":2380.15,"count":20,"start":"2026-06-16","end":"2026-07-15","n_requested":20,"insufficient":false,"note":null,"source":"TWSE官方","status":"ok"},
  "margin":{"balance_lots":25314,"as_of":"2026-07-14","source":"TWSE-MI_MARGN","status":"ok"},
  "ratio":{"value":170.94,"warning":"safe","formula":{"price":2440.0,"n_day_avg":2380.15,"margin_rate":0.6,"expression":"2440.0 / (2380.15 * 0.6) * 100"},"status":"ok"},
  "generated_at":"2026-07-15T13:25:08+08:00" }
```
### 降級：margin no_data / average uncomputable → ratio uncomputable(value:null, warning:"na", status:"uncomputable")
### ErrorResponse(422)：`{"error":"invalid_code","message":"代號需為 4 碼數字，且不支援 91 開頭","code":"9100"}`
### GET /api/health(200)：`{"status":"ok","service":"margin-maintenance-tracker","time":...}`
### GET /api/industry?market=tse&n=20(選配,200)：`{"market":"tse","ratio":158.42,"constituents":912,"excluded":37,"note":"...","status":"ok"}`

## 7. 測試策略（Phase 6）
1. 純函式單元(無網路，最高價值)：compute_average(正常/不足/空/N=1)、compute_maintenance_ratio(手算/n_avg=0→None/None→None 驗無 Inf/NaN)、classify_warning(130/166/None 邊界)、dates(ROC↔AD/跨月)、trading_session(08:59/09:00/13:30/13:31/週末)、validate_stock_code(正常/91/非4碼/空白)
2. Adapter(respx mock，餵實測樣本 2330 z=2440 / 6488 z=1480 y=1515)：price z="-" fallback、history 跨月合併+Yahoo fallback、margin 上市取值/上櫃 no_data、market 探測 tse→otc；每個驗「上游失敗回降級不拋例外」
3. API 整合(TestClient mock adapter)：/api/maintenance 200 契約+422+逐欄位降級；/api/health；驗任何情境不回未格式化 500
4. smoke：run.py 啟動打 / + /api/health + /api/maintenance?code=2330；前端無 console error、卡片渲染、N 調整重查、降級正確；launcher.py health 就緒→開瀏覽器（macOS 驗；Windows exe 屬交付端）

---

## 8. Phase 4 中控複審修正（Builder 必須吸收）

複審通過，0 阻斷。以下 7 項改進併入實作規格：

1. **detect_market 不得單點拖垮全查詢**（FN-009/FN-020）：MIS 探測失敗（端點故障/空）時，**不直接回 422**。改為：先試 MIS(tse→otc)；若 MIS 完全無回應，退而用 Yahoo 探測（先 `{code}.TW` 再 `{code}.TWO`，chart 有資料即該市場）。仍判不出才回 422 not_found。目的：即時端點掛了，歷史+融資仍能算維持率。

2. **F-002 措辭對齊**（FN-010）：z=="-"（當盤無成交）→ 採 (a+b)/2 中間價→y 昨收 fallback 並標 `is_fallback=true`；**僅端點無回應/解析失敗才 no_data**。（架構做法優於需求字面，以此為準）

3. **detect_session 需防國定假日誤標**（FN-006/FN-010）：不能只看「週一~五 09:00–13:30」。實作時以 **MIS 回傳的日期 d 是否等於系統今日** 為準：d==今日且在時段內 → `即時`；否則一律 `收盤`。休市日 MIS 回前一交易日資料，d≠今日即正確標 `收盤`。

4. **Yahoo fallback range 依 N 動態**（FN-014）：`range = "3mo" if N<=60 else "6mo" if N<=120 else "1y" if N<=240 else "2y"`。避免大 N 時備援點數不足。

5. **F-007 產業合計效能防護**（FN-021，選配）：逐檔抓取以 `asyncio.Semaphore(8)` 節流；成分股數量大時明確於回應 note 標示耗時；MVP 不阻塞，可最後實作或先留 stub 回 501/未啟用。

6. **PyInstaller 打包細節**（FN-034/FN-035）：
   - launcher 啟動 uvicorn **傳 app 物件**（`uvicorn.run(app, ...)`）而非 `"app.main:app"` 字串（frozen 環境字串 import 會失敗）；且不可用 `reload=True`
   - BUILD_WINDOWS.md 打包指令含：`--add-data "static;static"`（Windows 用分號）、`--hidden-import` 補 uvicorn 相關（`uvicorn.logging`、`uvicorn.protocols` 等，或用 `--collect-submodules uvicorn`）、`--name margin-maintenance-tracker`、進入點 `launcher.py`、`--noconfirm`
   - 明示 exe 僅能在 Windows 產出（Mac 無法交叉編譯）

7. **classify_warning 門檻加註依據**（FN-019）：門檻對應台股融資成數 0.6 之自然基準——初始維持率 = 1/0.6 ≈ 166.67%。故：`>=166.67 safe`（≥回本基準）、`130~166.67 warn`（虧損中未追繳）、`<130 danger`（達整戶追繳線 130%）、None na。前端 tooltip 標示此定義，避免誤導。
