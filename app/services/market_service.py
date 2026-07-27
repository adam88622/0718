"""F-012 大盤融資維持率指標：金額加權市場維持率 + MA20/60 + 位階燈號。

序列 = 打包歷史（`app/data/market_ratio_history.json`，至 2026-07-17）
      + 種子日之後由 margin_cost 滾動補齊的缺口（compute_market_gap）。

位階判斷（融資清洗逆勢框架）：
- 極端 washout 🟢：處近期低位（percentile≤10%）且低於 MA60 → 價值浮現區
- 清洗中：跌破 MA20 且 5 日下彎
- 過熱：處近期高位（percentile≥85%）且高於 MA60
- 正常：其餘
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.config import TZ, resolve_base_dir
from app.services.margin_cost import compute_market_gap

__all__ = ["get_market_indicator"]

_HISTORY_PARTS = ("app", "data", "market_ratio_history.json")
_PCT_WINDOW = 120  # 位階百分位取樣窗（交易日）
_SPARK_POINTS = 120  # 回傳給前端畫圖的點數


def _load_history() -> list[dict[str, Any]]:
    """載入打包的大盤維持率歷史序列（list of {date, ratio, n}）。"""
    path = resolve_base_dir().joinpath(*_HISTORY_PARTS)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return list(raw.get("series", []))
    except Exception:  # noqa: BLE001 - 缺檔則回空，上層降級
        return []


def _moving_avg(values: list[float], window: int) -> float | None:
    """尾端 window 筆算術平均；不足則回 None。"""
    if len(values) < window:
        return None
    return round(sum(values[-window:]) / window, 2)


def _classify_level(
    current: float, ma20: float | None, ma60: float | None,
    percentile: float, vel5: float | None,
) -> str:
    """位階分類，回傳 key：extreme_washout / washing / overheated / normal。"""
    below_ma60 = ma60 is not None and current < ma60
    falling = vel5 is not None and vel5 < 0
    if percentile <= 0.10 and below_ma60:
        return "extreme_washout"
    if percentile >= 0.85 and ma60 is not None and current > ma60:
        return "overheated"
    if ma20 is not None and current < ma20 and falling:
        return "washing"
    return "normal"


_LEVEL_ZH = {
    "extreme_washout": "極端清洗（價值浮現）",
    "washing": "清洗中",
    "overheated": "過熱",
    "normal": "正常",
}


async def get_market_indicator(client: Any, today: date) -> dict[str, Any]:
    """組出大盤融資維持率指標（含 MA20/60、位階、清洗速度、走勢序列）。"""
    tz = ZoneInfo(TZ)
    now = datetime.now(tz)

    history = _load_history()
    # 接續種子日之後的缺口（去重：只取比 bundle 最後日期更新的）
    try:
        gap = await compute_market_gap(client, today)
    except Exception:  # noqa: BLE001 - 缺口失敗僅用 bundle
        gap = []
    last_hist_date = history[-1]["date"] if history else ""
    merged = list(history) + [g for g in gap if g["date"] > last_hist_date]

    if not merged:
        return {
            "status": "no_data",
            "current": None,
            "generated_at": now.isoformat(),
        }

    values = [float(p["ratio"]) for p in merged]
    current = values[-1]
    ma20 = _moving_avg(values, 20)
    ma60 = _moving_avg(values, 60)

    window = values[-_PCT_WINDOW:] if len(values) >= _PCT_WINDOW else values
    below = sum(1 for v in window if v < current)
    percentile = round(below / len(window), 3) if window else 0.5

    vel5 = round(current - values[-6], 2) if len(values) >= 6 else None

    level = _classify_level(current, ma20, ma60, percentile, vel5)

    # 為 sparkline 每個點算出當日 MA20/MA60（用完整 values，左緣也正確）
    def _ma_at(i: int, window: int) -> float | None:
        if i + 1 < window:
            return None
        seg = values[i + 1 - window : i + 1]
        return round(sum(seg) / window, 2)

    start = max(0, len(merged) - _SPARK_POINTS)
    spark = [
        {
            "date": merged[i]["date"],
            "ratio": merged[i]["ratio"],
            "ma20": _ma_at(i, 20),
            "ma60": _ma_at(i, 60),
        }
        for i in range(start, len(merged))
    ]

    return {
        "status": "ok",
        "current": current,
        "as_of": merged[-1]["date"],
        "ma20": ma20,
        "ma60": ma60,
        "percentile": percentile,
        "velocity_5d": vel5,
        "level": level,
        "level_zh": _LEVEL_ZH[level],
        "window_min": round(min(window), 2),
        "window_max": round(max(window), 2),
        "constituents": merged[-1].get("n"),
        "series": [{"date": p["date"], "ratio": p["ratio"]} for p in spark],
        "generated_at": now.isoformat(),
    }
