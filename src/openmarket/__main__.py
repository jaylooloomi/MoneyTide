from __future__ import annotations

import argparse
import logging
import threading
import webbrowser

import uvicorn

from .api import create_app
from .config import AppConfig


def main() -> None:
    parser = argparse.ArgumentParser(prog="openmarket", description="台股產業熱力圖（本機）")
    parser.add_argument("--no-browser", action="store_true", help="啟動後不要自動開瀏覽器")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = AppConfig.from_env()
    url = f"http://{config.host}:{config.port}"
    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    print(f"Open Market → {url}")
    uvicorn.run(create_app(config), host=config.host, port=config.port, log_level="info")


if __name__ == "__main__":
    main()
