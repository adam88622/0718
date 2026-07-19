"""FN-025（選配）：產業別維持率合計端點。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from httpx import AsyncClient

from app.config import DEFAULT_N
from app.http_client import get_client
from app.services.industry_service import compute_industry_maintenance

__all__ = ["router"]

router = APIRouter()


@router.get("/api/industry")
async def get_industry(
    market: str, n: int = DEFAULT_N, client: AsyncClient = Depends(get_client)
) -> dict:
    """查詢產業別（全市場）維持率合計（目前為 stub，見 FN-021 docstring）。"""
    return await compute_industry_maintenance(market, n, client)
