"""SQLite store for daily closing quotes (data/history.sqlite)."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterable
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
CREATE TABLE IF NOT EXISTS margin_daily (
    date TEXT NOT NULL,
    code TEXT NOT NULL,
    margin_prev REAL, margin_bal REAL, short_prev REAL, short_bal REAL,
    PRIMARY KEY (date, code)
);
CREATE TABLE IF NOT EXISTS margin_day (
    date TEXT PRIMARY KEY,
    rows INTEGER NOT NULL DEFAULT 0,
    fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS corp_invest (
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    currency TEXT, cost REAL, shares REAL, pct REAL, book REAL, method TEXT
);
CREATE TABLE IF NOT EXISTS corp_board (
    code TEXT NOT NULL,
    title TEXT, name TEXT, corp TEXT, lots REAL, pct REAL
);
CREATE TABLE IF NOT EXISTS corp_fetch (
    code TEXT PRIMARY KEY,
    invest_rows INTEGER, board_rows INTEGER,
    fetched_at TEXT NOT NULL,
    error TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS company_name (
    code TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS intraday_tick (
    date TEXT NOT NULL,
    ts TEXT NOT NULL,
    data BLOB NOT NULL,
    PRIMARY KEY (date, ts)
);
CREATE TABLE IF NOT EXISTS yahoo_5m (
    code TEXT NOT NULL,
    date TEXT NOT NULL,
    bars TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (code, date)
);
CREATE TABLE IF NOT EXISTS yahoo_1m (
    code TEXT NOT NULL,
    date TEXT NOT NULL,
    bars TEXT NOT NULL,
    PRIMARY KEY (code, date)
);
CREATE TABLE IF NOT EXISTS finder_result (
    date TEXT NOT NULL,
    method TEXT NOT NULL,
    params TEXT NOT NULL,
    result TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    PRIMARY KEY (date, method, params)
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
        self._inst_version = 0  # bumped on institutional writes
        self._inst_day_version: dict[date, int] = {}  # per day: only that day's money-flow cache goes stale
        self.relations_version = 0  # bumped on 轉投資／董監／full-name writes (relations cache)
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
            c.execute("DELETE FROM finder_result WHERE date = ?", (day.isoformat(),))  # N's results used the old rows
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

    # ---- TWSE 類股指數 (C's 電子／金融／傳產 rows), kept in index_daily under those market names ----

    def save_sector_day(self, day: date, rows: dict | None, names: Iterable[str], fetched_at: datetime) -> None:
        """rows: {name: (close, change)}; every one of `names` gets a row, with a null close when the
        day had none, so a day without data is not asked for again."""
        with self._lock, self._conn() as c:
            c.executemany(
                "INSERT OR REPLACE INTO index_daily (date, market, close, change) VALUES (?, ?, ?, ?)",
                [(day.isoformat(), n, *((rows or {}).get(n) or (None, None))) for n in names],
            )

    def sector_dates(self, name: str) -> set[date]:
        with self._conn() as c:
            return {date.fromisoformat(r["date"]) for r in c.execute("SELECT date FROM index_daily WHERE market = ?", (name,))}

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
        self._inst_day_version[day] = self._inst_day_version.get(day, 0) + 1

    def inst_dates(self) -> set[date]:
        with self._conn() as c:
            return {date.fromisoformat(r["date"]) for r in c.execute("SELECT date FROM inst_day")}

    def inst_net(self, days: list[date], codes: Iterable[str] | None = None) -> dict[date, dict[str, float]]:
        """{day: {code: 三大法人 net shares}}; `codes` limits it to those stocks (a few cards, not ~2,000)."""
        return self._inst_column("total_net", days, codes)

    def _inst_column(self, column: str, days: list[date], codes: Iterable[str] | None) -> dict[date, dict[str, float]]:
        if not days:
            return {}
        out: dict[date, dict[str, float]] = {d: {} for d in days}
        sql = f"SELECT date, code, {column} FROM inst_daily WHERE date IN ({', '.join('?' for _ in days)})"
        args = [d.isoformat() for d in days]
        if codes is not None:
            codes = sorted(set(codes))
            sql += f" AND code IN ({', '.join('?' for _ in codes)})"
            args += codes
        with self._conn() as c:
            for d, code, net in c.execute(sql, args):
                out[date.fromisoformat(d)][code] = net or 0.0
        return out

    def inst_split(self, day: date) -> dict[str, tuple[float, float, float]]:
        """{code: (外資, 投信, 自營) net shares} for one day."""
        with self._conn() as c:
            return {
                code: (f or 0.0, t or 0.0, d or 0.0)
                for code, f, t, d in c.execute("SELECT code, foreign_net, trust_net, dealer_net FROM inst_daily WHERE date = ?", (day.isoformat(),))
            }

    def inst_trust(self, days: list[date], codes: Iterable[str] | None = None) -> dict[date, dict[str, float]]:
        """{day: {code: 投信 net shares}}"""
        return self._inst_column("trust_net", days, codes)

    # ---- 融資融券 balances (張) ----------------------------------------------------------------------

    def save_margin_day(self, day: date, rows: list | None, fetched_at: datetime) -> None:
        """rows: MarginRow-like objects, or None/[] for a day without data (recorded so it is not refetched)."""
        with self._lock, self._conn() as c:
            c.execute("DELETE FROM margin_daily WHERE date = ?", (day.isoformat(),))
            c.executemany(
                "INSERT INTO margin_daily (date, code, margin_prev, margin_bal, short_prev, short_bal) VALUES (?, ?, ?, ?, ?, ?)",
                [(day.isoformat(), r.code, r.margin_prev, r.margin_bal, r.short_prev, r.short_bal) for r in rows or []],
            )
            c.execute(
                "INSERT OR REPLACE INTO margin_day (date, rows, fetched_at) VALUES (?, ?, ?)",
                (day.isoformat(), len(rows or []), fetched_at.isoformat()),
            )

    def margin_dates(self) -> set[date]:
        with self._conn() as c:
            return {date.fromisoformat(r["date"]) for r in c.execute("SELECT date FROM margin_day")}

    def margin(self, days: list[date], codes: Iterable[str] | None = None) -> dict[date, dict[str, tuple[float, float, float, float]]]:
        """{day: {code: (融資前日餘額, 融資餘額, 融券前日餘額, 融券餘額)}} in 張; `codes` limits the stocks."""
        if not days:
            return {}
        out: dict[date, dict[str, tuple[float, float, float, float]]] = {d: {} for d in days}
        sql = f"SELECT date, code, margin_prev, margin_bal, short_prev, short_bal FROM margin_daily WHERE date IN ({', '.join('?' for _ in days)})"
        args = [d.isoformat() for d in days]
        if codes is not None:
            codes = sorted(set(codes))
            sql += f" AND code IN ({', '.join('?' for _ in codes)})"
            args += codes
        with self._conn() as c:
            for d, code, mp, mb, sp, sb in c.execute(sql, args):
                out[date.fromisoformat(d)][code] = (mp or 0.0, mb or 0.0, sp or 0.0, sb or 0.0)
        return out

    def inst_version(self, day: date | None = None) -> int:
        return self._inst_version if day is None else self._inst_day_version.get(day, 0)


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


    # ---- intraday: the app's own recorded polls (zlib JSON {code: price}) and Yahoo 5-minute bars --

    def save_tick(self, day: date, ts: str, prices: dict[str, float], keep_days: int = 20) -> None:
        import json
        import zlib

        blob = zlib.compress(json.dumps(prices, separators=(",", ":")).encode("utf-8"))
        with self._lock, self._conn() as c:
            c.execute("INSERT OR REPLACE INTO intraday_tick (date, ts, data) VALUES (?, ?, ?)", (day.isoformat(), ts, blob))
            old = [r["date"] for r in c.execute("SELECT DISTINCT date FROM intraday_tick ORDER BY date DESC LIMIT -1 OFFSET ?", (keep_days,))]
            if old:
                c.executemany("DELETE FROM intraday_tick WHERE date = ?", [(d,) for d in old])

    def tick_dates(self) -> set[date]:
        with self._conn() as c:
            return {date.fromisoformat(r["date"]) for r in c.execute("SELECT DISTINCT date FROM intraday_tick")}

    def ticks(self, day: date, codes: set[str]) -> dict[str, list[tuple[str, float]]]:
        """{code: [(HH:MM:SS, price)]} for `codes`, in time order."""
        import json
        import zlib

        out: dict[str, list[tuple[str, float]]] = {c: [] for c in codes}
        with self._conn() as c:
            for r in c.execute("SELECT ts, data FROM intraday_tick WHERE date = ? ORDER BY ts", (day.isoformat(),)):
                prices = json.loads(zlib.decompress(r["data"]))
                for code in codes:
                    p = prices.get(code)
                    if p is not None:
                        out[code].append((r["ts"], p))
        return out

    def save_yahoo_bars(self, code: str, by_day: dict[date, list], fetched_at: datetime) -> None:
        import json

        with self._lock, self._conn() as c:
            c.executemany(
                "INSERT OR REPLACE INTO yahoo_5m (code, date, bars, fetched_at) VALUES (?, ?, ?, ?)",
                [(code, d.isoformat(), json.dumps(b), fetched_at.isoformat()) for d, b in by_day.items()],
            )

    def yahoo_bars(self, code: str, days: list[date]) -> dict[date, list]:
        import json

        if not days:
            return {}
        marks = ", ".join("?" for _ in days)
        with self._conn() as c:
            return {
                date.fromisoformat(r["date"]): [tuple(x) for x in json.loads(r["bars"])]
                for r in c.execute(f"SELECT date, bars FROM yahoo_5m WHERE code = ? AND date IN ({marks})", [code, *[d.isoformat() for d in days]])
            }

    def save_yahoo_1m(self, code: str, day: date, bars: list) -> None:
        """One finished session's 1-minute bars (kept: a past session never changes)."""
        import json

        with self._lock, self._conn() as c:
            c.execute("INSERT OR REPLACE INTO yahoo_1m (code, date, bars) VALUES (?, ?, ?)", (code, day.isoformat(), json.dumps(bars)))

    def yahoo_1m(self, code: str, day: date) -> list | None:
        """Cached 1-minute bars, [] when Yahoo had none, None when never fetched."""
        import json

        with self._conn() as c:
            row = c.execute("SELECT bars FROM yahoo_1m WHERE code = ? AND date = ?", (code, day.isoformat())).fetchone()
        return [tuple(x) for x in json.loads(row["bars"])] if row else None

    def save_yahoo_1m_many(self, items: list[tuple[str, date, list]]) -> None:
        """Many (code, day, bars) in one transaction (N fetches dozens of stocks at once)."""
        import json

        if not items:
            return
        with self._lock, self._conn() as c:
            c.executemany(
                "INSERT OR REPLACE INTO yahoo_1m (code, date, bars) VALUES (?, ?, ?)",
                [(code, d.isoformat(), json.dumps(bars)) for code, d, bars in items],
            )

    def yahoo_1m_many(self, codes: list[str], days: list[date]) -> dict[tuple[str, date], list]:
        """{(code, day): bars} for what is cached ([] = Yahoo had none); missing keys were never fetched."""
        import json

        if not codes or not days:
            return {}
        out = {}
        dmarks = ", ".join("?" for _ in days)
        with self._conn() as c:
            for i in range(0, len(codes), 400):  # stay well under SQLite's variable limit
                part = codes[i : i + 400]
                cmarks = ", ".join("?" for _ in part)
                for r in c.execute(
                    f"SELECT code, date, bars FROM yahoo_1m WHERE code IN ({cmarks}) AND date IN ({dmarks})",
                    [*part, *[d.isoformat() for d in days]],
                ):
                    out[(r["code"], date.fromisoformat(r["date"]))] = [tuple(x) for x in json.loads(r["bars"])]
        return out

    def save_finder(self, day: date, method: str, params: str, result: dict) -> None:
        import json

        with self._lock, self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO finder_result (date, method, params, result, computed_at) VALUES (?, ?, ?, ?, ?)",
                (day.isoformat(), method, params, json.dumps(result, ensure_ascii=False), datetime.now().astimezone().isoformat()),
            )

    # ---- company relations (轉投資 / 法人董監, relations.py) and official full names -----------------

    def save_relations(self, code: str, invest: list | None, board: list | None, fetched_at: datetime, error: str = "") -> None:
        """Replace one stock's rows; an error keeps the old rows and only records the attempt."""
        with self._lock, self._conn() as c:
            if not error:
                c.execute("DELETE FROM corp_invest WHERE code = ?", (code,))
                c.execute("DELETE FROM corp_board WHERE code = ?", (code,))
                c.executemany(
                    "INSERT INTO corp_invest (code, name, currency, cost, shares, pct, book, method) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [(code, r.name, r.currency, r.cost, r.shares, r.pct, r.book, r.method) for r in invest or []],
                )
                c.executemany(
                    "INSERT INTO corp_board (code, title, name, corp, lots, pct) VALUES (?, ?, ?, ?, ?, ?)",
                    [(code, r.title, r.name, r.corp, r.lots, r.pct) for r in board or []],
                )
            c.execute(
                "INSERT OR REPLACE INTO corp_fetch (code, invest_rows, board_rows, fetched_at, error) VALUES (?, ?, ?, ?, ?)",
                (code, len(invest or []), len(board or []), fetched_at.isoformat(), error),
            )
        self.relations_version += 1

    def relation_fetched(self) -> dict[str, dict]:
        with self._conn() as c:
            return {r["code"]: {"fetched_at": r["fetched_at"], "error": r["error"]} for r in c.execute("SELECT code, fetched_at, error FROM corp_fetch")}

    def relation_rows(self) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
        """({code: its 轉投資 rows}, {code: its 董監 rows with a corporate holder})."""
        invest: dict[str, list[dict]] = {}
        board: dict[str, list[dict]] = {}
        with self._conn() as c:
            for r in c.execute("SELECT code, name, pct, method, shares, book FROM corp_invest"):
                invest.setdefault(r["code"], []).append(dict(r))
            for r in c.execute("SELECT code, title, name, corp, lots, pct FROM corp_board WHERE corp IS NOT NULL"):
                board.setdefault(r["code"], []).append(dict(r))
        return invest, board

    def save_company_names(self, names: dict[str, str], fetched_at: datetime) -> None:
        with self._lock, self._conn() as c:
            c.executemany("INSERT OR REPLACE INTO company_name (code, full_name, fetched_at) VALUES (?, ?, ?)", [(k, v, fetched_at.isoformat()) for k, v in names.items()])
        self.relations_version += 1

    def company_names(self) -> dict[str, str]:
        with self._conn() as c:
            return {r["code"]: r["full_name"] for r in c.execute("SELECT code, full_name FROM company_name")}

    def company_names_at(self) -> datetime | None:
        with self._conn() as c:
            row = c.execute("SELECT MAX(fetched_at) AS at FROM company_name").fetchone()
        return datetime.fromisoformat(row["at"]) if row and row["at"] else None

    def finder_any(self, days: list[date]) -> list[tuple[str, str, dict]]:
        """Every stored N result on `days`, whatever its thresholds: (date, method, result)."""
        import json

        if not days:
            return []
        with self._conn() as c:
            rows = c.execute(
                f"SELECT date, method, result FROM finder_result WHERE date IN ({', '.join('?' for _ in days)})", [d.isoformat() for d in days]
            ).fetchall()
        return [(r["date"], r["method"], json.loads(r["result"])) for r in rows]

    def finder(self, day: date, method: str, params: str) -> dict | None:
        import json

        with self._conn() as c:
            row = c.execute("SELECT result FROM finder_result WHERE date = ? AND method = ? AND params = ?", (day.isoformat(), method, params)).fetchone()
        return json.loads(row["result"]) if row else None

    def yahoo_fetched_at(self, code: str) -> datetime | None:
        with self._conn() as c:
            row = c.execute("SELECT MAX(fetched_at) AS f FROM yahoo_5m WHERE code = ?", (code,)).fetchone()
        return datetime.fromisoformat(row["f"]) if row and row["f"] else None
