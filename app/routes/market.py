"""F-012：大盤融資維持率指標端點。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from httpx import AsyncClient

from app.config import TZ
from app.http_client import get_client
from app.services.market_service import get_market_indicator

__all__ = ["router"]

router = APIRouter()


@router.get("/api/market", response_model=None)
async def get_market(client: AsyncClient = Depends(get_client)):
    """回傳大盤金額加權融資維持率 + MA20/60 + 位階 + 走勢序列。"""
    today = datetime.now(ZoneInfo(TZ)).date()
    return await get_market_indicator(client, today)
