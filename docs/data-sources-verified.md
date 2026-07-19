# TWSE / TPEx 資料源實測記錄（2026-07-15 於開發機 macOS 驗證）

所有端點均以 curl + User-Agent: Mozilla/5.0 驗證可從本機抓取。

## 1. 即時/收盤價 — TWSE MIS getStockInfo（上市+上櫃共用）
- URL: https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={PREFIX}_{CODE}.tw&json=1&delay=0
- Header: Referer: https://mis.twse.com.tw/stock/index.jsp（建議帶）
- PREFIX: 上市=tse、上櫃=otc
- 回傳 msgArray[0]：
  - z = 最新成交價（盤中即時；收盤後=當日收盤）。注意 z 可能為 "-"（當盤無成交），需 fallback。
  - y = 昨收；o=開,h=最高,l=最低；t=時間 HH:MM:SS；d=日期 YYYYMMDD；n=名稱；c=代號
  - 當 z 為 "-"：用 b(最佳買)/a(最佳賣) 中間價或 y 昨收 fallback，並標註
- 實測：2330.tw z=2440；6488(otc) z=1480，y=1515

## 2. N日均價歷史收盤 — 官方為主，Yahoo 備援
### 2a. 上市 TWSE STOCK_DAY（每股每月）
- URL: https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={YYYYMMDD}&stockNo={CODE}
- date 給該月任一日（通常月初）；回傳該月每日資料 data[]，欄位含「收盤價」(index 6)
- ROC 日期 "115/07/01"。跨月需抓當月+前月合併才湊滿 N 日
- 實測 OK
### 2b. 上櫃 TPEx tradingStock（每股每月，AD 日期）
- URL: https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock?code={CODE}&date={YYYY/MM/DD}&id=&response=json
- 注意：date 用「西元年」格式 YYYY/MM/DD（非 ROC）；回傳 tables[0].data[]，內部日期為 ROC "115/07/01"
- 欄位順序：[日期,成交仟股,成交仟元,開,高,低,收,漲跌,筆數]，收盤 index 6
- 實測 OK（6488 環球晶）
### 2c. 備援 Yahoo chart（上市+上櫃統一，一次到位）
- URL: https://query1.finance.yahoo.com/v8/finance/chart/{CODE}.{SFX}?range=3mo&interval=1d
- SFX: 上市=TW、上櫃=TWO
- result[0].indicators.quote[0].close = 日收盤陣列（過濾 null）；timestamp 為 epoch
- 實測 2330.TW / 6488.TWO 皆 OK，last 與官方一致（2440 / 1480）
- 用途：官方端點失敗時 fallback，確保 N日均價可算

## 3. 融資餘額（張數）
### 3a. 上市 TWSE MI_MARGN（全市場單日）
- URL: https://www.twse.com.tw/exchangeReport/MI_MARGN?response=json&date={YYYYMMDD}&selectType=ALL
- tables[1] 為「融資融券彙總(全部)」逐檔：欄位[代號,名稱,買進,賣出,現金償還,前日餘額,今日餘額,...]
- 「今日餘額」為融資餘額(張)。個股層級僅有張數無金額 → 確認需以 N日均價推估成本
- 假日/當日尚未出表：往前找最近交易日
- 實測 OK
### 3b. 上櫃 TPEx 融資融券 —【建置期釘死端點】
- openapi tpex_margin_* 名稱需查；新站 API 路徑待建置期以 openapi 清單確認
- F-004 為顯示用、非個股公式必需 → 取不到時該欄位「無資料」優雅降級

## 交易時段判斷（台北時間）
- 09:00–13:30 盤中 → z 視為即時；否則視為收盤
- 以 msgArray 的 t/d 或系統時間判斷；資料時間戳一律回傳前端標示
## 3b. 上櫃融資餘額 TPEx（已釘死 2026-07-15）
- URL: https://www.tpex.org.tw/www/zh-tw/margin/balance?date={YYYY/MM/DD 西元}&response=json&id=
- Referer: https://www.tpex.org.tw/zh-tw/mainboard/margin/balance.html
- 回傳 tables[0].data[]，共約 913 檔
- 欄位 index：代號=0, 名稱=1, 前資餘額(張)=2, 資買=3, 資賣=4, 現償=5, 資餘額=6(←今日融資餘額張數), 資屬證金=7, 資使用率%=8, ...
- 假日/未出表 → 往前找最近交易日
- 實測 date=2026/07/14 OK

## 4. 全市場掃描（警示清單 F-010，2026-07-15 實測）
目的：一次算全市場有融資標的的維持率。核心是「全市場單日收盤」批次端點——抓 N 天即得每檔 N 日均價，不需逐檔抓。歷史日期不變可快取。
### 4a. 上市全市場單日收盤 TWSE MI_INDEX
- URL: https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={YYYYMMDD}&type=ALLBUT0999
- 個股表在 tables[8]（fields 含「證券代號」「收盤價」）：代號 idx0、名稱 idx1、收盤價 idx8（去逗號）。約 1370 檔。stat!="OK" 或非交易日 → 該日無表(跳過視為非交易日)
- 實測 2330 收盤 2,440.00
### 4b. 上櫃全市場單日收盤 TPEx dailyQuotes
- URL: https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date={YYYY/MM/DD 西元}&type=EW&response=json
- tables[0].data：代號 idx0、名稱 idx1、收盤 idx2（去逗號）。含 ETF/債券約萬筆，靠融資universe過濾
- 實測 6488 收盤 1480.00
### 4c. 融資 universe（有融資餘額的標的清單）
- 上市：MI_MARGN selectType=ALL → tables[1]，代號 idx0、今日餘額(張) idx6（>0 且非 91 開頭）
- 上櫃：TPEx margin balance → tables[0]，代號 idx0、資餘額 idx6
### 掃描管線
1. 融資 universe（2 calls）→ 得代號+融資餘額
2. 回推 N 個交易日，逐日抓 4a/4b 全市場收盤 → 建 {code:[closes]} 矩陣（歷史日快取；asyncio.gather+Semaphore 並行）
3. 每檔 ratio = 最新收盤 /（N日均價×0.6）×100
4. 依 ratio 升序、分色帶（<130 紅 / 130-150 橘 / 150-166.67 黃 / ≥166.67 綠）
