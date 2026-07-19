"""FN-024：健康檢查端點。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from app.config import TZ

__all__ = ["router"]

router = APIRouter()


@router.get("/api/health")
async def get_health() -> dict[str, str]:
    """回傳服務健康狀態與台北時間時間戳，供 launcher 輪詢就緒使用。"""
    now = datetime.now(ZoneInfo(TZ))
    return {
        "status": "ok",
        "service": "margin-maintenance-tracker",
        "time": now.isoformat(),
    }
