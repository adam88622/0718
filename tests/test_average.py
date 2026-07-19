"""FN-016/FN-017：compute_average（純函式）與 get_n_day_average（編排，mock adapter）測試。"""

from __future__ import annotations

from datetime import date

import pytest

from app.services import average as average_module
from app.services.average import compute_average, get_n_day_average


def _series(pairs: list[tuple[str, float]]) -> list[tuple[date, float]]:
    return [(date.fromisoformat(d), c) for d, c in pairs]


class TestComputeAverage:
    def test_normal_n(self) -> None:
        series = _series(
            [
                ("2026-07-01", 100.0),
                ("2026-07-02", 102.0),
                ("2026-07-03", 104.0),
                ("2026-07-06", 106.0),
                ("2026-07-07", 108.0),
            ]
        )
        avg, used = compute_average(series, 3)
        # 手算：(104+106+108)/3 = 106.0
        assert avg == 106.0
        assert len(used) == 3
        assert used[0][1] == 104.0

    def test_insufficient_returns_all_available(self) -> None:
        series = _series([("2026-07-01", 10.0), ("2026-07-02", 20.0)])
        avg, used = compute_average(series, 5)
        assert avg == 15.0
        assert len(used) == 2

    def test_empty_series(self) -> None:
        avg, used = compute_average([], 5)
        assert avg is None
        assert used == []

    def test_n_le_zero(self) -> None:
        series = _series([("2026-07-01", 10.0)])
        avg, used = compute_average(series, 0)
        assert avg is None
        assert used == []

    def test_n_equals_one(self) -> None:
        series = _series([("2026-07-01", 10.0), ("2026-07-02", 20.0)])
        avg, used = compute_average(series, 1)
        assert avg == 20.0
        assert len(used) == 1

    def test_rounding_two_decimal_places(self) -> None:
        series = _series(
            [("2026-07-01", 1.0), ("2026-07-02", 1.0), ("2026-07-03", 1.0)]
        )
        avg, _ = compute_average(series, 3)
        assert avg == 1.0
        series2 = _series([("2026-07-01", 10.0), ("2026-07-02", 11.0)])
        avg2, _ = compute_average(series2, 2)
        assert avg2 == 10.5


@pytest.fixture
def patch_adapters(monkeypatch: pytest.MonkeyPatch):
    """回傳一個 helper，方便逐項測試設定 official/yahoo 回傳值。"""

    def _apply(official_series: list[tuple[date, float]], yahoo_series: list[tuple[date, float]]):
        async def _fake_official(code, market, n, client, today):
            return official_series

        async def _fake_yahoo(code, market, n, client):
            return yahoo_series

        monkeypatch.setattr(average_module, "fetch_history_official", _fake_official)
        monkeypatch.setattr(average_module, "fetch_history_yahoo", _fake_yahoo)

    return _apply


class TestGetNDayAverage:
    async def test_official_sufficient_no_yahoo_needed(
        self, patch_adapters, dummy_client
    ) -> None:
        official = _series(
            [(f"2026-07-{d:02d}", 100.0 + d) for d in range(1, 8)]
        )
        patch_adapters(official, [])
        result = await get_n_day_average("2330", "tse", 5, dummy_client, date(2026, 7, 10))
        assert result["status"] == "ok"
        assert result["source"] == "TWSE官方"
        assert result["count"] == 5
        assert result["insufficient"] is False

    async def test_official_insufficient_yahoo_supplements(
        self, patch_adapters, dummy_client
    ) -> None:
        official = _series([("2026-07-06", 100.0), ("2026-07-07", 101.0)])
        yahoo = _series(
            [
                ("2026-07-01", 90.0),
                ("2026-07-02", 91.0),
                ("2026-07-03", 92.0),
                ("2026-07-06", 999.0),  # 官方已有此日期，不應被覆蓋
            ]
        )
        patch_adapters(official, yahoo)
        result = await get_n_day_average("2330", "tse", 5, dummy_client, date(2026, 7, 10))
        assert result["status"] == "ok"
        assert result["source"] == "Yahoo"
        assert result["count"] == 5
        # 官方 2026-07-06 值應保持 100.0，不被 yahoo 999.0 覆蓋
        assert result["insufficient"] is False

    async def test_both_empty_returns_no_data(
        self, patch_adapters, dummy_client
    ) -> None:
        patch_adapters([], [])
        result = await get_n_day_average("2330", "tse", 5, dummy_client, date(2026, 7, 10))
        assert result["status"] == "no_data"
        assert result["source"] == "TWSE官方"

    async def test_insufficient_after_merge(self, patch_adapters, dummy_client) -> None:
        official = _series([("2026-07-06", 100.0)])
        yahoo = _series([("2026-07-01", 90.0)])
        patch_adapters(official, yahoo)
        result = await get_n_day_average("2330", "tse", 10, dummy_client, date(2026, 7, 10))
        assert result["status"] == "ok"
        assert result["insufficient"] is True
        assert result["note"] is not None
        assert "不足" in result["note"]

    async def test_split_breakpoint_trims_and_notes(
        self, patch_adapters, dummy_client
    ) -> None:
        # 官方序列含分割斷點：舊價 300 附近，事件後降到 12 附近
        official = _series(
            [
                ("2026-07-01", 306.0),
                ("2026-07-02", 300.0),
                ("2026-07-03", 302.0),
                ("2026-07-06", 12.2),
                ("2026-07-07", 12.1),
                ("2026-07-08", 12.15),
            ]
        )
        patch_adapters(official, [])
        result = await get_n_day_average("2330", "tse", 10, dummy_client, date(2026, 7, 10))
        assert result["status"] == "ok"
        assert result["count"] == 3
        assert result["note"] is not None
        assert "除權息" in result["note"] or "分割" in result["note"]
        # 均價只用事件後三筆：(12.2+12.1+12.15)/3
        assert result["value"] == round((12.2 + 12.1 + 12.15) / 3, 2)
