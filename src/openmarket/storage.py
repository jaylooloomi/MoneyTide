"""Small JSON-file stores under data/: generic cache, settings and watchlist."""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .config import POLL_SECONDS_DEFAULT, POLL_SECONDS_MAX, POLL_SECONDS_MIN

CODE_RE = re.compile(r"^[0-9A-Z]{4,6}$")


def _write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return None


class JsonCache:
    """Persists a JSON-serialisable payload together with the time it was saved."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> tuple[Any, datetime] | None:
        raw = _read_json(self.path)
        if not isinstance(raw, dict) or "saved_at" not in raw or "data" not in raw:
            return None
        try:
            saved_at = datetime.fromisoformat(raw["saved_at"])
        except (TypeError, ValueError):
            return None
        return raw["data"], saved_at

    def save(self, data: Any, now: datetime) -> None:
        _write_json_atomic(self.path, {"saved_at": now.isoformat(), "data": data})

    def is_fresh(self, now: datetime, max_age_days: int) -> bool:
        loaded = self.load()
        return loaded is not None and now - loaded[1] < timedelta(days=max_age_days)


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def get(self) -> dict:
        raw = _read_json(self.path)
        poll = raw.get("poll_seconds") if isinstance(raw, dict) else None
        if not isinstance(poll, int) or not POLL_SECONDS_MIN <= poll <= POLL_SECONDS_MAX:
            poll = POLL_SECONDS_DEFAULT
        return {"poll_seconds": poll}

    @property
    def poll_seconds(self) -> int:
        return self.get()["poll_seconds"]

    def set_poll_seconds(self, seconds: int) -> dict:
        if not isinstance(seconds, int) or not POLL_SECONDS_MIN <= seconds <= POLL_SECONDS_MAX:
            raise ValueError(f"poll_seconds must be an integer in {POLL_SECONDS_MIN}..{POLL_SECONDS_MAX}")
        with self._lock:
            _write_json_atomic(self.path, {"poll_seconds": seconds})
        return self.get()


class Watchlist:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def codes(self) -> list[str]:
        raw = _read_json(self.path)
        codes = raw.get("codes") if isinstance(raw, dict) else None
        if not isinstance(codes, list):
            return []
        return [c for c in codes if isinstance(c, str) and CODE_RE.match(c)]

    def add(self, code: str) -> list[str]:
        if not CODE_RE.match(code):
            raise ValueError(f"invalid stock code: {code!r}")
        with self._lock:
            codes = self.codes()
            if code not in codes:
                codes.append(code)
                _write_json_atomic(self.path, {"codes": codes})
            return codes

    def remove(self, code: str) -> list[str]:
        with self._lock:
            codes = [c for c in self.codes() if c != code]
            _write_json_atomic(self.path, {"codes": codes})
            return codes
