"""FN-008：降級結構 helper（集中錯誤降級語意，§5）。

刻意不 import `app.models`，避免 utils 對上層 Pydantic schema 產生耦合；
一律回傳 plain dict，形狀與對應的 PriceBlock/AverageBlock/MarginBlock/
RatioBlock 相容，由呼叫端（services/adapters）組進對應的 Pydantic model。
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Any

__all__ = ["no_data_block", "uncomputable_ratio", "safe_block"]


def no_data_block(source: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """產生「取不到資料」的降級 dict：`{"status":"no_data","source":source, ...extra}`。"""
    block: dict[str, Any] = {"status": "no_data", "source": source}
    if extra:
        block.update(extra)
    return block


def uncomputable_ratio(formula: dict[str, Any]) -> dict[str, Any]:
    """產生「維持率無法計算」的降級 dict（非除以 0/None，避免 Inf/NaN）。"""
    return {
        "value": None,
        "warning": "na",
        "formula": formula,
        "status": "uncomputable",
    }


async def safe_block(
    coro: Awaitable[dict[str, Any]],
    source: str,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """await `coro`；發生例外時回傳 `fallback`（未提供則回 `no_data_block(source)`）。

    用於包住 adapter 呼叫，確保單一欄位失敗不會拋例外中斷整體查詢。
    """
    try:
        return await coro
    except Exception:  # noqa: BLE001 - 統一降級，不外洩上游例外細節
        return fallback if fallback is not None else no_data_block(source)
