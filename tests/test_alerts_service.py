"""FN-010 全市場警示服務測試：_classify_band（純函式）與 build_alert_list（編排，mock adapter）。"""

from __future__ import annotations

from datetime import date

import pytest

from app.services import alerts_service
from app.services.alerts_service import (
    _classify_band,
    _gate_and_tag,
    build_alert_list,
)


class TestGateAndTag:
    def test_chronic_excluded(self) -> None:
        # 連續 5 日都 <130 → 排除
        exclude, fresh = _gate_and_tag([125, 122, 120, 118, 115])
        assert exclude is True and fresh is False

    def test_fresh_washout(self) -> None:
        # 前幾日 >=130，今日急殺跌破且單日跌幅大 → 急殺清洗
        exclude, fresh = _gate_and_tag([160, 158, 155, 150, 125])
        assert exclude is False and fresh is True

    def test_slow_drift_below_not_fresh(self) -> None:
        # 緩跌跌破、單日跌幅小 → 非急殺
        exclude, fresh = _gate_and_tag([133, 132, 131, 130, 129])
        assert fresh is False

    def test_healthy_not_flagged(self) -> None:
        exclude, fresh = _gate_and_tag([180, 178, 176, 175, 174])
        assert exclude is False and fresh is False

    def test_empty(self) -> None:
        assert _gate_and_tag([]) == (False, False)


class TestClassifyBand:
    def test_none_is_na(self) -> None:
        assert _classify_band(None) == "na"

    def test_below_danger(self) -> None:
        assert _classify_band(129.9) == "danger"

    def test_at_danger_boundary_is_warn1(self) -> None:
        assert _classify_band(130.0) == "warn1"

    def test_just_below_mid_is_warn1(self) -> None:
        assert _classify_band(149.9) == "warn1"

    def test_at_mid_boundary_is_warn2(self) -> None:
        assert _classify_band(150.0) == "warn2"

    def test_just_below_safe_is_warn2(self) -> None:
        assert _classify_band(166.66) == "warn2"

    def test_at_safe_boundary_is_safe(self) -> None:
        assert _classify_band(166.67) == "safe"

    def test_well_above_safe(self) -> None:
        assert _classify_band(300.0) == "safe"


@pytest.fixture(autouse=True)
def _clear_cache():
    """每個測試前後清空模組級快取，避免互相污染。"""
    alerts_service._cache.clear()
    yield
    alerts_service._cache.clear()


@pytest.fixture
def patch_bulk(monkeypatch: pytest.MonkeyPatch):
    def _apply(universe: dict, matrix: dict, call_counter: dict | None = None):
        async def _fake_universe(client, today):
            if call_counter is not None:
                call_counter["universe"] = call_counter.get("universe", 0) + 1
            return universe

        async def _fake_matrix(codes_by_market, n, client, today):
            if call_counter is not None:
                call_counter["matrix"] = call_counter.get("matrix", 0) + 1
            return matrix

        async def _fake_costs(client, today):
            # 預設回空 → build_alert_list 退回 N 日均價路徑，保留既有測試預期。
            return {}

        async def _fake_stock_recent(client, today):
            # 預設回空 → 雙閘門不排除、不標記，保留既有測試預期。
            return {}

        monkeypatch.setattr(alerts_service, "fetch_margin_universe", _fake_universe)
        monkeypatch.setattr(alerts_service, "build_close_matrix", _fake_matrix)
        monkeypatch.setattr(alerts_service, "compute_current_costs", _fake_costs)
        monkeypatch.setattr(alerts_service, "compute_stock_recent", _fake_stock_recent)
        monkeypatch.setattr(
            alerts_service, "_load_recent_bundle", lambda: {"dates": [], "ratio": {}}
        )

    return _apply


class TestBuildAlertList:
    async def test_normal_flow_sorted_and_banded(
        self, patch_bulk, dummy_client
    ) -> None:
        universe = {
            "tse": {"2330": 1000, "2317": 500},
            "otc": {"6488": 200},
            "names": {"2330": "台積電", "2317": "鴻海", "6488": "環球晶"},
            "as_of_tse": "2026-07-14",
            "as_of_otc": "2026-07-14",
        }
        matrix = {
            "tse": {
                "2330": [100.0, 100.0, 100.0],  # ratio = 100/(100*0.6)*100=166.67 safe
                "2317": [60.0, 60.0, 60.0],  # ratio = 60/(60*0.6)*100=166.67 safe
            },
            "otc": {"6488": [50.0, 50.0, 40.0]},  # ratio = 40/(50*0.6)*100=133.33 warn1
            "price_as_of": "2026-07-14",
        }
        patch_bulk(universe, matrix)
        result = await build_alert_list(20, dummy_client, date(2026, 7, 15))

        assert result["count"] == 3
        assert result["excluded"] == 0
        # 依 ratio 升序排列，最低者在前
        ratios = [item["ratio"] for item in result["items"]]
        assert ratios == sorted(ratios)
        codes = [item["code"] for item in result["items"]]
        assert "6488" in codes
        otc_item = next(i for i in result["items"] if i["code"] == "6488")
        assert otc_item["band"] == "warn1"
        assert otc_item["market"] == "otc"
        assert "bands" in result
        assert set(result["bands"].keys()) == {"danger", "warn1", "warn2", "safe"}

    async def test_excludes_codes_without_close_data(
        self, patch_bulk, dummy_client
    ) -> None:
        universe = {
            "tse": {"2330": 1000, "9999": 100},
            "otc": {},
            "names": {},
            "as_of_tse": "2026-07-14",
            "as_of_otc": None,
        }
        matrix = {
            "tse": {"2330": [100.0, 100.0]},  # 9999 無收盤資料
            "otc": {},
            "price_as_of": "2026-07-14",
        }
        patch_bulk(universe, matrix)
        result = await build_alert_list(20, dummy_client, date(2026, 7, 15))
        assert result["count"] == 1
        assert result["excluded"] == 1

    async def test_split_breakpoint_trimmed_and_flagged_adjusted(
        self, patch_bulk, dummy_client
    ) -> None:
        universe = {
            "tse": {"2330": 1000},
            "otc": {},
            "names": {},
            "as_of_tse": "2026-07-14",
            "as_of_otc": None,
        }
        matrix = {
            "tse": {"2330": [306.0, 300.0, 302.0, 12.2, 12.1, 12.15]},
            "otc": {},
            "price_as_of": "2026-07-14",
        }
        patch_bulk(universe, matrix)
        result = await build_alert_list(20, dummy_client, date(2026, 7, 15))
        assert result["count"] == 1
        item = result["items"][0]
        assert item["adjusted"] is True
        assert item["avg_days"] == 3
        assert item["price"] == 12.15

    async def test_cache_hit_within_ttl_avoids_recall(
        self, patch_bulk, dummy_client
    ) -> None:
        universe = {
            "tse": {"2330": 1000},
            "otc": {},
            "names": {},
            "as_of_tse": "2026-07-14",
            "as_of_otc": None,
        }
        matrix = {"tse": {"2330": [100.0, 100.0]}, "otc": {}, "price_as_of": "2026-07-14"}
        counter: dict = {}
        patch_bulk(universe, matrix, counter)

        result1 = await build_alert_list(20, dummy_client, date(2026, 7, 15))
        result2 = await build_alert_list(20, dummy_client, date(2026, 7, 15))

        assert counter["universe"] == 1
        assert counter["matrix"] == 1
        assert result1 is result2

    async def test_n_clamped_to_valid_range(self, patch_bulk, dummy_client) -> None:
        universe = {
            "tse": {"2330": 1000},
            "otc": {},
            "names": {},
            "as_of_tse": "2026-07-14",
            "as_of_otc": None,
        }
        matrix = {"tse": {"2330": [100.0]}, "otc": {}, "price_as_of": "2026-07-14"}
        patch_bulk(universe, matrix)
        # 要求 n=99999 應被 clamp 到 N_MAX(250)
        result = await build_alert_list(99999, dummy_client, date(2026, 7, 15))
        assert result["n_requested"] <= 250

    async def test_empty_universe_returns_zero_items(
        self, patch_bulk, dummy_client
    ) -> None:
        universe = {"tse": {}, "otc": {}, "names": {}, "as_of_tse": None, "as_of_otc": None}
        matrix = {"tse": {}, "otc": {}, "price_as_of": None}
        patch_bulk(universe, matrix)
        result = await build_alert_list(20, dummy_client, date(2026, 7, 15))
        assert result["count"] == 0
        assert result["items"] == []
