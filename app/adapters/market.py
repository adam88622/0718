"""FN-009：市場別探測（上市 tse / 上櫃 otc），唯一對外請求出口之一。

策略：先以 TWSE MIS getStockInfo 探測 tse 前綴，`msgArray` 非空即判定上市；
否則改探測 otc 前綴。若 MIS 兩次請求皆「無回應/例外」（區分於「有回應但
內容為空」），才退而改用 Yahoo chart 探測（先 `{code}.TW` 再 `{code}.TWO`，
任一有有效收盤資料即判定該市場）。全程 try/except，探測不出回傳 None，
不拋出例外（見 docs/architecture.md §8 修正第 1 點）。
"""

from __future__ import annotations

from typing import Any

from app.config import MIS_REFERER, MIS_STOCK_INFO_URL, YAHOO_CHART_URL

__all__ = ["detect_market"]


async def _mis_probe(code: str, prefix: str, client: Any) -> tuple[bool, bool]:
    """探測單一 MIS 前綴。

    回傳 `(responded, has_data)`：
    - `responded=False` 代表請求本身失敗（連線例外/非 2xx/JSON 解析失敗）。
    - `has_data` 僅在 `responded=True` 時才有意義。**注意 MIS 對「錯誤市場前綴」
      也會回傳長度 1 的 msgArray，但內容為空殼（`c=''`、`z='-'`）**，故不能只看
      msgArray 非空；必須確認回傳項的代號欄 `c` 等於查詢代號才算命中。
    """
    url = MIS_STOCK_INFO_URL.format(prefix=prefix, code=code)
    try:
        resp = await client.get(url, headers={"Referer": MIS_REFERER})
        resp.raise_for_status()
        data = resp.json()
    except Exception:  # noqa: BLE001 - 統一視為「無回應」，不外洩例外細節
        return False, False

    msg_array = data.get("msgArray") if isinstance(data, dict) else None
    if not msg_array:
        return True, False
    has_data = any(
        isinstance(entry, dict) and entry.get("c") == code for entry in msg_array
    )
    return True, has_data


async def _yahoo_has_data(code: str, sfx: str, client: Any) -> bool:
    """探測 Yahoo chart 是否有該代號在指定後綴（TW/TWO）下的有效收盤資料。"""
    url = YAHOO_CHART_URL.format(code=code, sfx=sfx, range="5d")
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
    except Exception:  # noqa: BLE001
        return False

    try:
        result = data["chart"]["result"]
    except (KeyError, TypeError):
        return False
    if not result:
        return False

    try:
        closes = result[0]["indicators"]["quote"][0]["close"]
    except (KeyError, TypeError, IndexError):
        return False

    return any(c is not None for c in closes)


async def detect_market(code: str, client: Any) -> str | None:
    """探測代號所屬市場別，回傳 "tse" / "otc" / None（探測不出）。

    不拋出例外；所有上游失敗一律吸收後續往下一步降級。
    """
    try:
        responded_tse, has_data_tse = await _mis_probe(code, "tse", client)
        if has_data_tse:
            return "tse"

        responded_otc, has_data_otc = await _mis_probe(code, "otc", client)
        if has_data_otc:
            return "otc"

        if not responded_tse and not responded_otc:
            # MIS 完全無回應（非「有回應但空」）→ 退而用 Yahoo 探測
            if await _yahoo_has_data(code, "TW", client):
                return "tse"
            if await _yahoo_has_data(code, "TWO", client):
                return "otc"

        return None
    except Exception:  # noqa: BLE001 - 保底，探測失敗一律回 None 不裸拋
        return None
