"""FN-014：N 日歷史收盤 — Yahoo chart 備援（上市 TW / 上櫃 TWO 統一格式）。

官方端點（`history_official.py`）全失敗或不足時，由 `services/average.py` 呼叫本模組
作為備援，確保 N 日均價仍可計算。含 Phase 4 修正第 4 點：`range` 依 N 動態調整，
避免 N 值較大時備援端點回傳的資料點數不足。
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx

from app.config import TZ, YAHOO_CHART_URL

__all__ = ["fetch_history_yahoo"]

_MARKET_SFX = {"tse": "TW", "otc": "TWO"}


def _range_for_n(n: int) -> str:
    """依需求日數 N 決定 Yahoo chart 查詢區間，避免大 N 時資料點不足。"""
    if n <= 60:
        return "3mo"
    if n <= 120:
        return "6mo"
    if n <= 240:
        return "1y"
    return "2y"


async def fetch_history_yahoo(
    code: str, market: str, n: int, client: httpx.AsyncClient
) -> list[tuple[date, float]]:
    """抓取 Yahoo chart 歷史收盤序列（官方端點備援）。

    `market`："tse"→後綴 "TW"、"otc"→後綴 "TWO"；未知市場一律回傳 []。
    `range` 依 `n` 動態決定（見 `_range_for_n`）。
    回傳升序 `[(date, close), ...]`（依 Asia/Taipei 時區將 epoch 轉為日期）；
    請求失敗、解析失敗、或無資料一律回傳 []，不對外拋出例外。
    """
    sfx = _MARKET_SFX.get(market)
    if sfx is None:
        return []

    url = YAHOO_CHART_URL.format(code=code, sfx=sfx, range=_range_for_n(n))
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        payload = resp.json()
    except Exception:  # noqa: BLE001 - 對外請求全程容錯
        return []

    try:
        result = payload["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError, TypeError):
        return []

    if not timestamps or not closes:
        return []

    tz = ZoneInfo(TZ)
    parsed: list[tuple[date, float]] = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        try:
            d = datetime.fromtimestamp(ts, tz=tz).date()
        except (TypeError, ValueError, OSError):
            continue
        parsed.append((d, float(close)))

    parsed.sort(key=lambda item: item[0])
    return parsed
