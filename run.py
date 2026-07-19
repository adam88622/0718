"""FN-033：開發環境進入點，`python run.py` 或 `uv run run.py` 啟動。

以字串 "app.main:app" 傳給 uvicorn，允許未來如需開啟 reload 時可正常運作
（開發環境非 frozen，字串 import 沒有問題）。
"""

from __future__ import annotations

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
