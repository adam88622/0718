"""FN-023：單股維持率查詢端點。

薄 handler：驗證/編排交由 `services.maintenance_service.get_stock_maintenance`
負責，本模組只處理例外轉 422（見 docs/architecture.md §8 修正約定）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from httpx import AsyncClient

from app.config import DEFAULT_N
from app.http_client import get_client
from app.models import ErrorResponse
from app.services.maintenance_service import (
    MarketNotFoundError,
    get_stock_maintenance,
)
from app.utils.codes import CodeError

__all__ = ["router"]

router = APIRouter()


@router.get("/api/maintenance", response_model=None)
async def get_maintenance(
    code: str, n: int = DEFAULT_N, client: AsyncClient = Depends(get_client)
) -> JSONResponse | dict:
    """查詢單一代號維持率。

    - 代號格式錯誤/91 開頭 -> 422 `ErrorResponse(error="invalid_code")`。
    - 探測不到所屬市場 -> 422 `ErrorResponse(error="not_found")`。
    - 成功 -> 直接回傳與 `MaintenanceResponse` 相容的 dict（服務層已回
      plain dict，故不套 `response_model`，避免對降級欄位做過嚴驗證）。
    """
    try:
        result = await get_stock_maintenance(code, n, client)
    except CodeError as exc:
        return JSONResponse(
            status_code=422,
            content=ErrorResponse(
                error="invalid_code", message=exc.reason, code="9100"
            ).model_dump(),
        )
    except MarketNotFoundError as exc:
        return JSONResponse(
            status_code=422,
            content=ErrorResponse(
                error="not_found",
                message=f"探測不到代號 {exc.code} 所屬市場",
            ).model_dump(),
        )
    return result
