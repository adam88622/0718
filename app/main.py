"""FN-022：FastAPI app 組裝層 — lifespan + router 掛載 + static mount + 全域例外處理。

流程順序（§2 單頁 serve 規範）：先 include_router（health/maintenance/industry），
最後才 mount static（避免 static 的 `/` catch-all 蓋掉 `/api/*` 路由）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.staticfiles import StaticFiles

from app.config import resolve_base_dir
from app.http_client import close_client
from app.models import ErrorResponse
from app.routes.alerts import router as alerts_router
from app.routes.health import router as health_router
from app.routes.industry import router as industry_router
from app.routes.maintenance import router as maintenance_router

__all__ = ["app", "create_app"]


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """應用生命週期：startup 無需特別動作（httpx client 由 `get_client` 懶建立）；
    shutdown 關閉共用 httpx.AsyncClient，釋放連線。
    """
    yield
    await close_client()


def create_app() -> FastAPI:
    """建立並組裝 FastAPI 應用實例。"""
    app = FastAPI(title="margin-maintenance-tracker", lifespan=_lifespan)

    # 先註冊 API router，後 mount static，避免 static 的 "/" catch-all 蓋掉 /api/*
    app.include_router(health_router)
    app.include_router(maintenance_router)
    app.include_router(industry_router)
    app.include_router(alerts_router)

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """攔截所有未預期例外，回傳統一 ErrorResponse JSON，不外洩堆疊資訊。"""
        _ = request, exc
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error="internal_error", message="伺服器內部錯誤"
            ).model_dump(),
        )

    static_dir = resolve_base_dir() / "static"
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app


app = create_app()
