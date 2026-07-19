"""FN-010：全市場融資維持率警示掃描端點。

薄 handler：編排交由 `services.alerts_service.build_alert_list` 負責，
本模組只負責解析台北時區的查詢基準日並轉呼叫。
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from httpx import AsyncClient

from app.config import DEFAULT_N, TZ
from app.http_client import get_client
from app.services.alerts_service import build_alert_list

__all__ = ["router"]

router = APIRouter()


@router.get("/api/alerts", response_model=None)
async def get_alerts(
    n: int = DEFAULT_N, client: AsyncClient = Depends(get_client)
) -> dict:
    """全市場融資維持率警示掃描，依維持率升序回傳警示清單。

    `n`（N 日均價天數）會由服務層 clamp 至 `[N_MIN, N_MAX]`。
    回傳與 `build_alert_list` 相容的 plain dict（不套 `response_model`，
    避免對降級/選配欄位做過嚴驗證——本專案已知作法，見
    `routes/maintenance.py`）。
    """
    today = datetime.now(ZoneInfo(TZ)).date()
    return await build_alert_list(n, client, today)
