"""SQLite store for daily closing quotes (data/history.sqlite)."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

COLUMNS = [
    "code", "name", "market", "industry", "kind", "close", "prev_close", "change", "change_pct",
    "open", "high", "low", "volume_shares", "turnover_yuan", "market_cap",
]

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS daily_quote (
    date TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT, market TEXT, industry TEXT, kind TEXT,
    close REAL, prev_close REAL, change REAL, change_pct REAL,
    open REAL, high REAL, low REAL, volume_shares REAL, turnover_yuan REAL, market_cap REAL,
    PRIMARY KEY (date, code)
);
CREATE INDEX IF NOT EXISTS daily_quote_code ON daily_quote (code, date);
CREATE TABLE IF NOT EXISTS trading_day (
    date TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('ok', 'no_data')),
    fetched_at TEXT NOT NULL,
    rows INTEGER NOT NULL DEFAULT 0
);
"""


class HistoryStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---- writes ------------------------------------------------------------

    def save_day(self, day: date, rows: list[dict], fetched_at: datetime) -> None:
        placeholders = ", ".join("?" for _ in range(len(COLUMNS) + 1))
        with self._lock, self._conn() as c:
            c.execute("DELETE FROM daily_quote WHERE date = ?", (day.isoformat(),))
            c.executemany(
                f"INSERT INTO daily_quote (date, {', '.join(COLUMNS)}) VALUES ({placeholders})",
                [(day.isoformat(), *(r.get(k) for k in COLUMNS)) for r in rows],
            )
            c.execute(
                "INSERT OR REPLACE INTO trading_day (date, status, fetched_at, rows) VALUES (?, 'ok', ?, ?)",
                (day.isoformat(), fetched_at.isoformat(), len(rows)),
            )

    def mark_no_data(self, day: date, fetched_at: datetime) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO trading_day (date, status, fetched_at, rows) VALUES (?, 'no_data', ?, 0)",
                (day.isoformat(), fetched_at.isoformat()),
            )

    # ---- reads -------------------------------------------------------------

    def days(self) -> dict[date, str]:
        with self._conn() as c:
            return {date.fromisoformat(r["date"]): r["status"] for r in c.execute("SELECT date, status FROM trading_day")}

    def trading_dates(self, up_to: date | None = None, limit: int | None = None) -> list[date]:
        """Dates with data, newest first."""
        sql = "SELECT date FROM trading_day WHERE status = 'ok'"
        args: list = []
        if up_to is not None:
            sql += " AND date <= ?"
            args.append(up_to.isoformat())
        sql += " ORDER BY date DESC"
        if limit is not None:
            sql += " LIMIT ?"
            args.append(limit)
        with self._conn() as c:
            return [date.fromisoformat(r["date"]) for r in c.execute(sql, args)]

    def rows(self, days: list[date]) -> dict[date, list[dict]]:
        if not days:
            return {}
        out: dict[date, list[dict]] = {d: [] for d in days}
        marks = ", ".join("?" for _ in days)
        with self._conn() as c:
            for r in c.execute(
                f"SELECT * FROM daily_quote WHERE date IN ({marks}) ORDER BY date, code",
                [d.isoformat() for d in days],
            ):
                out[date.fromisoformat(r["date"])].append(dict(r))
        return out

    def day_rows(self, day: date) -> list[dict]:
        return self.rows([day])[day]

    def stock_rows(self, code: str, up_to: date, limit: int) -> list[dict]:
        """One stock's last `limit` stored days up to `up_to`, oldest first."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM daily_quote WHERE code = ? AND date <= ? ORDER BY date DESC LIMIT ?",
                (code, up_to.isoformat(), limit),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def change_rows(self, days: list[date]) -> dict[date, list[dict]]:
        """Lean variant of rows(): only the fields needed for group return calculations."""
        if not days:
            return {}
        out: dict[date, list[dict]] = {d: [] for d in days}
        marks = ", ".join("?" for _ in days)
        with self._conn() as c:
            for d, code, kind, industry, pct in c.execute(
                f"SELECT date, code, kind, industry, change_pct FROM daily_quote WHERE date IN ({marks})",
                [d.isoformat() for d in days],
            ):
                out[date.fromisoformat(d)].append({"code": code, "kind": kind, "industry": industry, "change_pct": pct})
        return out
