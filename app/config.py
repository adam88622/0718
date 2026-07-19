"""FN-001: 全域常數、資料源端點模板與路徑解析。

集中管理維持率計算參數、交易時段設定、對外請求端點 URL 模板與共用 Header。
供 L2 adapter 層與 L3 服務層匯入使用，本模組不對外發出任何 HTTP 請求。
"""

from __future__ import annotations

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 維持率計算參數
# ---------------------------------------------------------------------------
MARGIN_RATE: float = 0.6  # 台股融資成數
DEFAULT_N: int = 20  # N 日均價預設天數
N_MIN: int = 1
N_MAX: int = 250

# 警戒門檻（依融資成數 0.6 推導：初始維持率 1/0.6 ≈ 166.67%）
WARN_DANGER: float = 130.0  # < 130 追繳
WARN_SAFE: float = 166.67  # >= 166.67 安全（回本基準）

# ---------------------------------------------------------------------------
# 對外請求參數
# ---------------------------------------------------------------------------
HTTP_TIMEOUT: float = 8.0  # 秒
MARGIN_LOOKBACK_DAYS: int = 5  # 融資餘額當日無表時往前回退天數

# ---------------------------------------------------------------------------
# 交易時段
# ---------------------------------------------------------------------------
SESSION_START: str = "09:00"
SESSION_END: str = "13:30"
TZ: str = "Asia/Taipei"

# ---------------------------------------------------------------------------
# 資料源端點 URL 模板（實測見 docs/data-sources-verified.md）
# ---------------------------------------------------------------------------

# 即時/收盤價 — TWSE MIS getStockInfo（上市 tse / 上櫃 otc 共用）
# 用法：MIS_STOCK_INFO_URL.format(prefix="tse"|"otc", code="2330")
MIS_STOCK_INFO_URL: str = (
    "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
    "?ex_ch={prefix}_{code}.tw&json=1&delay=0"
)

# N 日歷史收盤 — 上市 TWSE STOCK_DAY（每股每月）
# 用法：TWSE_STOCK_DAY_URL.format(date="20260701", code="2330")  # date=YYYYMMDD
TWSE_STOCK_DAY_URL: str = (
    "https://www.twse.com.tw/exchangeReport/STOCK_DAY"
    "?response=json&date={date}&stockNo={code}"
)

# N 日歷史收盤 — 上櫃 TPEx tradingStock（每股每月，date 為西元 YYYY/MM/DD）
TPEX_TRADING_STOCK_URL: str = (
    "https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock"
    "?code={code}&date={date}&id=&response=json"
)

# N 日歷史收盤備援 — Yahoo chart（上市 TW / 上櫃 TWO 統一格式）
# 用法：YAHOO_CHART_URL.format(code="2330", sfx="TW", range="3mo")
YAHOO_CHART_URL: str = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{code}.{sfx}"
    "?range={range}&interval=1d"
)

# 融資餘額 — 上市 TWSE MI_MARGN（全市場單日彙總）
TWSE_MI_MARGN_URL: str = (
    "https://www.twse.com.tw/exchangeReport/MI_MARGN"
    "?response=json&date={date}&selectType=ALL"
)

# 融資餘額 — 上櫃 TPEx margin balance（全市場單日彙總，date 為西元 YYYY/MM/DD）
TPEX_MARGIN_BALANCE_URL: str = (
    "https://www.tpex.org.tw/www/zh-tw/margin/balance"
    "?date={date}&response=json&id="
)

# 全市場單日收盤 — 上市 TWSE MI_INDEX（date=YYYYMMDD）
TWSE_MI_INDEX_URL: str = (
    "https://www.twse.com.tw/exchangeReport/MI_INDEX"
    "?response=json&date={date}&type=ALLBUT0999"
)

# 全市場單日收盤 — 上櫃 TPEx dailyQuotes（date 為西元 YYYY/MM/DD）
TPEX_DAILY_QUOTES_URL: str = (
    "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes"
    "?date={date}&type=EW&response=json"
)

# ---------------------------------------------------------------------------
# 全市場融資維持率警示掃描（F-010）
# ---------------------------------------------------------------------------
# 分色門檻：<130 紅(danger) / 130~150 橘(warn1) / 150~166.67 黃(warn2) / >=166.67 綠(safe)
ALERT_BANDS: dict[str, float] = {
    "danger": WARN_DANGER,  # 130.0
    "mid": 150.0,
    "safe": WARN_SAFE,  # 166.67
}

ALERT_CACHE_TTL: int = 300  # 秒，全市場警示清單快取存活時間
BULK_CONCURRENCY: int = 8  # 全市場批次抓取並行度上限（asyncio.Semaphore）

# ---------------------------------------------------------------------------
# 共用 Header
# ---------------------------------------------------------------------------
DEFAULT_HEADERS: dict[str, str] = {"User-Agent": "Mozilla/5.0"}

MIS_REFERER: str = "https://mis.twse.com.tw/stock/index.jsp"
TPEX_MARGIN_REFERER: str = (
    "https://www.tpex.org.tw/zh-tw/mainboard/margin/balance.html"
)


def resolve_base_dir() -> Path:
    """解析專案基準目錄，供 static 檔案定位使用。

    PyInstaller 打包後（frozen）以 `sys._MEIPASS` 為基準；
    開發環境則以本檔所在位置回推至專案根目錄（app/ 的上一層）。
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent
