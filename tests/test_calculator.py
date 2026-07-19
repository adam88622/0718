"""FN-018/FN-019/trim_recent_continuous 純函式測試（最高價值，無網路）。"""

from __future__ import annotations

import math

from app.services.calculator import (
    classify_warning,
    compute_maintenance_ratio,
    trim_recent_continuous,
)


class TestComputeMaintenanceRatio:
    def test_normal_manual_calc(self) -> None:
        # 手算：120 / (100 * 0.6) * 100 = 200.0
        assert compute_maintenance_ratio(120.0, 100.0, 0.6) == 200.0

    def test_normal_manual_calc_2(self) -> None:
        # 手算：166.67 / (100 * 0.6) * 100 = 277.78 (四捨五入2位)
        result = compute_maintenance_ratio(166.67, 100.0, 0.6)
        assert result == round(166.67 / 60.0 * 100, 2)
        assert result == 277.78

    def test_default_rate_matches_config(self) -> None:
        # 未傳 rate 時採 config.MARGIN_RATE=0.6
        assert compute_maintenance_ratio(120.0, 100.0) == 200.0

    def test_n_avg_zero_returns_none(self) -> None:
        assert compute_maintenance_ratio(100.0, 0.0) is None

    def test_n_avg_negative_returns_none(self) -> None:
        assert compute_maintenance_ratio(100.0, -5.0) is None

    def test_n_avg_none_returns_none(self) -> None:
        assert compute_maintenance_ratio(100.0, None) is None

    def test_price_none_returns_none(self) -> None:
        assert compute_maintenance_ratio(None, 100.0) is None

    def test_both_none_returns_none(self) -> None:
        assert compute_maintenance_ratio(None, None) is None

    def test_result_never_inf_or_nan(self) -> None:
        for price, n_avg in [(None, 0.0), (100.0, None), (None, None), (100.0, 0.0)]:
            result = compute_maintenance_ratio(price, n_avg)
            assert result is None
            # 保底：就算未來實作改動，也不能是 inf/nan
            assert result != float("inf")
            if result is not None:
                assert not math.isnan(result)


class TestClassifyWarning:
    def test_below_danger_threshold(self) -> None:
        assert classify_warning(129.9) == "danger"

    def test_at_danger_boundary_is_warn(self) -> None:
        # 130 不 <130，故落在 warn（130~166.67 之間）
        assert classify_warning(130.0) == "warn"

    def test_just_below_safe_boundary_is_warn(self) -> None:
        assert classify_warning(166.66) == "warn"

    def test_at_safe_boundary_is_safe(self) -> None:
        assert classify_warning(166.67) == "safe"

    def test_well_above_safe_is_safe(self) -> None:
        assert classify_warning(200.0) == "safe"

    def test_none_is_na(self) -> None:
        assert classify_warning(None) == "na"

    def test_zero_is_danger(self) -> None:
        assert classify_warning(0.0) == "danger"

    def test_negative_is_danger(self) -> None:
        assert classify_warning(-10.0) == "danger"


class TestTrimRecentContinuous:
    def test_no_breakpoint_returns_unchanged(self) -> None:
        closes = [100.0, 101.0, 99.5, 102.0, 103.0]
        trimmed, was_trimmed = trim_recent_continuous(closes)
        assert trimmed == closes
        assert was_trimmed is False

    def test_split_breakpoint_keeps_only_segment_after_event(self) -> None:
        # 模擬除權/分割：舊價在 300 附近，事件後價格驟降至 12 附近
        closes = [306.0, 300.0, 302.0, 298.0, 12.2, 12.1, 12.15]
        trimmed, was_trimmed = trim_recent_continuous(closes)
        assert was_trimmed is True
        assert trimmed == [12.2, 12.1, 12.15]

    def test_split_breakpoint_reverse_case_price_jump_up(self) -> None:
        # 反分割：事件後價格從低跳升到高（例如 10 -> 100）
        closes = [10.0, 10.1, 9.9, 100.0, 101.0]
        trimmed, was_trimmed = trim_recent_continuous(closes)
        assert was_trimmed is True
        assert trimmed == [100.0, 101.0]

    def test_empty_sequence(self) -> None:
        trimmed, was_trimmed = trim_recent_continuous([])
        assert trimmed == []
        assert was_trimmed is False

    def test_single_element_sequence(self) -> None:
        trimmed, was_trimmed = trim_recent_continuous([42.0])
        assert trimmed == [42.0]
        assert was_trimmed is False

    def test_two_elements_no_breakpoint(self) -> None:
        trimmed, was_trimmed = trim_recent_continuous([100.0, 101.0])
        assert trimmed == [100.0, 101.0]
        assert was_trimmed is False

    def test_zero_value_triggers_protective_trim(self) -> None:
        closes = [50.0, 0.0, 100.0]
        trimmed, was_trimmed = trim_recent_continuous(closes)
        assert was_trimmed is True
        assert trimmed == [100.0]

    def test_negative_value_triggers_protective_trim(self) -> None:
        closes = [50.0, -1.0, 100.0]
        trimmed, was_trimmed = trim_recent_continuous(closes)
        assert was_trimmed is True
        assert trimmed == [100.0]

    def test_custom_threshold_default_trims_but_relaxed_does_not(self) -> None:
        # 100 -> 140 為 40% 跳空：預設門檻(0.35)視為斷點，放寬門檻(0.5)則不視為斷點
        closes = [100.0, 140.0]
        trimmed_default, was_trimmed_default = trim_recent_continuous(closes)
        assert was_trimmed_default is True
        assert trimmed_default == [140.0]

        trimmed_relaxed, was_trimmed_relaxed = trim_recent_continuous(
            closes, max_step=0.5
        )
        assert was_trimmed_relaxed is False
        assert trimmed_relaxed == closes
