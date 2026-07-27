"""F-012 大盤指標 market_service 測試。"""

from __future__ import annotations

from datetime import date

import pytest

from app.services import market_service
from app.services.market_service import (
    _classify_level,
    _moving_avg,
    get_market_indicator,
)


class TestMovingAvg:
    def test_enough(self) -> None:
        assert _moving_avg([1, 2, 3, 4], 2) == 3.5

    def test_insufficient(self) -> None:
        assert _moving_avg([1, 2], 5) is None


class TestClassifyLevel:
    def test_extreme_washout(self) -> None:
        # 低位（percentile 5%）且低於 MA60 → 極端清洗
        assert _classify_level(120.0, 130.0, 160.0, 0.05, -6.0) == "extreme_washout"

    def test_overheated(self) -> None:
        assert _classify_level(190.0, 180.0, 175.0, 0.9, 1.0) == "overheated"

    def test_washing(self) -> None:
        # 跌破 MA20 且下彎，但非極端低位
        assert _classify_level(150.0, 158.0, 165.0, 0.4, -2.0) == "washing"

    def test_normal(self) -> None:
        assert _classify_level(162.0, 160.0, 165.0, 0.5, 0.5) == "normal"


class TestGetMarketIndicator:
    async def test_merges_history_and_gap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        hist = [{"date": f"2026-06-{d:02d}", "ratio": 160.0 + d, "n": 1000}
                for d in range(1, 26)]

        def _fake_hist():
            return hist

        async def _fake_gap(client, today):
            return [{"date": "2026-07-01", "ratio": 120.0, "n": 1000}]

        monkeypatch.setattr(market_service, "_load_history", _fake_hist)
        monkeypatch.setattr(market_service, "compute_market_gap", _fake_gap)

        res = await get_market_indicator(client=object(), today=date(2026, 7, 1))
        assert res["status"] == "ok"
        # 缺口最後一筆成為 current
        assert res["current"] == 120.0
        assert res["as_of"] == "2026-07-01"
        # 120 明顯低於歷史 → 低位 percentile 小
        assert res["percentile"] <= 0.1

    async def test_no_data(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(market_service, "_load_history", lambda: [])

        async def _empty_gap(client, today):
            return []

        monkeypatch.setattr(market_service, "compute_market_gap", _empty_gap)
        res = await get_market_indicator(client=object(), today=date(2026, 7, 1))
        assert res["status"] == "no_data"
