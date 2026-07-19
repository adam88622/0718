"""FN-015：融資餘額（張數）adapter。

- 上市：TWSE MI_MARGN（`selectType=ALL`），取 `tables[1]`（融資融券彙總）逐列
  比對代號取「今日餘額」。
- 上櫃：TPEx margin balance，取 `tables[0]`，代號 idx0 / 資餘額 idx6。

當日尚未出表（假日/例外）時，往前回退最多 `config.MARGIN_LOOKBACK_DAYS`
個日曆日重試；全部回退仍取不到 → `no_data_block`。全程 try/except，不拋例外。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.config import (
    MARGIN_LOOKBACK_DAYS,
    TPEX_MARGIN_BALANCE_URL,
    TPEX_MARGIN_REFERER,
    TWSE_MI_MARGN_URL,
)
from app.utils.dates import date_to_ad_slash, date_to_ymd
from app.utils.errors import no_data_block

__all__ = ["fetch_margin"]

_SOURCE_TWSE = "TWSE-MI_MARGN"
_SOURCE_TPEX = "TPEx"


def _parse_balance(row: list[Any], code: str) -> int | None:
    """比對代號欄(idx0)，解析「今日餘額」欄(idx6，含千分位逗號)為 int。"""
    if len(row) <= 6:
        return None
    row_code = str(row[0]).strip()
    if row_code != code:
        return None
    balance_text = str(row[6]).replace(",", "").strip()
    try:
        return int(balance_text)
    except ValueError:
        return None


async def _fetch_margin_twse(
    code: str, client: Any, today: date
) -> dict[str, Any] | None:
    """逐日回退嘗試 TWSE MI_MARGN，找到即回傳 `{"balance_lots", "as_of"}`。"""
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
        for row in rows:
            balance = _parse_balance(row, code)
            if balance is not None:
                return {"balance_lots": balance, "as_of": target_date.isoformat()}

    return None


async def _fetch_margin_tpex(
    code: str, client: Any, today: date
) -> dict[str, Any] | None:
    """逐日回退嘗試 TPEx margin balance，找到即回傳 `{"balance_lots", "as_of"}`。"""
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
        for row in rows:
            balance = _parse_balance(row, code)
            if balance is not None:
                return {"balance_lots": balance, "as_of": target_date.isoformat()}

    return None


async def fetch_margin(
    code: str, market: str, client: Any, today: date
) -> dict[str, Any]:
    """取單一代號融資餘額（張數），回傳與 `MarginBlock` 相容的 dict。

    參數：
        code: 已正規化的 4 碼股票代號。
        market: "tse"（走 TWSE MI_MARGN）或 "otc"（走 TPEx）。
        client: 共用 httpx.AsyncClient。
        today: 查詢基準日（回退搜尋的起點）。
    """
    source = _SOURCE_TWSE if market == "tse" else _SOURCE_TPEX
    try:
        if market == "tse":
            result = await _fetch_margin_twse(code, client, today)
        else:
            result = await _fetch_margin_tpex(code, client, today)
    except Exception:  # noqa: BLE001 - 保底，任何未預期例外一律降級
        return no_data_block(source)

    if result is None:
        return no_data_block(source)

    return {**result, "source": source, "status": "ok"}
