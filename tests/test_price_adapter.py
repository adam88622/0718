"""FN-010 fetch_price adapter 測試（respx mock httpx，離線）。"""

from __future__ import annotations

import httpx
import respx

from app.adapters.price import fetch_price
from app.config import MIS_STOCK_INFO_URL

CODE = "2330"
URL = MIS_STOCK_INFO_URL.format(prefix="tse", code=CODE)

# 用明顯的過去日期，確保無論實際跑測試的日期為何，price_type 一律判為「收盤」，
# 不受 detect_session/is_intraday_for 對「系統今日」比對影響（見 utils/trading_session.py）。
_PAST_DATE = "20200101"


class TestFetchPrice:
    async def test_normal_z_parses_correctly(self) -> None:
        payload = {
            "msgArray": [
                {
                    "c": CODE,
                    "n": "台積電",
                    "z": "600.5",
                    "y": "598.0",
                    "a": "601.0_601.5_",
                    "b": "600.0_599.5_",
                    "d": _PAST_DATE,
                    "t": "13:30:00",
                }
            ]
        }
        with respx.mock:
            respx.get(URL).mock(return_value=httpx.Response(200, json=payload))
            async with httpx.AsyncClient() as client:
                result = await fetch_price(CODE, "tse", client)

        assert result["status"] == "ok"
        assert result["value"] == 600.5
        assert result["prev_close"] == 598.0
        assert result["is_fallback"] is False
        assert result["price_type"] == "收盤"
        assert result["name"] == "台積電"
        assert result["source"] == "TWSE-MIS"

    async def test_z_dash_falls_back_to_midpoint(self) -> None:
        payload = {
            "msgArray": [
                {
                    "c": CODE,
                    "n": "台積電",
                    "z": "-",
                    "y": "598.0",
                    "a": "601.0_601.5_",
                    "b": "600.0_599.5_",
                    "d": _PAST_DATE,
                    "t": "09:00:00",
                }
            ]
        }
        with respx.mock:
            respx.get(URL).mock(return_value=httpx.Response(200, json=payload))
            async with httpx.AsyncClient() as client:
                result = await fetch_price(CODE, "tse", client)

        assert result["status"] == "ok"
        assert result["is_fallback"] is True
        # (601.0 + 600.0) / 2 = 600.5
        assert result["value"] == 600.5

    async def test_z_dash_no_quotes_falls_back_to_prev_close(self) -> None:
        payload = {
            "msgArray": [
                {
                    "c": CODE,
                    "n": "台積電",
                    "z": "-",
                    "y": "598.0",
                    "a": "",
                    "b": "",
                    "d": _PAST_DATE,
                    "t": "09:00:00",
                }
            ]
        }
        with respx.mock:
            respx.get(URL).mock(return_value=httpx.Response(200, json=payload))
            async with httpx.AsyncClient() as client:
                result = await fetch_price(CODE, "tse", client)

        assert result["status"] == "ok"
        assert result["is_fallback"] is True
        assert result["value"] == 598.0

    async def test_empty_msg_array_returns_no_data(self) -> None:
        with respx.mock:
            respx.get(URL).mock(
                return_value=httpx.Response(200, json={"msgArray": []})
            )
            async with httpx.AsyncClient() as client:
                result = await fetch_price(CODE, "tse", client)

        assert result["status"] == "no_data"
        assert result["source"] == "TWSE-MIS"

    async def test_endpoint_failure_returns_no_data(self) -> None:
        with respx.mock:
            respx.get(URL).mock(side_effect=httpx.ConnectError("boom"))
            async with httpx.AsyncClient() as client:
                result = await fetch_price(CODE, "tse", client)

        assert result["status"] == "no_data"
        assert result["source"] == "TWSE-MIS"

    async def test_malformed_json_returns_no_data(self) -> None:
        with respx.mock:
            respx.get(URL).mock(
                return_value=httpx.Response(200, content=b"not json")
            )
            async with httpx.AsyncClient() as client:
                result = await fetch_price(CODE, "tse", client)

        assert result["status"] == "no_data"
