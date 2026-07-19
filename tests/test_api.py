"""API 整合測試（TestClient + mock service 層），驗證契約與降級/例外處理。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.routes.alerts as alerts_route
import app.routes.maintenance as maintenance_route
from app.main import app
from app.services.maintenance_service import MarketNotFoundError
from app.utils.codes import CodeError


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


class TestHealth:
    def test_health_200(self, client: TestClient) -> None:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["service"] == "margin-maintenance-tracker"
        assert "time" in body


class TestMaintenanceValidation:
    def test_non_numeric_code_returns_422(self, client: TestClient) -> None:
        resp = client.get("/api/maintenance", params={"code": "abc"})
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"] == "invalid_code"

    def test_warrant_prefix_code_returns_422(self, client: TestClient) -> None:
        resp = client.get("/api/maintenance", params={"code": "9100"})
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"] == "invalid_code"

    def test_wrong_length_code_returns_422(self, client: TestClient) -> None:
        resp = client.get("/api/maintenance", params={"code": "233"})
        assert resp.status_code == 422


class TestMaintenanceSuccess:
    def test_success_path_structure(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _fake_get_stock_maintenance(code, n, client):
            return {
                "code": "2330",
                "name": "台積電",
                "market": "tse",
                "session": "intraday",
                "n_requested": n,
                "price": {
                    "value": 600.0,
                    "price_type": "即時",
                    "is_fallback": False,
                    "prev_close": 598.0,
                    "as_of": "13:25:00 / 20260715",
                    "name": "台積電",
                    "source": "TWSE-MIS",
                    "status": "ok",
                },
                "average": {
                    "value": 590.0,
                    "count": 20,
                    "start": "2026-06-16",
                    "end": "2026-07-15",
                    "n_requested": 20,
                    "insufficient": False,
                    "note": None,
                    "source": "TWSE官方",
                    "status": "ok",
                },
                "margin": {
                    "balance_lots": 12345,
                    "as_of": "2026-07-14",
                    "source": "TWSE-MI_MARGN",
                    "status": "ok",
                },
                "ratio": {
                    "value": 169.49,
                    "warning": "safe",
                    "formula": {
                        "price": 600.0,
                        "n_day_avg": 590.0,
                        "margin_rate": 0.6,
                        "expression": "600.0 / (590.0 * 0.6) * 100",
                    },
                    "status": "ok",
                },
                "generated_at": "2026-07-15T13:25:08+08:00",
            }

        monkeypatch.setattr(
            maintenance_route, "get_stock_maintenance", _fake_get_stock_maintenance
        )
        resp = client.get("/api/maintenance", params={"code": "2330", "n": 20})
        assert resp.status_code == 200
        body = resp.json()
        for key in ("price", "average", "margin", "ratio", "code", "market"):
            assert key in body
        assert body["ratio"]["value"] == 169.49
        assert body["price"]["status"] == "ok"

    def test_market_not_found_returns_422(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _raise_market_not_found(code, n, client):
            raise MarketNotFoundError(code)

        monkeypatch.setattr(
            maintenance_route, "get_stock_maintenance", _raise_market_not_found
        )
        resp = client.get("/api/maintenance", params={"code": "1234"})
        assert resp.status_code == 422
        assert resp.json()["error"] == "not_found"

    def test_code_error_raised_deep_in_service_still_returns_422(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _raise_code_error(code, n, client):
            raise CodeError("代號需為 4 碼數字", code)

        monkeypatch.setattr(
            maintenance_route, "get_stock_maintenance", _raise_code_error
        )
        resp = client.get("/api/maintenance", params={"code": "2330"})
        assert resp.status_code == 422
        assert resp.json()["error"] == "invalid_code"

    def test_unexpected_exception_returns_formatted_500_not_raw_traceback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _boom(code, n, client):
            raise RuntimeError("unexpected upstream failure")

        monkeypatch.setattr(maintenance_route, "get_stock_maintenance", _boom)

        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get("/api/maintenance", params={"code": "2330"})

        assert resp.status_code == 500
        body = resp.json()
        # 全域 handler 需回傳格式化的 ErrorResponse，不外洩堆疊資訊
        assert body["error"] == "internal_error"
        assert "message" in body
        assert "RuntimeError" not in body["message"]
        assert "Traceback" not in body["message"]


class TestAlerts:
    def test_alerts_success_structure(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _fake_build_alert_list(n, client, today):
            return {
                "n_requested": n,
                "price_as_of": "2026-07-15",
                "margin_as_of_tse": "2026-07-14",
                "margin_as_of_otc": "2026-07-14",
                "count": 1,
                "excluded": 0,
                "bands": {
                    "danger": "< 130.0",
                    "warn1": "130.0 ~ 150.0",
                    "warn2": "150.0 ~ 166.67",
                    "safe": ">= 166.67",
                },
                "items": [
                    {
                        "code": "2330",
                        "name": "台積電",
                        "market": "tse",
                        "price": 600.0,
                        "n_day_avg": 590.0,
                        "avg_days": 20,
                        "margin_lots": 12345,
                        "ratio": 169.49,
                        "band": "safe",
                        "adjusted": False,
                    }
                ],
                "generated_at": "2026-07-15T13:25:08+08:00",
            }

        monkeypatch.setattr(alerts_route, "build_alert_list", _fake_build_alert_list)
        resp = client.get("/api/alerts", params={"n": 20})
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "bands" in body
        assert body["items"][0]["code"] == "2330"
