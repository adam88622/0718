"""FN-004/FN-005：日期轉換與所需月份回推工具。

- ROC（民國年）與西元日期互轉。
- TWSE 用 YYYYMMDD、TPEx 用 YYYY/MM/DD（西元，斜線）。
- months_to_fetch：回推足以覆蓋 N 個交易日的月份代表日（每月 1 號）。
"""

from __future__ import annotations

import math
from datetime import date

__all__ = [
    "roc_to_date",
    "date_to_roc",
    "date_to_ad_slash",
    "date_to_ymd",
    "months_to_fetch",
]


def roc_to_date(roc: str) -> date:
    """解析民國年日期字串（如 " 115/07/01 "）為 `date`。

    容錯：前後空白會被去除。年份 = 民國年 + 1911。
    """
    cleaned = roc.strip()
    parts = cleaned.split("/")
    if len(parts) != 3:
        raise ValueError(f"無效的民國年日期格式：{roc!r}")
    try:
        roc_year, month, day = (int(p.strip()) for p in parts)
    except ValueError as exc:
        raise ValueError(f"無效的民國年日期格式：{roc!r}") from exc
    return date(roc_year + 1911, month, day)


def date_to_roc(d: date) -> str:
    """`date` -> "115/07/01"（民國年，不補零年份、月日補零）。"""
    return f"{d.year - 1911}/{d.month:02d}/{d.day:02d}"


def date_to_ad_slash(d: date) -> str:
    """`date` -> "2026/07/01"（西元，斜線分隔，TPEx tradingStock 用）。"""
    return f"{d.year:04d}/{d.month:02d}/{d.day:02d}"


def date_to_ymd(d: date) -> str:
    """`date` -> "20260701"（西元，TWSE 用）。"""
    return f"{d.year:04d}{d.month:02d}{d.day:02d}"


def months_to_fetch(n: int, today: date) -> list[date]:
    """回傳需抓取的各月代表日（每月 1 號），由近到遠排序。

    數量 = max(2, ceil(n/18) + 1)，以確保涵蓋足夠交易日（每月約 18 個交易日估算）。
    """
    count = max(2, math.ceil(n / 18) + 1)
    result: list[date] = []
    year, month = today.year, today.month
    for _ in range(count):
        result.append(date(year, month, 1))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return result
