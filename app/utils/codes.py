"""FN-007：股票代號驗證。"""

from __future__ import annotations

import re

__all__ = ["CodeError", "validate_stock_code"]

_CODE_PATTERN = re.compile(r"^\d{4}$")
_WARRANT_PREFIX = "91"


class CodeError(ValueError):
    """代號格式或種類不支援時拋出，帶原始 `code` 與人類可讀 `reason`。"""

    def __init__(self, reason: str, code: str) -> None:
        self.reason = reason
        self.code = code
        super().__init__(reason)


def validate_stock_code(code: str) -> str:
    """驗證並正規化股票代號。

    - 去除前後空白，須符合 `^\\d{4}$`（4 碼數字），否則 raise `CodeError`。
    - 91 開頭（權證/牛熊證）不支援，raise `CodeError`。
    - 通過驗證則回傳正規化後（去空白）的代號字串。
    """
    normalized = code.strip()
    if not _CODE_PATTERN.match(normalized):
        raise CodeError("代號需為 4 碼數字", code)
    if normalized.startswith(_WARRANT_PREFIX):
        raise CodeError("不支援 91 開頭（權證/牛熊證）", code)
    return normalized
