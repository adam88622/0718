"""融資成本加權滾動引擎測試（見 docs/margin-cost-algorithm.md）。"""

from __future__ import annotations

from datetime import date

import pytest

from app.services import margin_cost
from app.services.margin_cost import compute_current_costs, load_seed, roll_cost


class TestRollCost:
    def test_verified_2327_case(self) -> None:
        # 反向工程對答案：2327 於 2026-06-30 由 886.7276 滾到 912.84
        got = roll_cost(886.7276, buy=5572, balance=54043, close=1140.0)
        assert round(got, 2) == 912.84

    def test_balance_zero_returns_prev(self) -> None:
        assert roll_cost(100.0, buy=10, balance=0, close=50.0) == 100.0

    def test_zero_buy_unchanged(self) -> None:
        assert roll_cost(100.0, buy=0, balance=5000, close=50.0) == 100.0

    def test_buy_equals_balance_becomes_close(self) -> None:
        assert roll_cost(100.0, buy=5000, balance=5000, close=50.0) == 50.0

    def test_buy_exceeds_balance_clamped(self) -> None:
        # 權重 clamp 至 1 → 等於 close，不會過衝
        assert roll_cost(100.0, buy=9999, balance=5000, close=50.0) == 50.0

    def test_moves_toward_close(self) -> None:
        got = roll_cost(100.0, buy=500, balance=5000, close=50.0)  # w=0.1
        assert got == pytest.approx(95.0)


class TestLoadSeed:
    def test_seed_loads_known_stocks(self) -> None:
        cost, seed_date = load_seed()
        assert seed_date == date(2026, 7, 17)
        # 2330/2327 應在種子中，值與檔案一致
        assert round(cost["2327"], 2) == 884.77
        assert round(cost["2330"], 2) == 2348.22


class TestComputeCurrentCosts:
    async def test_no_roll_days_returns_seed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 種子日當天（無後續交易日）→ 成本 = 種子值，roll_days=0
        margin_cost._result_cache.clear()

        async def _empty_snapshot(day, client, today):
            return {}, {}  # 視為非交易日

        monkeypatch.setattr(margin_cost, "_snapshot", _empty_snapshot)
        result = await compute_current_costs(client=object(), today=date(2026, 7, 17))
        assert result["2327"]["value"] == pytest.approx(884.77, abs=0.01)
        assert result["2327"]["roll_days"] == 0
        assert result["2327"]["source"] == "加權融資成本"

    async def test_one_roll_day_applies_recurrence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        margin_cost._result_cache.clear()

        async def _one_day(day, client, today):
            if day == date(2026, 7, 18):
                return {"2327": (5572, 54043)}, {"2327": 1140.0}
            return {}, {}

        monkeypatch.setattr(margin_cost, "_snapshot", _one_day)
        result = await compute_current_costs(client=object(), today=date(2026, 7, 18))
        # 種子 884.7673 滾一天 → 依遞迴
        expected = roll_cost(884.7673, 5572, 54043, 1140.0)
        assert result["2327"]["value"] == pytest.approx(round(expected, 4), abs=0.01)
        assert result["2327"]["roll_days"] == 1
