"""FN-010 全市場融資維持率警示掃描主編排服務。

流程：clamp N -> 取得融資 universe（上市+上櫃）-> 回推 N 個交易日組出
全市場收盤矩陣 -> 逐代號計算維持率與分色 -> 依維持率升序排列 -> 組成
警示清單 dict。整份結果以模組級快取（TTL=`ALERT_CACHE_TTL` 秒，key=n），
避免每次請求都重算全市場批次資料。

全程容錯：個別市場/代號失敗只影響該市場/該代號（計入 `excluded`），
不影響整體回應成功。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.adapters.bulk import build_close_matrix, fetch_margin_universe
from app.config import ALERT_BANDS, ALERT_CACHE_TTL, N_MAX, N_MIN, TZ
from app.services.calculator import (
    compute_maintenance_ratio,
    trim_recent_continuous,
)
from app.services.margin_cost import compute_current_costs

__all__ = ["build_alert_list"]

# 模組級快取：key=n，value=(cached_at, result)。
_cache: dict[int, tuple[datetime, dict[str, Any]]] = {}


def _clamp_n(n: int) -> int:
    """將使用者請求的 N 限制在 `[N_MIN, N_MAX]` 範圍內。"""
    return max(N_MIN, min(N_MAX, n))


def _classify_band(ratio: float | None) -> str:
    """依 `ALERT_BANDS` 門檻（130/150/166.67）分色。

    - `ratio is None` -> "na"
    - `ratio < danger(130)` -> "danger"（紅）
    - `danger <= ratio < mid(150)` -> "warn1"（橘）
    - `mid <= ratio < safe(166.67)` -> "warn2"（黃）
    - `ratio >= safe` -> "safe"（綠）
    """
    if ratio is None:
        return "na"
    if ratio < ALERT_BANDS["danger"]:
        return "danger"
    if ratio < ALERT_BANDS["mid"]:
        return "warn1"
    if ratio < ALERT_BANDS["safe"]:
        return "warn2"
    return "safe"


def _bands_description() -> dict[str, str]:
    """組出分色門檻的人類可讀說明，供前端顯示圖例。"""
    danger = ALERT_BANDS["danger"]
    mid = ALERT_BANDS["mid"]
    safe = ALERT_BANDS["safe"]
    return {
        "danger": f"< {danger}",
        "warn1": f"{danger} ~ {mid}",
        "warn2": f"{mid} ~ {safe}",
        "safe": f">= {safe}",
    }


async def build_alert_list(
    n: int, client: httpx.AsyncClient, today: date
) -> dict[str, Any]:
    """組出全市場融資維持率警示清單，回傳與 `/api/alerts` 回應相容的 dict。

    參數：
        n: 使用者指定的 N 日均價天數，會被 clamp 到 `[N_MIN, N_MAX]`。
        client: 共用 httpx.AsyncClient。
        today: 查詢基準日（台北時區的今日）。

    快取：整份結果以模組級 dict 快取（key=n），存活 `ALERT_CACHE_TTL` 秒；
    過期或未快取則重新計算全市場批次資料。
    """
    n = _clamp_n(n)
    tz = ZoneInfo(TZ)
    now = datetime.now(tz)

    cached = _cache.get(n)
    if cached is not None:
        cached_at, cached_result = cached
        if (now - cached_at).total_seconds() < ALERT_CACHE_TTL:
            return cached_result

    universe = await fetch_margin_universe(client, today)
    names: dict[str, str] = universe.get("names", {}) or {}
    codes_by_market = {
        "tse": list(universe.get("tse", {}).keys()),
        "otc": list(universe.get("otc", {}).keys()),
    }
    matrix = await build_close_matrix(codes_by_market, n, client, today)
    # 加權融資成本（種子 2026-07-17 + 每日滾動）；無種子的標的退回 N 日均價。
    weighted = await compute_current_costs(client, today)

    items: list[dict[str, Any]] = []
    excluded = 0

    for market in ("tse", "otc"):
        margin_map: dict[str, int] = universe.get(market, {}) or {}
        close_map: dict[str, list[float]] = matrix.get(market, {}) or {}

        for code, lots in margin_map.items():
            closes = close_map.get(code) or []
            if not closes:
                excluded += 1
                continue

            # 先排除近期除權/分割造成的未還原價斷點，只取事件後連續段。
            continuous, adjusted = trim_recent_continuous(closes)
            recent = continuous[-n:] if n > 0 else continuous
            if not recent:
                excluded += 1
                continue

            latest_price = recent[-1]
            n_day_avg = round(sum(recent) / len(recent), 2)

            # 融資成本基礎：優先用加權滾動成本（券商級），否則退回 N 日均價
            wc = weighted.get(code)
            if wc is not None and wc.get("value"):
                cost_basis = wc["value"]
                cost_source = "加權融資成本"
            else:
                cost_basis = n_day_avg
                cost_source = "N日均價"

            ratio = compute_maintenance_ratio(latest_price, cost_basis)
            if ratio is None:
                excluded += 1
                continue

            items.append(
                {
                    "code": code,
                    "name": names.get(code),
                    "market": market,
                    "price": latest_price,
                    "cost": round(cost_basis, 2),
                    "cost_source": cost_source,
                    "n_day_avg": n_day_avg,
                    "avg_days": len(recent),
                    "margin_lots": lots,
                    "ratio": ratio,
                    "band": _classify_band(ratio),
                    "adjusted": adjusted,
                }
            )

    items.sort(key=lambda item: item["ratio"])

    result: dict[str, Any] = {
        "n_requested": n,
        "price_as_of": matrix.get("price_as_of"),
        "margin_as_of_tse": universe.get("as_of_tse"),
        "margin_as_of_otc": universe.get("as_of_otc"),
        "count": len(items),
        "excluded": excluded,
        "bands": _bands_description(),
        "items": items,
        "generated_at": now.isoformat(),
    }

    _cache[n] = (now, result)
    return result
