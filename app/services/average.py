"""FN-016/FN-017：N 日均價計算與官方+Yahoo 備援編排。

- `compute_average`：純函式，取升序序列尾端最近 N 筆算術平均。
- `get_n_day_average`：先呼叫官方歷史（`fetch_history_official`），資料筆數
  不足 N 時，再呼叫 Yahoo（`fetch_history_yahoo`）補足缺漏日期；`source`
  依「Yahoo 是否實際補上任何資料」標示 "TWSE官方" 或 "Yahoo"。全程不裸拋例外，
  皆無資料時回傳 `no_data_block`（見 docs/architecture.md §5）。
"""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from app.adapters.history_official import fetch_history_official
from app.adapters.history_yahoo import fetch_history_yahoo
from app.services.calculator import trim_recent_continuous
from app.utils.errors import no_data_block

__all__ = ["compute_average", "get_n_day_average"]

_SOURCE_OFFICIAL = "TWSE官方"
_SOURCE_YAHOO = "Yahoo"


def compute_average(
    series: list[tuple[date, float]], n: int
) -> tuple[float | None, list[tuple[date, float]]]:
    """純函式：取升序序列尾端最近 N 筆算術平均（四捨五入 2 位）。

    參數：
        series: 升序排列的 `[(date, close), ...]`。
        n: 欲取用的天數。

    回傳：
        `(avg, used)`；`series` 為空、或 `n<=0` 時回傳 `(None, [])`。
        `used` 為實際取用的尾端筆數（可能因資料不足而少於 `n`）。
    """
    if not series or n <= 0:
        return None, []
    used = series[-n:]
    avg = round(sum(close for _, close in used) / len(used), 2)
    return avg, used


async def get_n_day_average(
    code: str,
    market: str,
    n: int,
    client: httpx.AsyncClient,
    today: date,
) -> dict[str, Any]:
    """取 N 日均價，回傳與 `AverageBlock` 相容的 dict。

    參數：
        code: 已正規化的 4 碼股票代號。
        market: "tse" 或 "otc"。
        n: 使用者請求天數（呼叫端須先 clamp 至 `[N_MIN, N_MAX]`）。
        client: 共用 httpx.AsyncClient。
        today: 查詢基準日（台北時區的今日）。

    邏輯：
        1. 先取官方歷史；筆數 < n 時再取 Yahoo，補上官方缺漏的日期
           （同日期以官方為準，不覆蓋）。
        2. 若 Yahoo 實際補上任何官方沒有的日期，`source` 標為 "Yahoo"，
           否則維持 "TWSE官方"。
        3. `compute_average` 取合併後序列最近 N 筆；不足 N 筆時
           `insufficient=True` 並附 `note`。
        4. 官方與 Yahoo 皆無資料時，回傳 `no_data_block("TWSE官方")`
           並於 `note` 說明兩者皆無歷史資料。
    """
    official = await fetch_history_official(code, market, n, client, today)

    merged: dict[date, float] = dict(official)
    source = _SOURCE_OFFICIAL

    if len(official) < n:
        yahoo = await fetch_history_yahoo(code, market, n, client)
        supplemented = False
        for d, close in yahoo:
            if d not in merged:
                merged[d] = close
                supplemented = True
        if supplemented:
            source = _SOURCE_YAHOO

    series = sorted(merged.items(), key=lambda item: item[0])

    # 排除近期除權/分割造成的未還原價斷點（官方 STOCK_DAY/tradingStock 為
    # 未還原價），只取事件後連續段，避免分割前後不同計價基礎混算。
    closes_only = [close for _, close in series]
    trimmed_closes, adjusted = trim_recent_continuous(closes_only)
    if adjusted:
        series = series[-len(trimmed_closes):]

    avg, used = compute_average(series, n)

    if not used:
        return no_data_block(
            _SOURCE_OFFICIAL,
            {
                "value": None,
                "count": 0,
                "start": None,
                "end": None,
                "n_requested": n,
                "insufficient": True,
                "note": "官方與 Yahoo 皆無歷史資料",
            },
        )

    count = len(used)
    insufficient = count < n
    notes: list[str] = []
    if adjusted:
        notes.append("近期有除權息/分割，均價僅取事件後資料")
    if insufficient:
        notes.append(f"資料不足 {n} 日，以 {count} 日計算")
    note = "；".join(notes) if notes else None

    return {
        "value": avg,
        "count": count,
        "start": used[0][0].isoformat(),
        "end": used[-1][0].isoformat(),
        "n_requested": n,
        "insufficient": insufficient,
        "note": note,
        "source": source,
        "status": "ok",
    }
