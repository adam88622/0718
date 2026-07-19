"""FN-004/FN-005：日期轉換與月份回推工具測試。"""

from __future__ import annotations

import math
from datetime import date

import pytest

from app.utils.dates import (
    date_to_ad_slash,
    date_to_roc,
    date_to_ymd,
    months_to_fetch,
    roc_to_date,
)


class TestRocToDate:
    def test_normal(self) -> None:
        assert roc_to_date("115/07/01") == date(2026, 7, 1)

    def test_strips_whitespace(self) -> None:
        assert roc_to_date(" 115/07/01 ") == date(2026, 7, 1)

    def test_internal_whitespace_around_parts(self) -> None:
        assert roc_to_date("115/ 07 /01") == date(2026, 7, 1)

    def test_invalid_format_wrong_parts_count_raises(self) -> None:
        with pytest.raises(ValueError):
            roc_to_date("2026-07-01")

    def test_invalid_non_numeric_raises(self) -> None:
        with pytest.raises(ValueError):
            roc_to_date("abc/07/01")

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError):
            roc_to_date("")


class TestDateToRoc:
    def test_normal(self) -> None:
        assert date_to_roc(date(2026, 7, 1)) == "115/07/01"

    def test_pads_month_day(self) -> None:
        assert date_to_roc(date(2026, 1, 5)) == "115/01/05"

    def test_roundtrip_with_roc_to_date(self) -> None:
        d = date(2025, 12, 31)
        assert roc_to_date(date_to_roc(d)) == d


class TestDateToAdSlash:
    def test_normal(self) -> None:
        assert date_to_ad_slash(date(2026, 7, 1)) == "2026/07/01"

    def test_pads_single_digit_month_day(self) -> None:
        assert date_to_ad_slash(date(2026, 1, 5)) == "2026/01/05"


class TestDateToYmd:
    def test_normal(self) -> None:
        assert date_to_ymd(date(2026, 7, 1)) == "20260701"

    def test_pads_single_digit_month_day(self) -> None:
        assert date_to_ymd(date(2026, 1, 5)) == "20260105"


class TestMonthsToFetch:
    def test_count_formula_small_n(self) -> None:
        today = date(2026, 7, 15)
        result = months_to_fetch(20, today)
        expected_count = max(2, math.ceil(20 / 18) + 1)
        assert len(result) == expected_count
        # 由近到遠，第一筆是當月 1 號
        assert result[0] == date(2026, 7, 1)

    def test_minimum_two_months_for_tiny_n(self) -> None:
        today = date(2026, 7, 15)
        result = months_to_fetch(1, today)
        assert len(result) == 2

    def test_large_n_more_months(self) -> None:
        today = date(2026, 7, 15)
        result = months_to_fetch(200, today)
        expected_count = max(2, math.ceil(200 / 18) + 1)
        assert len(result) == expected_count

    def test_crosses_year_boundary(self) -> None:
        today = date(2026, 1, 15)
        result = months_to_fetch(40, today)
        # 應回推跨到前一年 12 月
        assert date(2025, 12, 1) in result

    def test_descending_order_by_month(self) -> None:
        today = date(2026, 7, 15)
        result = months_to_fetch(40, today)
        for earlier, later in zip(result, result[1:]):
            assert earlier > later
