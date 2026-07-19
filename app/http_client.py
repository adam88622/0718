"""FN-002: 共用 httpx.AsyncClient 生命週期管理。

L2 adapter 層的唯一對外 httpx 出口皆透過 `get_client()` 取得同一個單例，
避免每次請求重新建立連線。生命週期由 FastAPI lifespan（app/main.py）掌控。
"""

from __future__ import annotations

import httpx

from app.config import DEFAULT_HEADERS, HTTP_TIMEOUT

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    """取得共用的 httpx.AsyncClient 單例，不存在則建立。"""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=DEFAULT_HEADERS)
    return _client


async def close_client() -> None:
    """關閉共用 httpx.AsyncClient 並清空單例，供 lifespan shutdown 呼叫。"""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
