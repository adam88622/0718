"""FN-006：交易時段判斷測試（含防國定假日誤標邏輯）。"""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from app.utils.trading_session import detect_session, is_intraday_for

_TZ = ZoneInfo("Asia/Taipei")


def _a_monday(year: int = 2026) -> date:
    """回傳指定年份 ISO 第 10 週的週一（不依賴記憶中的星期對照，穩健可靠）。"""
    return date.fromisocalendar(year, 10, 1)


def _a_saturday(year: int = 2026) -> date:
    return date.fromisocalendar(year, 10, 6)


def _a_sunday(year: int = 2026) -> date:
    return date.fromisocalendar(year, 10, 7)


def _dt(d: date, t: time) -> datetime:
    return datetime(d.year, d.month, d.day, t.hour, t.minute, tzinfo=_TZ)


class TestDetectSession:
    def test_before_open_08_59_is_closed(self) -> None:
        monday = _a_monday()
        assert detect_session(_dt(monday, time(8, 59))) == "closed"

    def test_at_open_09_00_is_intraday(self) -> None:
        monday = _a_monday()
        assert detect_session(_dt(monday, time(9, 0))) == "intraday"

    def test_at_close_13_30_is_intraday(self) -> None:
        monday = _a_monday()
        assert detect_session(_dt(monday, time(13, 30))) == "intraday"

    def test_after_close_13_31_is_closed(self) -> None:
        monday = _a_monday()
        assert detect_session(_dt(monday, time(13, 31))) == "closed"

    def test_midday_intraday(self) -> None:
        monday = _a_monday()
        assert detect_session(_dt(monday, time(11, 0))) == "intraday"

    def test_saturday_is_closed_even_during_session_hours(self) -> None:
        saturday = _a_saturday()
        assert detect_session(_dt(saturday, time(10, 0))) == "closed"

    def test_sunday_is_closed(self) -> None:
        sunday = _a_sunday()
        assert detect_session(_dt(sunday, time(10, 0))) == "closed"


class TestIsIntradayFor:
    def test_data_date_matches_today_and_in_session_is_realtime(self) -> None:
        monday = _a_monday()
        now = _dt(monday, time(10, 0))
        data_date = monday.strftime("%Y%m%d")
        assert is_intraday_for(data_date, now) == "即時"

    def test_data_date_differs_from_today_is_closing(self) -> None:
        # 模擬國定假日：MIS 回傳前一交易日資料，系統今日與資料日不同
        monday = _a_monday()
        now = _dt(monday, time(10, 0))
        stale_date = date.fromisocalendar(2026, 9, 5).strftime("%Y%m%d")
        assert is_intraday_for(stale_date, now) == "收盤"

    def test_data_date_matches_today_but_outside_session_is_closing(self) -> None:
        monday = _a_monday()
        now = _dt(monday, time(15, 0))  # 已收盤時段
        data_date = monday.strftime("%Y%m%d")
        assert is_intraday_for(data_date, now) == "收盤"

    def test_weekend_data_date_matches_today_still_closing(self) -> None:
        saturday = _a_saturday()
        now = _dt(saturday, time(10, 0))
        data_date = saturday.strftime("%Y%m%d")
        assert is_intraday_for(data_date, now) == "收盤"
