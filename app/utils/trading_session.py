"""FN-006：交易時段判斷（含 Phase 4 複審修正第 3 點：防國定假日誤標）。

`detect_session` 僅依「現在是否週一~五 09:00–13:30（Asia/Taipei）」判斷盤中/收盤，
不知道國定假日。因此對外顯示「即時 / 收盤」時，需另外用 `is_intraday_for`
比對資料來源實際回傳的日期（如 MIS 的 d 欄位）是否等於系統今日，避免休市日
把「昨日收盤資料」誤標成「即時」。

僅使用標準庫 `zoneinfo`（Python 3.11 內建），不引入第三方 tz 套件。
"""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.config import SESSION_END, SESSION_START, TZ

__all__ = ["detect_session", "is_intraday_for"]

_WEEKDAY_SATURDAY = 5  # datetime.weekday(): Mon=0 ... Sun=6


def _resolve_tz() -> ZoneInfo:
    """將 config.TZ 正規化為 `ZoneInfo`（TZ 可能已是 ZoneInfo 或時區名稱字串）。"""
    if isinstance(TZ, ZoneInfo):
        return TZ
    return ZoneInfo(str(TZ))


def _resolve_bound(value: time | str) -> time:
    """將 config.SESSION_START/END 正規化為 `time`（可能是 time 物件或 "HH:MM" 字串）。"""
    if isinstance(value, time):
        return value
    hour_str, minute_str = str(value).split(":")[:2]
    return time(int(hour_str), int(minute_str))


def _now_in_taipei(now: datetime | None, tz: ZoneInfo) -> datetime:
    if now is None:
        return datetime.now(tz)
    if now.tzinfo is None:
        return now.replace(tzinfo=tz)
    return now.astimezone(tz)


def detect_session(now: datetime | None = None) -> str:
    """回傳 "intraday" 或 "closed"。

    `now=None` 時取當下台北時間。僅當「週一~五」且「09:00 <= t <= 13:30」
    （皆以 Asia/Taipei 為準）才回 "intraday"，否則一律 "closed"。
    """
    tz = _resolve_tz()
    current = _now_in_taipei(now, tz)

    if current.weekday() >= _WEEKDAY_SATURDAY:
        return "closed"

    start = _resolve_bound(SESSION_START)
    end = _resolve_bound(SESSION_END)
    if start <= current.time() <= end:
        return "intraday"
    return "closed"


def is_intraday_for(data_date_ymd: str, now: datetime | None = None) -> str:
    """給 price adapter 用：判斷應標示「即時」或「收盤」。

    只有當資料來源回傳的日期 `data_date_ymd`（格式 "YYYYMMDD"）等於系統今日
    （Asia/Taipei）且 `detect_session(now) == "intraday"` 時才回 "即時"，
    否則一律回 "收盤"。此設計可防止國定假日 MIS 回傳前一交易日資料時被
    誤標為「即時」。
    """
    tz = _resolve_tz()
    current = _now_in_taipei(now, tz)
    today_ymd = current.strftime("%Y%m%d")

    if data_date_ymd == today_ymd and detect_session(current) == "intraday":
        return "即時"
    return "收盤"
