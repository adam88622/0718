"""FN-010：現價 adapter（TWSE MIS getStockInfo，上市/上櫃共用）。

取 `msgArray[0].z` 為現價；`z` 為 "-"（當盤無成交）或空值時，改採
最佳買賣 `a`(賣)/`b`(買) 中間價 fallback，再退而使用昨收 `y`，並標記
`is_fallback=True`（見 docs/architecture.md §8 修正第 2 點）。

`price_type`（即時/收盤）委由 `app.utils.trading_session.is_intraday_for`
依資料日期 `d` 與系統今日比對判斷，避免假日誤標（§8 修正第 3 點）。

端點無回應或解析失敗一律降級為 `no_data_block("TWSE-MIS")`，不拋例外。
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.adapters.history_yahoo import fetch_history_yahoo
from app.config import (
    LIVE_MARKET_CHUNK,
    LIVE_MARKET_CONCURRENCY,
    MIS_REFERER,
    MIS_STOCK_INFO_BATCH_URL,
    MIS_STOCK_INFO_URL,
)
from app.utils.errors import no_data_block
from app.utils.trading_session import is_intraday_for

__all__ = ["fetch_price", "fetch_prices_mis_batch"]

_SOURCE = "TWSE-MIS"


def _to_float(value: Any) -> float | None:
    """安全轉 float；`None`/空字串/"-" /無法解析一律回 None。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == "-":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _best_quote_price(field: Any) -> float | None:
    """解析 MIS 最佳買/賣欄位（底線分隔多檔），取第一檔（最佳）價格。"""
    if field is None:
        return None
    text = str(field).strip()
    if not text:
        return None
    first = text.split("_")[0]
    return _to_float(first)


async def _yahoo_close_fallback(
    code: str, market: str, client: Any
) -> dict[str, Any] | None:
    """MIS 失敗（如限流）時，改用 Yahoo 最新收盤當現價，讓維持率仍可計算。

    Yahoo 走 query1.finance.yahoo.com（非 MIS 主機，不受 MIS 限流影響）。
    回傳 PriceBlock 相容 dict（price_type="收盤"、is_fallback=True、source="Yahoo收盤"），
    取不到回 None。
    """
    try:
        series = await fetch_history_yahoo(code, market, 5, client)
        if not series:
            return None
        last_date, last_close = series[-1]
        if last_close is None or last_close <= 0:
            return None
        return {
            "value": round(float(last_close), 2),
            "price_type": "收盤",
            "is_fallback": True,
            "prev_close": series[-2][1] if len(series) >= 2 else None,
            "as_of": last_date.isoformat(),
            "name": None,
            "source": "Yahoo收盤",
            "status": "ok",
        }
    except Exception:  # noqa: BLE001
        return None


async def fetch_price(code: str, market: str, client: Any) -> dict[str, Any]:
    """取單一代號現價，回傳與 `PriceBlock` 相容的 dict。

    優先 MIS 即時；MIS 無回應/限流（無價）時，退用 Yahoo 最新收盤，
    確保維持率不因單一即時源掛掉就「無法計算」。

    參數：
        code: 已正規化的 4 碼股票代號。
        market: "tse" 或 "otc"（由 `detect_market` 決定）。
        client: 共用 httpx.AsyncClient。
    """
    mis_ok = False
    result: dict[str, Any] = no_data_block(_SOURCE)
    url = MIS_STOCK_INFO_URL.format(prefix=market, code=code)
    try:
        resp = await client.get(url, headers={"Referer": MIS_REFERER})
        resp.raise_for_status()
        data = resp.json()
        msg_array = data.get("msgArray") if isinstance(data, dict) else None
        msg: dict[str, Any] = msg_array[0] if msg_array else {}

        prev_close = _to_float(msg.get("y"))
        value = _to_float(msg.get("z"))
        is_fallback = False
        if value is None:
            best_ask = _best_quote_price(msg.get("a"))
            best_bid = _best_quote_price(msg.get("b"))
            if best_ask is not None and best_bid is not None:
                value = round((best_ask + best_bid) / 2, 2)
            else:
                value = prev_close
            is_fallback = True

        if value is not None:
            data_date = str(msg.get("d") or "")
            data_time = str(msg.get("t") or "")
            price_type = is_intraday_for(data_date) if data_date else "收盤"
            result = {
                "value": value,
                "price_type": price_type,
                "is_fallback": is_fallback,
                "prev_close": prev_close,
                "as_of": f"{data_time} / {data_date}",
                "name": msg.get("n"),
                "source": _SOURCE,
                "status": "ok",
            }
            mis_ok = True
    except Exception:  # noqa: BLE001 - MIS 無回應/解析失敗 → 走 Yahoo fallback
        mis_ok = False

    if mis_ok:
        return result

    # MIS 取不到現價 → Yahoo 收盤 fallback
    yahoo = await _yahoo_close_fallback(code, market, client)
    return yahoo if yahoo is not None else no_data_block(_SOURCE)


async def fetch_prices_mis_batch(
    pairs: list[tuple[str, str]], client: Any
) -> dict[str, float]:
    """批次抓即時價（供即時大盤）。

    參數 `pairs`：`[(code, market), ...]`，market 為 "tse"/"otc"。
    以 MIS 批次端點（ex_ch 多檔以 | 串接）分批查詢，每批 `LIVE_MARKET_CHUNK` 檔、
    並行度 `LIVE_MARKET_CONCURRENCY`（低，避免 MIS 限流）。取 `z`（現價），
    `z` 為 "-"/空/0 時退用昨收 `y`。回傳 `{code: price}`；抓不到的檔略過
    （由呼叫端以收盤價補），全程 try/except 不拋例外。
    """
    result: dict[str, float] = {}
    if not pairs:
        return result
    chunks = [
        pairs[i : i + LIVE_MARKET_CHUNK]
        for i in range(0, len(pairs), LIVE_MARKET_CHUNK)
    ]
    sem = asyncio.Semaphore(LIVE_MARKET_CONCURRENCY)

    async def _one(chunk: list[tuple[str, str]]) -> dict[str, float]:
        ex_ch = "|".join(f"{m}_{c}.tw" for c, m in chunk)
        url = MIS_STOCK_INFO_BATCH_URL.format(ex_ch=ex_ch)
        out: dict[str, float] = {}
        async with sem:
            try:
                resp = await client.get(url, headers={"Referer": MIS_REFERER})
                resp.raise_for_status()
                data = resp.json()
            except Exception:  # noqa: BLE001 - 該批失敗，交由收盤補
                return out
        for msg in (data.get("msgArray") or []) if isinstance(data, dict) else []:
            code = str(msg.get("c") or "").strip()
            if not code:
                continue
            price = _to_float(msg.get("z"))
            if price is None or price <= 0:
                price = _to_float(msg.get("y"))  # 昨收 fallback
            if price is not None and price > 0:
                out[code] = price
        return out

    results = await asyncio.gather(
        *(_one(c) for c in chunks), return_exceptions=True
    )
    for r in results:
        if isinstance(r, dict):
            result.update(r)
    return result
