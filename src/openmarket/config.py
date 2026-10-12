from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = PROJECT_ROOT / "static"

POLL_SECONDS_DEFAULT = 60
POLL_SECONDS_MIN = 30
POLL_SECONDS_MAX = 600
REFRESH_MIN_INTERVAL_SECONDS = 30
STATIC_CACHE_MAX_AGE_DAYS = 7

HTTP_TIMEOUT_SECONDS = 15.0
HTTP_RETRY_DELAY_SECONDS = 3.0
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)


@dataclass(frozen=True, slots=True)
class AppConfig:
    data_dir: Path
    host: str = "127.0.0.1"
    port: int = 8765

    @classmethod
    def from_env(cls) -> "AppConfig":
        data_dir = Path(os.environ.get("OPENMARKET_DATA_DIR", PROJECT_ROOT / "data"))
        port = int(os.environ.get("OPENMARKET_PORT", "8765"))
        return cls(data_dir=data_dir, port=port)
