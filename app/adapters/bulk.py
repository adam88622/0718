"""FN-010 全市場掃描 adapter：融資 universe + 全市場單日收盤批次抓取。

目的：一次算全市場有融資標的的維持率，核心是「全市場單日收盤」批次端點——
抓 N 天即得每檔 N 日均價，不需逐檔抓（見 docs/data-sources-verified.md §4）。

- `fetch_margin_universe`：上市 MI_MARGN + 上櫃 margin balance，取得有融資
  餘額（排除 91 開頭、餘額<=0）的全市場代號清單。
- `fetch_all_close_twse` / `fetch_all_close_tpex`：全市場單日收盤快照。
- `build_close_matrix`：回推交易日，逐日並行抓兩市場全市場收盤，組出
  `{code: [close 由舊到新]}` 矩陣，歷史日期以模組級 dict 永久快取。

全程 async、使用傳入 client、try/except 不裸拋，個別市場/日期失敗僅該筆
資料缺漏，不影響整體流程。
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any

from app.config import (
    BULK_CONCURRENCY,
    MARGIN_LOOKBACK_DAYS,
    TPEX_DAILY_QUOTES_URL,
    TPEX_MARGIN_BALANCE_URL,
    TPEX_MARGIN_REFERER,
    TWSE_MI_INDEX_URL,
    TWSE_MI_MARGN_URL,
)
from app.utils.dates import date_to_ad_slash, date_to_ymd

__all__ = [
    "fetch_margin_universe",
    "fetch_all_close_twse",
    "fetch_all_close_tpex",
    "build_close_matrix",
    "fetch_all_margin_twse",
    "fetch_all_margin_tpex",
]

_WARRANT_PREFIX = "91"
_EMPTY_MARKERS = {"--", "—", "", "-", "N/A"}

# 歷史日期全市場收盤快照永久快取（key = "YYYYMMDD"）；今日不快取，
# 確保盤中/當日資料每次重新抓取。
_TSE_CLOSE_CACHE: dict[str, dict[str, float]] = {}
_OTC_CLOSE_CACHE: dict[str, dict[str, float]] = {}


def _parse_close_cell(raw: Any) -> float | None:
    """去逗號轉 float；"--"/"—"/空白等無資料標記回傳 None。"""
    cleaned = str(raw).replace(",", "").strip()
    if cleaned in _EMPTY_MARKERS:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


async def _fetch_universe_twse(
    client: Any, today: date
) -> tuple[dict[str, int], dict[str, str], str | None]:
    """回推 `MARGIN_LOOKBACK_DAYS` 天，抓上市全市場融資餘額 universe。

    回傳 `({code: balance_lots}, {code: name}, as_of_iso)`；全部回退仍取不到
    回 `({}, {}, None)`。名稱取自 MI_MARGN tables[1] 名稱欄（idx1）。
    """
    for offset in range(MARGIN_LOOKBACK_DAYS + 1):
        target_date = today - timedelta(days=offset)
        url = TWSE_MI_MARGN_URL.format(date=date_to_ymd(target_date))
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        except Exception:  # noqa: BLE001 - 該日失敗，往前一天重試
            continue

        if not isinstance(data, dict):
            continue
        stat = data.get("stat")
        if stat is not None and stat != "OK":
            continue

        tables = data.get("tables")
        if not isinstance(tables, list) or len(tables) < 2:
            continue

        rows = tables[1].get("data") or []
        universe: dict[str, int] = {}
        names: dict[str, str] = {}
        for row in rows:
            if len(row) <= 6:
                continue
            code = str(row[0]).strip()
            if not code or code.startswith(_WARRANT_PREFIX):
                continue
            balance_text = str(row[6]).replace(",", "").strip()
            try:
                balance = int(balance_text)
            except ValueError:
                continue
            if balance <= 0:
                continue
            universe[code] = balance
            names[code] = str(row[1]).strip()

        if universe:
            return universe, names, target_date.isoformat()

    return {}, {}, None


async def _fetch_universe_tpex(
    client: Any, today: date
) -> tuple[dict[str, int], dict[str, str], str | None]:
    """回推 `MARGIN_LOOKBACK_DAYS` 天，抓上櫃全市場融資餘額 universe。

    回傳 `({code: balance_lots}, {code: name}, as_of_iso)`；全部回退仍取不到
    回 `({}, {}, None)`。名稱取自 TPEx margin balance tables[0] 名稱欄（idx1）。
    """
    for offset in range(MARGIN_LOOKBACK_DAYS + 1):
        target_date = today - timedelta(days=offset)
        url = TPEX_MARGIN_BALANCE_URL.format(date=date_to_ad_slash(target_date))
        try:
            resp = await client.get(url, headers={"Referer": TPEX_MARGIN_REFERER})
            resp.raise_for_status()
            data = resp.json()
        except Exception:  # noqa: BLE001 - 該日失敗，往前一天重試
            continue

        if not isinstance(data, dict):
            continue

        tables = data.get("tables")
        if not isinstance(tables, list) or not tables:
            continue

        rows = tables[0].get("data") or []
        universe: dict[str, int] = {}
        names: dict[str, str] = {}
        for row in rows:
            if len(row) <= 6:
                continue
            code = str(row[0]).strip()
            if not code or code.startswith(_WARRANT_PREFIX):
                continue
            balance_text = str(row[6]).replace(",", "").strip()
            try:
                balance = int(balance_text)
            except ValueError:
                continue
            if balance <= 0:
                continue
            universe[code] = balance
            names[code] = str(row[1]).strip()

        if universe:
            return universe, names, target_date.isoformat()

    return {}, {}, None


async def fetch_margin_universe(client: Any, today: date) -> dict[str, Any]:
    """取得全市場（上市+上櫃）有融資餘額的代號 universe。

    排除 91 開頭（權證/牛熊證）與餘額<=0；當日無表時往前回退最多
    `MARGIN_LOOKBACK_DAYS` 個日曆日。全程容錯，任一市場失敗僅該市場為空。

    回傳：
        `{"tse": {code: lots}, "otc": {code: lots},
          "names": {code: name}(上市+上櫃合併),
          "as_of_tse": "YYYY-MM-DD"|None, "as_of_otc": "YYYY-MM-DD"|None}`
    """
    try:
        tse_universe, tse_names, as_of_tse = await _fetch_universe_twse(client, today)
    except Exception:  # noqa: BLE001 - 保底，任何未預期例外一律降級
        tse_universe, tse_names, as_of_tse = {}, {}, None

    try:
        otc_universe, otc_names, as_of_otc = await _fetch_universe_tpex(client, today)
    except Exception:  # noqa: BLE001 - 保底，任何未預期例外一律降級
        otc_universe, otc_names, as_of_otc = {}, {}, None

    names: dict[str, str] = {}
    names.update(tse_names)
    names.update(otc_names)

    return {
        "tse": tse_universe,
        "otc": otc_universe,
        "names": names,
        "as_of_tse": as_of_tse,
        "as_of_otc": as_of_otc,
    }


async def fetch_all_close_twse(day: date, client: Any) -> dict[str, float]:
    """抓上市全市場單日收盤（TWSE MI_INDEX，`type=ALLBUT0999`）。

    個股表以 `fields` 搜尋定位（同時含「證券代號」「收盤價」的表），
    不寫死 index。非交易日/`stat`!="OK"/找不到個股表 -> 回傳 `{}`。
    """
    url = TWSE_MI_INDEX_URL.format(date=date_to_ymd(day))
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
    except Exception:  # noqa: BLE001 - 對外請求全程容錯
        return {}

    if not isinstance(data, dict):
        return {}
    stat = data.get("stat")
    if stat is not None and stat != "OK":
        return {}

    tables = data.get("tables")
    if not isinstance(tables, list):
        return {}

    target_table = None
    for table in tables:
        fields = table.get("fields") or []
        if "證券代號" in fields and "收盤價" in fields:
            target_table = table
            break
    if target_table is None:
        return {}

    fields = target_table.get("fields") or []
    try:
        close_idx = fields.index("收盤價")
    except ValueError:
        return {}

    rows = target_table.get("data") or []
    result: dict[str, float] = {}
    for row in rows:
        if len(row) <= close_idx:
            continue
        code = str(row[0]).strip()
        if not code:
            continue
        close = _parse_close_cell(row[close_idx])
        if close is None:
            continue
        result[code] = close

    return result


async def fetch_all_close_tpex(day: date, client: Any) -> dict[str, float]:
    """抓上櫃全市場單日收盤（TPEx dailyQuotes，`type=EW`）。

    `tables[0].data`：代號 idx0、收盤 idx2（去逗號）。含 ETF/債券等非個股列，
    交由呼叫端以融資 universe 過濾。非交易日/請求失敗 -> 回傳 `{}`。
    """
    url = TPEX_DAILY_QUOTES_URL.format(date=date_to_ad_slash(day))
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
    except Exception:  # noqa: BLE001 - 對外請求全程容錯
        return {}

    if not isinstance(data, dict):
        return {}

    tables = data.get("tables")
    if not isinstance(tables, list) or not tables:
        return {}

    rows = tables[0].get("data") or []
    result: dict[str, float] = {}
    for row in rows:
        if len(row) <= 2:
            continue
        code = str(row[0]).strip()
        if not code:
            continue
        close = _parse_close_cell(row[2])
        if close is None:
            continue
        result[code] = close

    return result


async def fetch_all_margin_twse(day: date, client: Any) -> dict[str, tuple[int, int]]:
    """抓上市全市場單日融資（TWSE MI_MARGN, selectType=ALL）。

    回傳 `{code: (今日融資買進張, 今日融資餘額張)}`，供融資成本加權滾動用
    （不做 >0 / 91 過濾，交由呼叫端決定）。非交易日/失敗 -> `{}`。
    買進=idx2、今日餘額=idx6。
    """
    url = TWSE_MI_MARGN_URL.format(date=date_to_ymd(day))
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(data, dict):
        return {}
    stat = data.get("stat")
    if stat is not None and stat != "OK":
        return {}
    tables = data.get("tables")
    if not isinstance(tables, list) or len(tables) < 2:
        return {}
    result: dict[str, tuple[int, int]] = {}
    for row in tables[1].get("data") or []:
        if len(row) <= 6:
            continue
        code = str(row[0]).strip()
        if not code:
            continue
        try:
            buy = int(str(row[2]).replace(",", "").strip())
            bal = int(str(row[6]).replace(",", "").strip())
        except ValueError:
            continue
        result[code] = (buy, bal)
    return result


async def fetch_all_margin_tpex(day: date, client: Any) -> dict[str, tuple[int, int]]:
    """抓上櫃全市場單日融資（TPEx margin balance）。

    回傳 `{code: (資買張, 資餘額張)}`。資買=idx3、資餘額=idx6。非交易日/失敗 -> `{}`。
    """
    url = TPEX_MARGIN_BALANCE_URL.format(date=date_to_ad_slash(day))
    try:
        resp = await client.get(url, headers={"Referer": TPEX_MARGIN_REFERER})
        resp.raise_for_status()
        data = resp.json()
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(data, dict):
        return {}
    tables = data.get("tables")
    if not isinstance(tables, list) or not tables:
        return {}
    result: dict[str, tuple[int, int]] = {}
    for row in tables[0].get("data") or []:
        if len(row) <= 6:
            continue
        code = str(row[0]).strip()
        if not code:
            continue
        try:
            buy = int(str(row[3]).replace(",", "").strip())
            bal = int(str(row[6]).replace(",", "").strip())
        except ValueError:
            continue
        result[code] = (buy, bal)
    return result


async def _cached_fetch_twse(
    day: date, client: Any, today: date
) -> dict[str, float]:
    """帶快取的上市全市場收盤查詢：歷史日期（`day < today`）永久快取，今日不快取。"""
    if day >= today:
        return await fetch_all_close_twse(day, client)

    key = date_to_ymd(day)
    cached = _TSE_CLOSE_CACHE.get(key)
    if cached is not None:
        return cached

    result = await fetch_all_close_twse(day, client)
    if result:
        _TSE_CLOSE_CACHE[key] = result
    return result


async def _cached_fetch_tpex(
    day: date, client: Any, today: date
) -> dict[str, float]:
    """帶快取的上櫃全市場收盤查詢：歷史日期（`day < today`）永久快取，今日不快取。"""
    if day >= today:
        return await fetch_all_close_tpex(day, client)

    key = date_to_ymd(day)
    cached = _OTC_CLOSE_CACHE.get(key)
    if cached is not None:
        return cached

    result = await fetch_all_close_tpex(day, client)
    if result:
        _OTC_CLOSE_CACHE[key] = result
    return result


async def build_close_matrix(
    codes_by_market: dict[str, list[str]] | dict[str, set[str]],
    n: int,
    client: Any,
    today: date,
) -> dict[str, Any]:
    """回推交易日，並行抓取全市場收盤，組出 `{code: [close 由舊到新]}` 矩陣。

    對每個候選日曆日，`tse`/`otc` 兩市場的抓取以 `asyncio.Semaphore
    (BULK_CONCURRENCY)` 併發控管；收集到「每市場各湊滿 N 個有資料交易日」
    即停止，最多回推 `n*2+10` 個日曆日作為保護（避免長假造成無限回推）。

    參數：
        codes_by_market: `{"tse": [code, ...], "otc": [code, ...]}`，
            僅對這些代號組出矩陣（其餘全市場收盤資料不保留，節省記憶體）。
        n: 欲湊滿的交易日數。
        client: 共用 httpx.AsyncClient。
        today: 查詢基準日（回推起點）。

    回傳：
        `{"tse": {code: [close,...]}, "otc": {code: [close,...]},
          "price_as_of": "YYYY-MM-DD"|None}`（矩陣收盤序列由舊到新排列）。
    """
    semaphore = asyncio.Semaphore(BULK_CONCURRENCY)
    max_calendar_days = n * 2 + 10

    tse_days: list[tuple[date, dict[str, float]]] = []
    otc_days: list[tuple[date, dict[str, float]]] = []
    tse_needed = n
    otc_needed = n
    latest_day: date | None = None

    async def _guarded_tse(day: date) -> dict[str, float]:
        async with semaphore:
            try:
                return await _cached_fetch_twse(day, client, today)
            except Exception:  # noqa: BLE001 - 保底，單日失敗視為無資料
                return {}

    async def _guarded_otc(day: date) -> dict[str, float]:
        async with semaphore:
            try:
                return await _cached_fetch_tpex(day, client, today)
            except Exception:  # noqa: BLE001 - 保底，單日失敗視為無資料
                return {}

    day_offset = 0
    while (tse_needed > 0 or otc_needed > 0) and day_offset <= max_calendar_days:
        day = today - timedelta(days=day_offset)
        day_offset += 1

        tasks: list[Any] = []
        need_tse = tse_needed > 0
        need_otc = otc_needed > 0
        if need_tse:
            tasks.append(_guarded_tse(day))
        if need_otc:
            tasks.append(_guarded_otc(day))
        if not tasks:
            break

        results = await asyncio.gather(*tasks, return_exceptions=True)
        idx = 0
        tse_snapshot: dict[str, float] = {}
        otc_snapshot: dict[str, float] = {}
        if need_tse:
            r = results[idx]
            idx += 1
            tse_snapshot = r if isinstance(r, dict) else {}
        if need_otc:
            r = results[idx]
            otc_snapshot = r if isinstance(r, dict) else {}

        if need_tse and tse_snapshot:
            tse_days.append((day, tse_snapshot))
            tse_needed -= 1
            if latest_day is None or day > latest_day:
                latest_day = day
        if need_otc and otc_snapshot:
            otc_days.append((day, otc_snapshot))
            otc_needed -= 1
            if latest_day is None or day > latest_day:
                latest_day = day

    tse_days.sort(key=lambda item: item[0])
    otc_days.sort(key=lambda item: item[0])

    tse_matrix: dict[str, list[float]] = {}
    for code in codes_by_market.get("tse", []):
        series = [snap[code] for _, snap in tse_days if code in snap]
        if series:
            tse_matrix[code] = series

    otc_matrix: dict[str, list[float]] = {}
    for code in codes_by_market.get("otc", []):
        series = [snap[code] for _, snap in otc_days if code in snap]
        if series:
            otc_matrix[code] = series

    return {
        "tse": tse_matrix,
        "otc": otc_matrix,
        "price_as_of": latest_day.isoformat() if latest_day else None,
    }
