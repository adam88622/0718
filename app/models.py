"""FN-003: Pydantic v2 schema，定義 API 契約與各欄位降級結構。

每個資料區塊（price/average/margin/ratio）皆獨立帶 `status`/`source`，
單一欄位缺資料不影響整體回應（見 docs/architecture.md §5 降級策略）。
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class FieldStatus(str, Enum):
    """單一資料欄位的取得狀態。"""

    OK = "ok"
    NO_DATA = "no_data"
    UNCOMPUTABLE = "uncomputable"


class PriceBlock(BaseModel):
    """現價區塊（即時或收盤），z="-" 時以中間價/昨收 fallback。"""

    value: float | None
    price_type: str | None
    is_fallback: bool = False
    prev_close: float | None = None
    as_of: str | None = None
    name: str | None = None
    source: str
    status: FieldStatus


class AverageBlock(BaseModel):
    """N 日均價區塊，官方歷史不足時退回 Yahoo 並標註來源。"""

    value: float | None
    count: int = 0
    start: str | None
    end: str | None
    n_requested: int
    insufficient: bool = False
    note: str | None = None
    source: str
    status: FieldStatus


class MarginBlock(BaseModel):
    """融資餘額（張數）區塊。"""

    balance_lots: int | None = None
    as_of: str | None = None
    source: str
    status: FieldStatus


class RatioFormula(BaseModel):
    """維持率計算公式三值，供前端顯示計算依據。"""

    price: float | None
    n_day_avg: float | None
    margin_rate: float
    expression: str | None


class RatioBlock(BaseModel):
    """維持率結果區塊，含警戒分類與公式明細。"""

    value: float | None
    warning: str
    formula: RatioFormula
    status: FieldStatus


class MaintenanceResponse(BaseModel):
    """GET /api/maintenance 成功回應（200）完整契約。"""

    code: str
    name: str | None
    market: str
    session: str
    n_requested: int
    price: PriceBlock
    average: AverageBlock
    margin: MarginBlock
    ratio: RatioBlock
    generated_at: str


class IndustryResponse(BaseModel):
    """GET /api/industry（選配）回應契約。"""

    market: str
    ratio: float | None
    constituents: int
    excluded: int
    note: str | None
    n_requested: int
    status: str
    generated_at: str


class ErrorResponse(BaseModel):
    """統一錯誤回應（422 / 全域例外處理）契約。"""

    error: str
    message: str
    code: str | None = None
