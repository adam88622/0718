"""F-012：大盤融資維持率指標端點。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from httpx import AsyncClient

from app.config import TZ
from app.http_client import get_client
from app.services.market_service import get_market_indicator, get_market_live

__all__ = ["router"]

router = APIRouter()


@router.get("/api/market", response_model=None)
async def get_market(client: AsyncClient = Depends(get_client)):
    """回傳大盤金額加權融資維持率 + MA20/60 + 位階 + 走勢序列。"""
    today = datetime.now(ZoneInfo(TZ)).date()
    return await get_market_indicator(client, today)


@router.get("/api/market/live", response_model=None)
async def get_market_live_route(client: AsyncClient = Depends(get_client)):
    """即時大盤融資維持率（前 N 大權重即時、其餘收盤；抓不到即時自動降級）。"""
    today = datetime.now(ZoneInfo(TZ)).date()
    return await get_market_live(client, today)
