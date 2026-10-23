from __future__ import annotations

import argparse
import json
import logging
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

import uvicorn

from .api import create_app
from .config import AppConfig


def _port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex((host, port)) != 0


def _is_openmarket(url: str) -> bool:
    """True when the process on our port is already a MoneyTide server."""
    try:
        with urllib.request.urlopen(f"{url}/api/settings", timeout=2) as resp:
            return resp.status == 200 and "poll_seconds" in json.load(resp)
    except (OSError, ValueError):
        return False


def _open_when_listening(host: str, port: int, url: str, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _port_free(host, port):
            webbrowser.open(url)
            return
        time.sleep(0.2)


def main() -> None:
    # Windows consoles default to cp950, which cannot encode every company name (e.g. 堃).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")

    parser = argparse.ArgumentParser(prog="openmarket", description="台股產業熱力圖（本機）")
    parser.add_argument("--no-browser", action="store_true", help="啟動後不要自動開瀏覽器")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = AppConfig.from_env()
    url = f"http://{config.host}:{config.port}"
    if not _port_free(config.host, config.port):
        if _is_openmarket(url):
            print(f"MoneyTide 錢潮已在執行中 → {url}")
            if not args.no_browser:
                webbrowser.open(url)
            return
        sys.exit(f"連接埠 {config.port} 已被其他程式占用。請關閉該程式，或設定 OPENMARKET_PORT。")
    if not args.no_browser:
        threading.Thread(
            target=_open_when_listening, args=(config.host, config.port, url), daemon=True
        ).start()
    print(f"MoneyTide 錢潮 → {url}")
    uvicorn.run(create_app(config), host=config.host, port=config.port, log_level="info")


if __name__ == "__main__":
    main()
