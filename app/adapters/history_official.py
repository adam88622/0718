"""FN-011/FN-012/FN-013：N 日歷史收盤 — 官方端點（TWSE STOCK_DAY / TPEx tradingStock）。

- `fetch_history_twse`：上市，STOCK_DAY（date=YYYYMMDD，通常給該月 1 號）。
- `fetch_history_tpex`：上櫃，tradingStock（date=YYYY/MM/DD 西元）。
- `fetch_history_official`：依市場對 `months_to_fetch` 回推的各月分別呼叫、合併去重排序。

全程容錯：任何解析/請求失敗一律回傳空 list，不對外拋出例外，供上層 `services/average.py`
判斷是否需要退而使用 Yahoo 備援（FN-014）。
"""

from __future__ import annotations

import asyncio
from datetime import date

import httpx

from app.config import TPEX_TRADING_STOCK_URL, TWSE_STOCK_DAY_URL
from app.utils.dates import date_to_ad_slash, date_to_ymd, months_to_fetch, roc_to_date

__all__ = [
    "fetch_history_twse",
    "fetch_history_tpex",
    "fetch_history_official",
]

_EMPTY_MARKERS = {"--", "—", "", "-", "N/A"}


def _parse_close(raw: str) -> float | None:
    """將收盤價欄位字串轉為 float；無資料標記（"--"/"—"/空白）回傳 None。"""
    cleaned = raw.strip()
    if cleaned in _EMPTY_MARKERS:
        return None
    cleaned = cleaned.replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


async def fetch_history_twse(
    code: str, month: date, client: httpx.AsyncClient
) -> list[tuple[date, float]]:
    """抓取上市個股單月歷史收盤（TWSE STOCK_DAY）。

    `month`：該月代表日（通常為每月 1 號），僅用其年月定位查詢區間。
    回傳升序 `[(date, close), ...]`；請求失敗、`stat` 非 "OK"、或無 `data` 一律回傳 []。
    """
    url = TWSE_STOCK_DAY_URL.format(date=date_to_ymd(month), code=code)
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        payload = resp.json()
    except Exception:  # noqa: BLE001 - 對外請求全程容錯
        return []

    if payload.get("stat") != "OK":
        return []
    rows = payload.get("data")
    if not rows:
        return []

    result: list[tuple[date, float]] = []
    for row in rows:
        try:
            d = roc_to_date(str(row[0]))
        except (ValueError, IndexError):
            continue
        close = _parse_close(str(row[6])) if len(row) > 6 else None
        if close is None:
            continue
        result.append((d, close))

    result.sort(key=lambda item: item[0])
    return result


async def fetch_history_tpex(
    code: str, month: date, client: httpx.AsyncClient
) -> list[tuple[date, float]]:
    """抓取上櫃個股單月歷史收盤（TPEx tradingStock）。

    `month`：該月代表日，`date` 查詢參數以**西元** `YYYY/MM/DD` 格式帶入（非 ROC）。
    回傳升序 `[(date, close), ...]`；請求失敗或無 `tables[0].data` 一律回傳 []。
    """
    url = TPEX_TRADING_STOCK_URL.format(code=code, date=date_to_ad_slash(month))
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        payload = resp.json()
    except Exception:  # noqa: BLE001 - 對外請求全程容錯
        return []

    tables = payload.get("tables")
    if not tables:
        return []
    rows = tables[0].get("data")
    if not rows:
        return []

    result: list[tuple[date, float]] = []
    for row in rows:
        try:
            d = roc_to_date(str(row[0]))
        except (ValueError, IndexError):
            continue
        close = _parse_close(str(row[6])) if len(row) > 6 else None
        if close is None:
            continue
        result.append((d, close))

    result.sort(key=lambda item: item[0])
    return result


async def fetch_history_official(
    code: str,
    market: str,
    n: int,
    client: httpx.AsyncClient,
    today: date,
) -> list[tuple[date, float]]:
    """依市場（"tse"/"otc"）抓取足以覆蓋 N 日的官方歷史收盤，合併去重並升序回傳。

    各月請求並行（`asyncio.gather`）；任一月失敗僅該月無資料，不影響其餘月份。
    全部月份皆無資料時回傳 []。全程容錯，不對外拋出例外。
    """
    months = months_to_fetch(n, today)
    fetch_fn = fetch_history_twse if market == "tse" else fetch_history_tpex

    try:
        monthly_results = await asyncio.gather(
            *(fetch_fn(code, month, client) for month in months),
            return_exceptions=True,
        )
    except Exception:  # noqa: BLE001 - 保底容錯
        return []

    merged: dict[date, float] = {}
    for entry in monthly_results:
        if isinstance(entry, BaseException):
            continue
        for d, close in entry:
            merged[d] = close

    return sorted(merged.items(), key=lambda item: item[0])
