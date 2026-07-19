"""FN-021（選配）：產業別（全市場 tse/otc）維持率合計服務。

依 docs/architecture.md §8 修正第 5 點，本服務為選配、不得阻塞 MVP。
目前提供與 `IndustryResponse` 相容的介面，但實作為**未啟用 stub**
（`status="not_enabled"`），不對外發出任何請求。

未來啟用時的完整實作方向（供接手者參考，尚未實作）：
    - 缺現成成分股清單時，以融資餘額清單（`fetch_margin` 對應端點的全表）
      作為成分股來源，排除代號 91 開頭（權證/牛熊證）。
    - 逐檔並行取得現價/N 日均價/融資餘額，套用
      `Σ(收盤×資餘) / Σ(均價×資餘×MARGIN_RATE) × 100` 計算產業合計維持率。
    - 使用 `asyncio.Semaphore(8)` 節流逐檔查詢，避免對外部端點造成過大壓力。
    - 任一檔缺資料則排除該檔並累計 `excluded`，於 `note` 標示成分股數量大時
      的耗時提示。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.config import TZ

__all__ = ["compute_industry_maintenance"]


async def compute_industry_maintenance(
    market: str,
    n: int,
    client: httpx.AsyncClient,
    codes: list[str] | None = None,
) -> dict[str, Any]:
    """產業別（全市場）維持率合計，回傳與 `IndustryResponse` 相容的 dict。

    參數：
        market: "tse" 或 "otc"。
        n: N 日均價天數。
        client: 共用 httpx.AsyncClient（stub 階段未發出任何請求，保留介面
            供未來啟用完整實作時使用）。
        codes: 指定成分股代號清單（選配；未提供時，未來完整實作將以融資
            餘額清單為成分股來源）。

    回傳：
        目前恆為 stub 回應：`ratio=None`、`constituents=0`、`excluded=0`、
        `status="not_enabled"`，並於 `note` 說明本功能尚未啟用。
    """
    _ = client, codes  # 保留介面參數，stub 階段未使用

    tz = ZoneInfo(TZ)
    now = datetime.now(tz)

    return {
        "market": market,
        "ratio": None,
        "constituents": 0,
        "excluded": 0,
        "note": "產業別維持率合計為選配功能，尚未啟用（見 FN-021 docstring 之完整實作方向）",
        "n_requested": n,
        "status": "not_enabled",
        "generated_at": now.isoformat(),
    }
