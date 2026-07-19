"""FN-009 detect_market adapter 測試（respx mock httpx，離線）。"""

from __future__ import annotations

import httpx
import respx

from app.adapters.market import detect_market
from app.config import MIS_STOCK_INFO_URL, YAHOO_CHART_URL

CODE = "2330"

TSE_URL = MIS_STOCK_INFO_URL.format(prefix="tse", code=CODE)
OTC_URL = MIS_STOCK_INFO_URL.format(prefix="otc", code=CODE)
YAHOO_TW_URL = YAHOO_CHART_URL.format(code=CODE, sfx="TW", range="5d")
YAHOO_TWO_URL = YAHOO_CHART_URL.format(code=CODE, sfx="TWO", range="5d")


def _mis_hit(code: str) -> dict:
    return {"msgArray": [{"c": code, "z": "600.0"}]}


def _mis_empty_shell(code: str) -> dict:
    # MIS 對錯誤市場前綴常回傳長度 1 的空殼（c='' 不等於查詢代號）
    return {"msgArray": [{"c": "", "z": "-"}]}


def _mis_no_msg_array() -> dict:
    return {"msgArray": []}


def _yahoo_has_close() -> dict:
    return {
        "chart": {
            "result": [{"indicators": {"quote": [{"close": [600.0, 601.0]}]}}]
        }
    }


def _yahoo_no_close() -> dict:
    return {"chart": {"result": [{"indicators": {"quote": [{"close": [None, None]}]}}]}}


class TestDetectMarket:
    async def test_tse_hit_on_first_probe(self) -> None:
        with respx.mock:
            respx.get(TSE_URL).mock(
                return_value=httpx.Response(200, json=_mis_hit(CODE))
            )
            async with httpx.AsyncClient() as client:
                result = await detect_market(CODE, client)
            assert result == "tse"

    async def test_tse_empty_shell_falls_through_to_otc_hit(self) -> None:
        with respx.mock:
            respx.get(TSE_URL).mock(
                return_value=httpx.Response(200, json=_mis_empty_shell(CODE))
            )
            respx.get(OTC_URL).mock(
                return_value=httpx.Response(200, json=_mis_hit(CODE))
            )
            async with httpx.AsyncClient() as client:
                result = await detect_market(CODE, client)
            assert result == "otc"

    async def test_both_mis_respond_but_empty_returns_none_without_yahoo_fallback(
        self,
    ) -> None:
        # MIS 兩者皆「有回應但空殼」（非無回應），依規格不應退而使用 Yahoo。
        with respx.mock:
            respx.get(TSE_URL).mock(
                return_value=httpx.Response(200, json=_mis_no_msg_array())
            )
            respx.get(OTC_URL).mock(
                return_value=httpx.Response(200, json=_mis_no_msg_array())
            )
            async with httpx.AsyncClient() as client:
                result = await detect_market(CODE, client)
            assert result is None

    async def test_mis_completely_unresponsive_falls_back_to_yahoo_tw(self) -> None:
        with respx.mock:
            respx.get(TSE_URL).mock(side_effect=httpx.ConnectError("boom"))
            respx.get(OTC_URL).mock(side_effect=httpx.ConnectError("boom"))
            respx.get(YAHOO_TW_URL).mock(
                return_value=httpx.Response(200, json=_yahoo_has_close())
            )
            async with httpx.AsyncClient() as client:
                result = await detect_market(CODE, client)
            assert result == "tse"

    async def test_mis_completely_unresponsive_yahoo_tw_empty_falls_back_otc(
        self,
    ) -> None:
        with respx.mock:
            respx.get(TSE_URL).mock(side_effect=httpx.ConnectError("boom"))
            respx.get(OTC_URL).mock(side_effect=httpx.ConnectError("boom"))
            respx.get(YAHOO_TW_URL).mock(
                return_value=httpx.Response(200, json=_yahoo_no_close())
            )
            respx.get(YAHOO_TWO_URL).mock(
                return_value=httpx.Response(200, json=_yahoo_has_close())
            )
            async with httpx.AsyncClient() as client:
                result = await detect_market(CODE, client)
            assert result == "otc"

    async def test_all_sources_fail_returns_none(self) -> None:
        with respx.mock:
            respx.get(TSE_URL).mock(side_effect=httpx.ConnectError("boom"))
            respx.get(OTC_URL).mock(side_effect=httpx.ConnectError("boom"))
            respx.get(YAHOO_TW_URL).mock(side_effect=httpx.ConnectError("boom"))
            respx.get(YAHOO_TWO_URL).mock(side_effect=httpx.ConnectError("boom"))
            async with httpx.AsyncClient() as client:
                result = await detect_market(CODE, client)
            assert result is None
