"""FN-010 全市場融資維持率警示掃描主編排服務。

流程：clamp N -> 取得融資 universe（上市+上櫃）-> 回推 N 個交易日組出
全市場收盤矩陣 -> 逐代號計算維持率與分色 -> 依維持率升序排列 -> 組成
警示清單 dict。整份結果以模組級快取（TTL=`ALERT_CACHE_TTL` 秒，key=n），
避免每次請求都重算全市場批次資料。

全程容錯：個別市場/代號失敗只影響該市場/該代號（計入 `excluded`），
不影響整體回應成功。
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.adapters.bulk import build_close_matrix, fetch_margin_universe
from app.config import (
    ALERT_BANDS,
    ALERT_CACHE_TTL,
    N_MAX,
    N_MIN,
    TZ,
    WARN_DANGER,
    resolve_base_dir,
)
from app.services.calculator import (
    compute_maintenance_ratio,
    trim_recent_continuous,
)
from app.services.margin_cost import compute_current_costs, compute_stock_recent

__all__ = ["build_alert_list"]

# 模組級快取：key=n，value=(cached_at, result)。
_cache: dict[int, tuple[datetime, dict[str, Any]]] = {}

# 雙閘門參數（融資清洗框架）
_LOW_T = WARN_DANGER  # 「低維持率」門檻 = 追繳線 130
_CHRONIC_DAYS = 5  # 連續 N 日都低 → 排除（慢性套牢）
_FRESH_FAST_DROP = 8.0  # 近 2 日單日維持率跌幅 ≥ 此值 → 視為「跨得快」

# 個股近期維持率 bundle（種子日前 7 日，from xlsx；載入一次快取）
_recent_bundle: dict[str, Any] | None = None


def _load_recent_bundle() -> dict[str, Any]:
    """載入 app/data/stock_ratio_recent.json（{dates:[...], ratio:{code:[...]}}）。"""
    global _recent_bundle
    if _recent_bundle is not None:
        return _recent_bundle
    path = resolve_base_dir() / "app" / "data" / "stock_ratio_recent.json"
    try:
        _recent_bundle = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        _recent_bundle = {"dates": [], "ratio": {}}
    return _recent_bundle


def _merged_recent(code: str, bundle: dict[str, Any], rolled: dict[str, list]) -> list[float]:
    """合併 bundle（種子日前）與 rolled（種子日後）近期維持率，回傳依日期升序的 ratio list。"""
    dated: dict[str, float] = {}
    b_dates = bundle.get("dates", [])
    b_vals = bundle.get("ratio", {}).get(code)
    if b_vals:
        for d, v in zip(b_dates, b_vals):
            if v is not None:
                dated[d] = float(v)
    for d, v in rolled.get(code, []):
        dated[d] = float(v)
    return [dated[d] for d in sorted(dated)]


def _gate_and_tag(recent: list[float]) -> tuple[bool, bool]:
    """雙閘門判斷。回傳 (exclude_chronic, fresh_washout)。

    - exclude_chronic：最近 `_CHRONIC_DAYS` 日維持率全部 < 門檻 → 慢性套牢，排除。
    - fresh_washout：現值 < 門檻，且前幾日曾 ≥ 門檻（新跨低），且近 2 日單日
      跌幅 ≥ `_FRESH_FAST_DROP`（跨得快）→ 急殺清洗，浮到最上面。
    """
    if not recent:
        return False, False
    current = recent[-1]
    tail = recent[-_CHRONIC_DAYS:]
    if len(tail) >= _CHRONIC_DAYS and all(r < _LOW_T for r in tail):
        return True, False  # 慢性套牢
    if current < _LOW_T:
        prior = recent[-4:-1] if len(recent) >= 2 else []
        newly_below = any(r >= _LOW_T for r in prior)
        fast = len(recent) >= 2 and (recent[-2] - current) >= _FRESH_FAST_DROP
        if newly_below and fast:
            return False, True
    return False, False


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
    # 至少抓 60 個交易日：算股價月線(MA20)/季線(MA60) 需要 60 日。
    ma_days = max(n, 60)
    matrix = await build_close_matrix(codes_by_market, ma_days, client, today)
    # 加權融資成本（種子 2026-07-17 + 每日滾動）；無種子的標的退回 N 日均價。
    weighted = await compute_current_costs(client, today)
    # 雙閘門所需：個股近期維持率（bundle 種子前 + rolled 種子後）
    recent_bundle = _load_recent_bundle()
    rolled_recent = await compute_stock_recent(client, today)

    items: list[dict[str, Any]] = []
    excluded = 0
    chronic_excluded = 0

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

            # 股價月線(MA20)/季線(MA60) 與股價位階（用還原斷點後的連續收盤）
            ma20_price = (
                round(sum(continuous[-20:]) / 20, 2) if len(continuous) >= 20 else None
            )
            ma60_price = (
                round(sum(continuous[-60:]) / 60, 2) if len(continuous) >= 60 else None
            )
            above_ma20 = latest_price > ma20_price if ma20_price else None
            above_ma60 = latest_price > ma60_price if ma60_price else None

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

            # 雙閘門：排除慢性套牢（連續5日低），標記急殺清洗
            recent_ratios = _merged_recent(code, recent_bundle, rolled_recent)
            exclude_chronic, fresh_washout = _gate_and_tag(recent_ratios)
            if exclude_chronic:
                chronic_excluded += 1
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
                    "fresh_washout": fresh_washout,
                    "ma20_price": ma20_price,
                    "ma60_price": ma60_price,
                    "above_ma20": above_ma20,
                    "above_ma60": above_ma60,
                }
            )

    # 急殺清洗浮到最上面（fresh 優先），其餘依維持率升序
    items.sort(key=lambda item: (0 if item.get("fresh_washout") else 1, item["ratio"]))
    fresh_count = sum(1 for i in items if i.get("fresh_washout"))

    result: dict[str, Any] = {
        "n_requested": n,
        "price_as_of": matrix.get("price_as_of"),
        "margin_as_of_tse": universe.get("as_of_tse"),
        "margin_as_of_otc": universe.get("as_of_otc"),
        "count": len(items),
        "excluded": excluded,
        "chronic_excluded": chronic_excluded,
        "fresh_count": fresh_count,
        "low_threshold": _LOW_T,
        "bands": _bands_description(),
        "items": items,
        "generated_at": now.isoformat(),
    }

    _cache[n] = (now, result)
    return result
