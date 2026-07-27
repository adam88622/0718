"""融資成本（推估）加權平均成本法滾動引擎。

見 docs/margin-cost-algorithm.md（反向工程自券商級資料並以 TWSE/TPEx 對答案驗證）。

核心遞迴（每股）：
    融資成本[t] = 融資成本[t-1] + (今日融資買進 / 今日融資餘額)
                                    × (今日收盤價 − 融資成本[t-1])

策略：
- 以 `app/data/margin_cost_seed.json`（2026-07-17 券商級成本，1744 檔）為種子。
- 從種子日起，對每個交易日抓（全市場買進、今日餘額、收盤）滾到最新交易日。
- 歷史交易日快照永久快取（不變）；種子日無 roll 時，成本即種子值。
- 無種子的標的回傳 None，交由上層退回 N 日均價「簡易估計」。
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.adapters.bulk import (
    fetch_all_close_tpex,
    fetch_all_close_twse,
    fetch_all_margin_tpex,
    fetch_all_margin_twse,
)
from app.config import TZ, resolve_base_dir

__all__ = [
    "load_seed",
    "roll_cost",
    "compute_current_costs",
    "compute_market_gap",
    "compute_stock_recent",
]


def _is_common(code: str) -> bool:
    """普通股判斷（排除 ETF/ETN 首碼 0、TDR/權證 91、非 4 碼），供大盤指標用。"""
    return len(code) == 4 and code.isdigit() and code[0] != "0" and not code.startswith("91")

_SEED_PATH_PARTS = ("app", "data", "margin_cost_seed.json")
_MAX_ROLL_DAYS = 400  # 保護：種子過舊時的回補上限

# 種子（載入一次快取）
_seed_cache: tuple[dict[str, float], date] | None = None
# 每日全市場快照快取：ymd -> merged dict
_margin_snap_cache: dict[str, dict[str, tuple[int, int]]] = {}
_close_snap_cache: dict[str, dict[str, float]] = {}
# 整體滾動結果快取：target_ymd -> (computed_at, result)
_result_cache: dict[str, tuple[datetime, dict[str, dict[str, Any]]]] = {}
_RESULT_TTL = 300


def load_seed() -> tuple[dict[str, float], date]:
    """載入種子融資成本與種子日期。找不到檔案回傳 `({}, 很舊的日期)`。"""
    global _seed_cache
    if _seed_cache is not None:
        return _seed_cache
    path = resolve_base_dir().joinpath(*_SEED_PATH_PARTS)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        cost = {str(k): float(v) for k, v in raw.get("cost", {}).items()}
        seed_date = datetime.strptime(raw["seed_date"], "%Y-%m-%d").date()
    except Exception:  # noqa: BLE001 - 種子缺失時退化為空，上層走 fallback
        cost, seed_date = {}, date(2000, 1, 1)
    _seed_cache = (cost, seed_date)
    return _seed_cache


def roll_cost(prev: float, buy: int, balance: int, close: float) -> float:
    """單日遞迴：以今日買進佔今日餘額之權重，將成本朝今日收盤移動。

    `balance<=0` 時回傳 `prev`（無部位不更新）；權重 clamp 至 [0,1]
    （買進>餘額等異常時視為全數新部位）。
    """
    if balance <= 0:
        return prev
    w = buy / balance
    if w < 0:
        w = 0.0
    elif w > 1:
        w = 1.0
    return prev + w * (close - prev)


async def _snapshot(day: date, client: Any, today: date) -> tuple[
    dict[str, tuple[int, int]], dict[str, float]
]:
    """取某日全市場（上市+上櫃合併）融資(buy,bal) 與 收盤，帶快取。

    歷史日（day<today）永久快取；當日不快取。回傳 `(margin_map, close_map)`。
    """
    key = day.strftime("%Y%m%d")
    is_history = day < today
    if is_history and key in _margin_snap_cache:
        return _margin_snap_cache[key], _close_snap_cache[key]

    m_twse, m_tpex, c_twse, c_tpex = await asyncio.gather(
        fetch_all_margin_twse(day, client),
        fetch_all_margin_tpex(day, client),
        fetch_all_close_twse(day, client),
        fetch_all_close_tpex(day, client),
        return_exceptions=True,
    )
    margin: dict[str, tuple[int, int]] = {}
    close: dict[str, float] = {}
    for m in (m_twse, m_tpex):
        if isinstance(m, dict):
            margin.update(m)
    for c in (c_twse, c_tpex):
        if isinstance(c, dict):
            close.update(c)

    if is_history and margin and close:
        _margin_snap_cache[key] = margin
        _close_snap_cache[key] = close
    return margin, close


async def _roll_all(client: Any, today: date) -> dict[str, Any]:
    """核心：從種子滾到最新交易日，同時算出每個滾動日的大盤金額加權維持率。

    回傳 `{"costs": {code: {...}}, "market_gap": [{date,ratio,n}], "seed_date": iso}`。
    整體結果快取 `_RESULT_TTL` 秒（key=today）。
    """
    tz = ZoneInfo(TZ)
    now = datetime.now(tz)
    target_key = today.strftime("%Y%m%d")
    cached = _result_cache.get(target_key)
    if cached is not None and (now - cached[0]).total_seconds() < _RESULT_TTL:
        return cached[1]

    seed_costs, seed_date = load_seed()
    costs: dict[str, float] = dict(seed_costs)
    as_of = seed_date
    roll_days = 0
    market_gap: list[dict[str, Any]] = []
    # 每檔近 7 個滾動日維持率（供警示雙閘門用）：code -> [(date_iso, ratio)]
    stock_recent: dict[str, list[tuple[str, float]]] = {}

    day = seed_date + timedelta(days=1)
    guard = 0
    while day <= today and guard < _MAX_ROLL_DAYS:
        guard += 1
        margin, close = await _snapshot(day, client, today)
        if margin and close:  # 交易日
            day_iso = day.isoformat()
            for code, prev in list(costs.items()):
                bm = margin.get(code)
                px = close.get(code)
                if bm is None or px is None:
                    continue
                buy, bal = bm
                costs[code] = roll_cost(prev, buy, bal, px)
                # 捕捉該日維持率 = 收盤 /（成本×0.6）×100
                c = costs[code]
                if c > 0:
                    ratio = round(px / (c * 0.6) * 100, 2)
                    lst = stock_recent.setdefault(code, [])
                    lst.append((day_iso, ratio))
                    if len(lst) > 7:
                        del lst[0]
            # 該日大盤金額加權維持率（排除 ETF）
            num = den = 0.0
            n = 0
            for code, c in costs.items():
                if not _is_common(code):
                    continue
                bm = margin.get(code)
                px = close.get(code)
                if bm is None or px is None or c <= 0:
                    continue
                bal = bm[1]
                if bal <= 0:
                    continue
                num += px * bal
                den += c * bal * 0.6
                n += 1
            if den > 0:
                market_gap.append(
                    {"date": day.isoformat(), "ratio": round(num / den * 100, 2), "n": n}
                )
            as_of = day
            roll_days += 1
        day += timedelta(days=1)

    costs_out = {
        code: {
            "value": round(v, 4),
            "as_of": as_of.isoformat(),
            "roll_days": roll_days,
            "source": "加權融資成本",
        }
        for code, v in costs.items()
    }
    result = {
        "costs": costs_out,
        "market_gap": market_gap,
        "stock_recent": stock_recent,
        "seed_date": seed_date.isoformat(),
    }
    _result_cache[target_key] = (now, result)
    return result


async def compute_current_costs(
    client: Any, today: date
) -> dict[str, dict[str, Any]]:
    """回傳每檔目前融資成本 `{code: {value, as_of, roll_days, source}}`。"""
    return (await _roll_all(client, today))["costs"]


async def compute_market_gap(client: Any, today: date) -> list[dict[str, Any]]:
    """回傳種子日之後每個交易日的大盤金額加權維持率序列（補在 bundle 之後）。"""
    return (await _roll_all(client, today))["market_gap"]


async def compute_stock_recent(
    client: Any, today: date
) -> dict[str, list[tuple[str, float]]]:
    """回傳每檔種子日之後近 7 個交易日維持率 `{code: [(date_iso, ratio)]}`。"""
    return (await _roll_all(client, today))["stock_recent"]
