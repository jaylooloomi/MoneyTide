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
CREATE TABLE IF NOT EXISTS index_daily (
    date TEXT NOT NULL,
    market TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, change REAL, turnover_yuan REAL,
    PRIMARY KEY (date, market)
);
CREATE TABLE IF NOT EXISTS inst_daily (
    date TEXT NOT NULL,
    code TEXT NOT NULL,
    foreign_net REAL, trust_net REAL, dealer_net REAL, total_net REAL,
    PRIMARY KEY (date, code)
);
CREATE TABLE IF NOT EXISTS inst_day (
    date TEXT PRIMARY KEY,
    rows INTEGER NOT NULL DEFAULT 0,
    fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ptt_day (
    date TEXT PRIMARY KEY,
    titles TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS news_day (
    date TEXT PRIMARY KEY,
    themes TEXT NOT NULL,
    headlines INTEGER NOT NULL DEFAULT 0,
    fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS news_ai (
    date TEXT PRIMARY KEY,
    themes TEXT NOT NULL,
    model TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ai_reason (
    date TEXT NOT NULL,
    code TEXT NOT NULL,
    reason TEXT NOT NULL,
    links TEXT NOT NULL,
    model TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (date, code)
);
CREATE TABLE IF NOT EXISTS index_month (
    market TEXT NOT NULL,
    month TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    rows INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (market, month)
);
"""


class HistoryStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        # results derived from immutable past days (e.g. per-day group averages); cleared on writes
        self.derived_cache: dict = {}
        self._news_version = 0  # bumped on news writes; part of the hot-themes cache key
        self._inst_version = 0  # bumped on institutional writes; part of the money-flow cache key
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
        self.derived_cache.clear()  # after commit, so no reader can re-cache pre-write rows

    def mark_no_data(self, day: date, fetched_at: datetime) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO trading_day (date, status, fetched_at, rows) VALUES (?, 'no_data', ?, 0)",
                (day.isoformat(), fetched_at.isoformat()),
            )
        self.derived_cache.clear()

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

    def daily_breadth(self) -> list[dict]:
        """bonus-14: per trading day, advancers/decliners and the equal-weight average change of
        common stocks — one aggregate query for the breadth calendar."""
        with self._conn() as c:
            rows = c.execute(
                """SELECT q.date,
                          SUM(CASE WHEN q.change > 0 THEN 1 ELSE 0 END),
                          SUM(CASE WHEN q.change < 0 THEN 1 ELSE 0 END),
                          COUNT(*),
                          AVG(q.change_pct)
                   FROM daily_quote q JOIN trading_day t ON t.date = q.date AND t.status = 'ok'
                   WHERE q.kind = 'stock'
                   GROUP BY q.date ORDER BY q.date"""
            ).fetchall()
        return [
            {"date": d, "up": up, "down": down, "count": n, "avg_pct": round(avg, 4) if avg is not None else None}
            for d, up, down, n, avg in rows
        ]

    def group_turnover_avg(self, days: int = 20) -> dict:
        """bonus-16: average daily turnover (元) per (industry, market) over the latest `days` stored
        trading days, common stocks only. {"as_of": date, "days": n, "avg": {industry: {market: 元}}}"""
        dates = self.trading_dates(limit=days)
        if not dates:
            return {"as_of": None, "days": 0, "avg": {}}
        key = ("turnover_avg", dates[0], days)
        if key in self.derived_cache:
            return self.derived_cache[key]
        marks = ", ".join("?" for _ in dates)
        with self._conn() as c:
            rows = c.execute(
                f"""SELECT industry, market, SUM(turnover_yuan) FROM daily_quote
                    WHERE kind = 'stock' AND date IN ({marks}) GROUP BY industry, market""",
                [d.isoformat() for d in dates],
            ).fetchall()
        avg: dict[str, dict[str, float]] = {}
        for industry, market, total in rows:
            avg.setdefault(industry, {})[market] = (total or 0) / len(dates)
        result = {"as_of": dates[0].isoformat(), "days": len(dates), "avg": avg}
        self.derived_cache[key] = result
        return result


    # ---- market index history (TAIEX / TPEx, see sources/official_index.py) ----------------

    def save_index_month(self, market: str, month: str, rows: list, fetched_at: datetime) -> None:
        """Replace one market's rows for `month` ('YYYY-MM') with `rows` (IndexRow-like objects)."""
        with self._lock, self._conn() as c:
            c.execute("DELETE FROM index_daily WHERE market = ? AND substr(date, 1, 7) = ?", (market, month))
            c.executemany(
                """INSERT INTO index_daily (date, market, open, high, low, close, change, turnover_yuan)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [(r.date.isoformat(), market, r.open, r.high, r.low, r.close, r.change, r.turnover_yuan) for r in rows],
            )
            c.execute(
                "INSERT OR REPLACE INTO index_month (market, month, fetched_at, rows) VALUES (?, ?, ?, ?)",
                (market, month, fetched_at.isoformat(), len(rows)),
            )

    def index_months(self) -> dict[tuple[str, str], datetime]:
        """{(market, 'YYYY-MM'): fetched_at}"""
        with self._conn() as c:
            return {
                (r["market"], r["month"]): datetime.fromisoformat(r["fetched_at"])
                for r in c.execute("SELECT market, month, fetched_at FROM index_month")
            }

    def index_rows(self) -> dict[str, dict[str, dict]]:
        """{date: {market: {open, high, low, close, change, turnover_yuan}}}"""
        out: dict[str, dict[str, dict]] = {}
        with self._conn() as c:
            for r in c.execute("SELECT * FROM index_daily ORDER BY date"):
                row = dict(r)
                d, m = row.pop("date"), row.pop("market")
                out.setdefault(d, {})[m] = row
        return out

    def daily_strength(self, strong_pct: float, limit_pct: float) -> dict[str, dict]:
        """Per stored trading day, over common stocks: share (%) with change >= strong_pct and
        the count with change >= limit_pct. Cached until the next save_day."""
        key = ("daily_strength", strong_pct, limit_pct)
        cached = self.derived_cache.get(key)
        if cached is not None:
            return cached
        with self._conn() as c:
            rows = c.execute(
                """SELECT q.date,
                          AVG(CASE WHEN q.change_pct >= ? THEN 1.0 ELSE 0.0 END) * 100,
                          SUM(CASE WHEN q.change_pct >= ? THEN 1 ELSE 0 END)
                   FROM daily_quote q JOIN trading_day t ON t.date = q.date AND t.status = 'ok'
                   WHERE q.kind = 'stock' AND q.change_pct IS NOT NULL
                   GROUP BY q.date""",
                (strong_pct, limit_pct),
            ).fetchall()
        result = {d: {"strong_ratio": round(ratio, 2), "limit_up": int(n)} for d, ratio, n in rows}
        self.derived_cache[key] = result
        return result


    # ---- ⑤ AI news explanations (one answer per date and code) ------------------------------

    def ai_reasons(self, day: date) -> dict[str, dict]:
        """{code: {reason, links, model, created_at}} for `day`."""
        import json

        with self._conn() as c:
            return {
                r["code"]: {"reason": r["reason"], "links": json.loads(r["links"]), "model": r["model"], "created_at": r["created_at"]}
                for r in c.execute("SELECT * FROM ai_reason WHERE date = ?", (day.isoformat(),))
            }

    def save_ai_reason(self, day: date, code: str, reason: str, links: list[dict], model: str | None) -> None:
        import json

        with self._lock, self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO ai_reason (date, code, reason, links, model, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (day.isoformat(), code, reason, json.dumps(links, ensure_ascii=False), model, datetime.now().astimezone().isoformat()),
            )


    # ---- news-driven hot groups (one keyword result per day, optional AI clean-up) ---------------

    def save_news_day(self, day: date, themes: dict, headlines: int) -> None:
        import json

        with self._lock, self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO news_day (date, themes, headlines, fetched_at) VALUES (?, ?, ?, ?)",
                (day.isoformat(), json.dumps(themes, ensure_ascii=False), headlines, datetime.now().astimezone().isoformat()),
            )
        self._news_version += 1

    def news_dates(self) -> set[date]:
        with self._conn() as c:
            return {date.fromisoformat(r["date"]) for r in c.execute("SELECT date FROM news_day")}

    def news_dates_sorted(self, up_to: date | None = None, limit: int | None = None) -> list[date]:
        """Stored news days, newest first."""
        sql, args = "SELECT date FROM news_day", []
        if up_to is not None:
            sql += " WHERE date <= ?"
            args.append(up_to.isoformat())
        sql += " ORDER BY date DESC"
        if limit is not None:
            sql += " LIMIT ?"
            args.append(limit)
        with self._conn() as c:
            return [date.fromisoformat(r["date"]) for r in c.execute(sql, args)]

    def news_day(self, day: date) -> dict:
        import json

        with self._conn() as c:
            row = c.execute("SELECT themes FROM news_day WHERE date = ?", (day.isoformat(),)).fetchone()
        return json.loads(row["themes"]) if row else {}

    def save_news_ai(self, day: date, themes: list[dict], model: str | None) -> None:
        import json

        with self._lock, self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO news_ai (date, themes, model, created_at) VALUES (?, ?, ?, ?)",
                (day.isoformat(), json.dumps(themes, ensure_ascii=False), model, datetime.now().astimezone().isoformat()),
            )
        self._news_version += 1

    def news_ai(self, day: date) -> list[dict] | None:
        import json

        with self._conn() as c:
            row = c.execute("SELECT themes FROM news_ai WHERE date = ?", (day.isoformat(),)).fetchone()
        return json.loads(row["themes"]) if row else None

    def news_version(self) -> int:
        return self._news_version


    # ---- 三大法人 net buy/sell (shares) ------------------------------------------------------

    def save_inst_day(self, day: date, rows: list | None, fetched_at: datetime) -> None:
        """rows: InstRow-like objects, or None/[] for a day without data (recorded so it is not refetched)."""
        with self._lock, self._conn() as c:
            c.execute("DELETE FROM inst_daily WHERE date = ?", (day.isoformat(),))
            c.executemany(
                "INSERT INTO inst_daily (date, code, foreign_net, trust_net, dealer_net, total_net) VALUES (?, ?, ?, ?, ?, ?)",
                [(day.isoformat(), r.code, r.foreign, r.trust, r.dealer, r.total) for r in rows or []],
            )
            c.execute(
                "INSERT OR REPLACE INTO inst_day (date, rows, fetched_at) VALUES (?, ?, ?)",
                (day.isoformat(), len(rows or []), fetched_at.isoformat()),
            )
        self._inst_version += 1

    def inst_dates(self) -> set[date]:
        with self._conn() as c:
            return {date.fromisoformat(r["date"]) for r in c.execute("SELECT date FROM inst_day")}

    def inst_net(self, days: list[date]) -> dict[date, dict[str, float]]:
        """{day: {code: 三大法人 net shares}}"""
        if not days:
            return {}
        out: dict[date, dict[str, float]] = {d: {} for d in days}
        marks = ", ".join("?" for _ in days)
        with self._conn() as c:
            for d, code, net in c.execute(
                f"SELECT date, code, total_net FROM inst_daily WHERE date IN ({marks})", [d.isoformat() for d in days]
            ):
                out[date.fromisoformat(d)][code] = net or 0.0
        return out

    def inst_version(self) -> int:
        return self._inst_version


    # ---- PTT 股版 titles per day (heat bursts) ------------------------------------------------

    def save_ptt_days(self, by_day: dict[date, list[str]]) -> None:
        import json

        now = datetime.now().astimezone().isoformat()
        with self._lock, self._conn() as c:
            c.executemany(
                "INSERT OR REPLACE INTO ptt_day (date, titles, fetched_at) VALUES (?, ?, ?)",
                [(d.isoformat(), json.dumps(t, ensure_ascii=False), now) for d, t in by_day.items()],
            )
        self._news_version += 1

    def ptt_dates_sorted(self, up_to: date | None = None, limit: int | None = None) -> list[date]:
        sql, args = "SELECT date FROM ptt_day", []
        if up_to is not None:
            sql += " WHERE date <= ?"
            args.append(up_to.isoformat())
        sql += " ORDER BY date DESC"
        if limit is not None:
            sql += " LIMIT ?"
            args.append(limit)
        with self._conn() as c:
            return [date.fromisoformat(r["date"]) for r in c.execute(sql, args)]

    def ptt_titles(self, day: date) -> list[str]:
        import json

        with self._conn() as c:
            row = c.execute("SELECT titles FROM ptt_day WHERE date = ?", (day.isoformat(),)).fetchone()
        return json.loads(row["titles"]) if row else []
