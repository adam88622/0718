"""FN-034：PyInstaller exe 進入點 — 背景執行緒起 server + 輪詢就緒 + 開瀏覽器。

依 docs/architecture.md §8 修正第 6 點：
    - 啟動 uvicorn 時傳入 **app 物件**（`from app.main import app`），而非
      `"app.main:app"` 字串，避免 PyInstaller frozen 環境下字串 import 失敗。
    - 不可使用 `reload=True`（frozen 環境不支援亦無意義）。
    - 全程使用標準庫（webbrowser/threading/socket/time/urllib），跨平台相容
      （不可有 macOS 專屬呼叫）。
"""

from __future__ import annotations

import socket
import threading
import time
import urllib.error
import urllib.request
import webbrowser

import uvicorn

from app.main import app

__all__ = ["main"]

_PREFERRED_PORT = 8000
_READY_POLL_INTERVAL = 0.2
_READY_TIMEOUT = 15.0


def _find_free_port(preferred: int = _PREFERRED_PORT) -> int:
    """尋找可用的本機 port：優先嘗試 `preferred`，被佔用則交由系統配置空閒 port。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            pass

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _run_server(port: int) -> None:
    """在目前執行緒中啟動 uvicorn（供背景 thread 呼叫），傳入 app 物件。"""
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def _wait_until_ready(port: int, timeout: float = _READY_TIMEOUT) -> bool:
    """輪詢 `/api/health` 直到就緒或逾時；回傳是否在逾時前就緒。"""
    url = f"http://127.0.0.1:{port}/api/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:  # noqa: S310
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(_READY_POLL_INTERVAL)
    return False


def main() -> None:
    """啟動背景 server thread，輪詢健康檢查就緒後開啟瀏覽器（逾時仍嘗試開啟）。"""
    port = _find_free_port()

    server_thread = threading.Thread(target=_run_server, args=(port,), daemon=True)
    server_thread.start()

    _wait_until_ready(port)

    webbrowser.open(f"http://127.0.0.1:{port}/")

    server_thread.join()


if __name__ == "__main__":
    main()
