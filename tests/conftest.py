"""共用 pytest fixtures。"""

from __future__ import annotations

import httpx
import pytest


@pytest.fixture
def dummy_client() -> httpx.AsyncClient:
    """未真正發出請求時使用的佔位 AsyncClient（呼叫端邏輯已被 mock，不會真的打網路）。"""
    return httpx.AsyncClient()
