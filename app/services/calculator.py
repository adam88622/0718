"""FN-018/FN-019：維持率計算公式與警戒分類（純函式，無 I/O）。"""

from __future__ import annotations

from app.config import MARGIN_RATE, WARN_DANGER, WARN_SAFE

__all__ = [
    "compute_maintenance_ratio",
    "classify_warning",
    "trim_recent_continuous",
]

# 台股單日漲跌幅上限為 ±10%，故相鄰交易日收盤價不可能差超過約 10%。
# 序列中若出現遠大於此的跳空（預設 >35%），必為公司行為（分割/反分割/
# 除權除息/面額變更）造成的「未還原價」斷點，而非真實價格變動。將此跳空
# 之前的舊價視為不同計價基礎，計算 N 日均價時應排除，只取事件後的連續段。
_SPLIT_STEP_THRESHOLD = 0.35


def trim_recent_continuous(
    closes: list[float], max_step: float = _SPLIT_STEP_THRESHOLD
) -> tuple[list[float], bool]:
    """回傳「最近一段連續、無公司行為斷點」的收盤序列。

    參數 `closes` 為由舊到新排列的收盤價。自最新一筆往回掃，遇到相鄰兩日
    變動幅度超過 `max_step`（預設 35%）即視為除權/分割斷點，截斷不再往回取。

    回傳 `(trimmed, was_trimmed)`：`trimmed` 仍為由舊到新；`was_trimmed`
    表示是否偵測到斷點而截斷（供上層標註「均價已排除除權前資料」）。
    """
    if len(closes) <= 1:
        return closes, False

    kept = [closes[-1]]
    trimmed = False
    for i in range(len(closes) - 2, -1, -1):
        newer = kept[-1]
        older = closes[i]
        if older <= 0 or newer <= 0:
            trimmed = True
            break
        if abs(newer - older) / older > max_step:
            trimmed = True
            break
        kept.append(older)

    kept.reverse()
    return kept, trimmed


def compute_maintenance_ratio(
    price: float | None, n_avg: float | None, rate: float = MARGIN_RATE
) -> float | None:
    """純函式：維持率 = `price / (n_avg * rate) * 100`（四捨五入 2 位）。

    `price` 為 `None`，或 `n_avg` 為 `None`/小於等於 0 時回傳 `None`
    （不執行除法，避免 `Inf`/`NaN`）。
    """
    if price is None or n_avg is None or n_avg <= 0:
        return None
    return round(price / (n_avg * rate) * 100, 2)


def classify_warning(ratio: float | None) -> str:
    """依維持率分類警戒等級，門檻依台股融資成數 0.6 推導
    （初始維持率基準 = 1/0.6 ≈ 166.67%，見 docs/architecture.md §8 修正第 7 點）。

    - `ratio is None` -> "na"
    - `ratio < WARN_DANGER(130)` -> "danger"（達整戶追繳線）
    - `ratio >= WARN_SAFE(166.67)` -> "safe"（回本基準）
    - 其餘（130 <= ratio < 166.67） -> "warn"（虧損中尚未追繳）
    """
    if ratio is None:
        return "na"
    if ratio < WARN_DANGER:
        return "danger"
    if ratio >= WARN_SAFE:
        return "safe"
    return "warn"
