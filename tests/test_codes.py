"""FN-007：股票代號驗證測試。"""

from __future__ import annotations

import pytest

from app.utils.codes import CodeError, validate_stock_code


class TestValidateStockCode:
    def test_normal_four_digit_code(self) -> None:
        assert validate_stock_code("2330") == "2330"

    def test_normalizes_surrounding_whitespace(self) -> None:
        assert validate_stock_code("  2330  ") == "2330"

    def test_warrant_prefix_91_raises(self) -> None:
        with pytest.raises(CodeError) as exc_info:
            validate_stock_code("9100")
        assert exc_info.value.code == "9100"

    def test_warrant_prefix_91_any_suffix_raises(self) -> None:
        with pytest.raises(CodeError):
            validate_stock_code("9199")

    def test_three_digit_code_raises(self) -> None:
        with pytest.raises(CodeError):
            validate_stock_code("233")

    def test_five_digit_code_raises(self) -> None:
        with pytest.raises(CodeError):
            validate_stock_code("23300")

    def test_non_numeric_raises(self) -> None:
        with pytest.raises(CodeError):
            validate_stock_code("abcd")

    def test_empty_string_raises(self) -> None:
        with pytest.raises(CodeError):
            validate_stock_code("")

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(CodeError):
            validate_stock_code("   ")

    def test_mixed_alnum_raises(self) -> None:
        with pytest.raises(CodeError):
            validate_stock_code("23a0")

    def test_error_carries_reason_and_original_code(self) -> None:
        with pytest.raises(CodeError) as exc_info:
            validate_stock_code("abc")
        assert exc_info.value.code == "abc"
        assert exc_info.value.reason
