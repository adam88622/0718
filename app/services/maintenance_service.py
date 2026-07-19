"""FN-020：單股維持率查詢主編排服務。

流程：驗證代號 -> clamp N -> 判斷交易時段 -> 探測市場 -> 並行取得
現價/N 日均價/融資餘額（各自降級，不互相拖累）-> 計算維持率與警戒分類 ->
組成與 `MaintenanceResponse` 相容的 dict。

例外約定（呼叫端 `routes/maintenance.py` 需知悉）：
    - `app.utils.codes.CodeError`：代號格式錯誤或 91 開頭，本函式**不捕捉**，
      直接上拋，由 route 轉為 422 `ErrorResponse`（error="invalid_code"）。
    - `MarketNotFoundError`（本模組定義）：代號格式合法，但探測不到所屬市場
      （tse/otc 皆無資料），本函式**不捕捉**，直接上拋，由 route 轉為 422
      `ErrorResponse`（error="not_found"）。
    - 其餘子資料（現價/均價/融資）失敗一律降級為對應 Block 的 `no_data`/
      `uncomputable`，不影響整體查詢成功，本函式全程不裸拋。
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.adapters.margin import fetch_margin
from app.adapters.market import detect_market
from app.adapters.price import fetch_price
from app.config import MARGIN_RATE, N_MAX, N_MIN, TZ
from app.services.average import get_n_day_average
from app.services.calculator import classify_warning, compute_maintenance_ratio
from app.services.margin_cost import compute_current_costs
from app.utils.codes import validate_stock_code
from app.utils.errors import no_data_block, safe_block
from app.utils.trading_session import detect_session

__all__ = ["MarketNotFoundError", "get_stock_maintenance"]


class MarketNotFoundError(Exception):
    """代號通過格式驗證，但探測不到所屬市場（tse/otc）時拋出。

    由呼叫端（`routes/maintenance.py`）捕捉並轉為 422 `ErrorResponse`
    （建議 `error="not_found"`）。
    """

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"探測不到代號 {code} 所屬市場")


def _clamp_n(n: int) -> int:
    """將使用者請求的 N 限制在 `[N_MIN, N_MAX]` 範圍內。"""
    return max(N_MIN, min(N_MAX, n))


async def get_stock_maintenance(
    code: str, n: int, client: httpx.AsyncClient
) -> dict[str, Any]:
    """查詢單一代號維持率，回傳與 `MaintenanceResponse` 相容的 dict。

    參數：
        code: 使用者輸入的股票代號（未正規化亦可，內部會驗證/正規化）。
        n: 使用者指定的 N 日均價天數，會被 clamp 到 `[N_MIN, N_MAX]`。
        client: 共用 httpx.AsyncClient。

    拋出：
        `CodeError`：代號格式錯誤或 91 開頭（見模組 docstring）。
        `MarketNotFoundError`：探測不到所屬市場（見模組 docstring）。
    """
    normalized_code = validate_stock_code(code)
    n = _clamp_n(n)

    tz = ZoneInfo(TZ)
    now = datetime.now(tz)
    today = now.date()

    session = detect_session(now)

    market = await detect_market(normalized_code, client)
    if market is None:
        raise MarketNotFoundError(normalized_code)

    gathered = await asyncio.gather(
        safe_block(fetch_price(normalized_code, market, client), "TWSE-MIS"),
        safe_block(
            get_n_day_average(normalized_code, market, n, client, today),
            "TWSE官方",
        ),
        safe_block(
            fetch_margin(normalized_code, market, client, today), "TWSE-MI_MARGN"
        ),
        return_exceptions=True,
    )
    price_result, average_result, margin_result = gathered

    price = (
        price_result if isinstance(price_result, dict) else no_data_block("TWSE-MIS")
    )
    average = (
        average_result
        if isinstance(average_result, dict)
        else no_data_block("TWSE官方")
    )
    margin = (
        margin_result
        if isinstance(margin_result, dict)
        else no_data_block("TWSE-MI_MARGN")
    )

    # 融資成本基礎：優先用加權滾動成本（券商級，種子 2026-07-17 + 每日滾動），
    # 無種子的標的退回 N 日均價「簡易估計」。維持率一律以此基礎為分母。
    cost = await safe_block(
        _resolve_cost(normalized_code, average, client, today), "加權融資成本"
    )
    if not isinstance(cost, dict) or cost.get("value") is None:
        cost = {
            "value": average.get("value"),
            "source": "N日均價",
            "method": "n_day_avg",
            "as_of": average.get("end"),
            "status": average.get("status", "no_data"),
        }

    cost_value = cost.get("value")
    ratio_value = compute_maintenance_ratio(price.get("value"), cost_value)
    warning = classify_warning(ratio_value)

    expression = None
    if ratio_value is not None:
        expression = f"{price.get('value')} / ({cost_value} * {MARGIN_RATE}) * 100"

    ratio = {
        "value": ratio_value,
        "warning": warning,
        "formula": {
            "price": price.get("value"),
            "n_day_avg": cost_value,
            "cost_source": cost.get("source"),
            "margin_rate": MARGIN_RATE,
            "expression": expression,
        },
        "status": "ok" if ratio_value is not None else "uncomputable",
    }

    return {
        "code": normalized_code,
        "name": price.get("name"),
        "market": market,
        "session": session,
        "n_requested": n,
        "price": price,
        "average": average,
        "cost": cost,
        "margin": margin,
        "ratio": ratio,
        "generated_at": now.isoformat(),
    }


async def _resolve_cost(
    code: str, average: dict[str, Any], client: httpx.AsyncClient, today: Any
) -> dict[str, Any]:
    """取該股加權融資成本；種子有則用加權，否則退回 N 日均價。"""
    costs = await compute_current_costs(client, today)
    wc = costs.get(code)
    if wc is not None and wc.get("value"):
        return {
            "value": round(float(wc["value"]), 2),
            "source": "加權融資成本",
            "method": "weighted",
            "as_of": wc.get("as_of"),
            "roll_days": wc.get("roll_days"),
            "status": "ok",
        }
    return {
        "value": average.get("value"),
        "source": "N日均價",
        "method": "n_day_avg",
        "as_of": average.get("end"),
        "status": average.get("status", "no_data"),
    }
