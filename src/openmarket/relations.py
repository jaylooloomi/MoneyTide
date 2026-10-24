"""Company relations (轉投資 / 法人董監 / 集團) between listed common stocks, crawled slowly from MoneyDJ.

Edges, all between two listed stocks (names are matched to codes by the official full / short names):
- invest: A's 轉投資 lists B (pct = A's stake in B, method = 權益法 / 綜合公允 / …)
- board:  B's 董監事 has A as a corporate director (pct = A's stake in B, title = 董事長 / 董事 / 監察人)
Groups: stocks joined by an equity-method stake ≥ GROUP_PCT or any board seat, the largest market cap first.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .config import TAIPEI
from .history.store import HistoryStore

log = logging.getLogger(__name__)

REFRESH_DAYS = 30  # 轉投資 / 董監 change with the quarterly reports: a month is fresh enough
RETRY_HOURS = 24  # a stock that failed is tried again after this long
PAGE_DELAY = 4.0  # seconds between two pages (plus a random 0–2 s): MoneyDJ is a broker's site, go slow
START_DELAY = 300  # wait after start-up, so the crawl never competes with the first page loads
PAUSE_AFTER_FAILS = 3  # this many failures in a row → stop for PAUSE_SECONDS (blocked / site down)
PAUSE_SECONDS = 900
GROUP_PCT = 20.0  # an equity-method stake from this % (關係企業) joins a group


def norm_name(name: str) -> str:
    """Company name for matching: no 股份有限公司 / (股) / spaces, 台 for 臺."""
    s = re.sub(r"\s+", "", name or "")
    for suffix in ("股份有限公司", "有限公司", "(股)", "（股）", "公司"):
        s = s.replace(suffix, "")
    return s.replace("臺", "台")


@dataclass
class NameIndex:
    """norm(full name) / norm(short name) → code, for the listed common stocks."""

    by_name: dict[str, str] = field(default_factory=dict)

    @classmethod
    def build(cls, full_names: Mapping[str, str], short_names: Mapping[str, str]) -> NameIndex:
        idx = cls()
        for code, n in short_names.items():
            if n:
                idx.by_name.setdefault(norm_name(n), code)
        for code, n in full_names.items():  # full names win over a clashing short name
            if n:
                idx.by_name[norm_name(n)] = code
        return idx

    def code(self, name: str) -> str | None:
        return self.by_name.get(norm_name(name))


def relation_edges(invest: Mapping[str, list[dict]], board: Mapping[str, list[dict]], idx: NameIndex, listed: Iterable[str]) -> list[dict]:
    """Edges between listed stocks: {src, dst, kind: invest|board, pct, method|title}; src holds dst."""
    listed = set(listed)
    out = []
    for src, rows in invest.items():
        for r in rows:
            dst = idx.code(r["name"])
            if dst and dst != src and dst in listed:
                out.append({"src": src, "dst": dst, "kind": "invest", "pct": r.get("pct"), "method": r.get("method") or ""})
    for dst, rows in board.items():
        for r in rows:
            src = idx.code(r["corp"]) if r.get("corp") else None
            if src and src != dst and src in listed:
                out.append({"src": src, "dst": dst, "kind": "board", "pct": r.get("pct"), "title": r.get("title") or ""})
    return out


def relation_groups(edges: list[dict], caps: Mapping[str, float]) -> dict[str, dict]:
    """{code: {id, leader, members}} for stocks joined by a ≥ GROUP_PCT equity-method stake or a board
    seat; a group is named after its largest market cap (leader). Lone stocks have no group."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in edges:
        strong = e["kind"] == "board" or ("權益法" in (e.get("method") or "") and (e.get("pct") or 0) >= GROUP_PCT)
        if strong:
            parent[find(e["src"])] = find(e["dst"])
    comps: dict[str, list[str]] = {}
    for c in list(parent):
        comps.setdefault(find(c), []).append(c)
    out = {}
    for members in comps.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda c: -(caps.get(c) or 0))
        g = {"id": members[0], "leader": members[0], "members": members}
        for c in members:
            out[c] = g
    return out


class RelationCollector:
    """Crawls MoneyDJ's 轉投資 + 董監持股 pages, one stock at a time, slowly; fresh for REFRESH_DAYS."""

    def __init__(
        self,
        *,
        store: HistoryStore,
        fetch: Callable[[str], Awaitable[tuple[list, list]]],
        fetch_names: Callable[[], Awaitable[dict[str, str]]],
        codes: Callable[[], list[str]],
        clock: Callable[[], datetime] = lambda: datetime.now(TAIPEI),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        start_delay: float = START_DELAY,
    ) -> None:
        self.store = store
        self._fetch = fetch
        self._fetch_names = fetch_names
        self._codes = codes
        self._clock = clock
        self._sleep = sleep
        self._start_delay = start_delay
        self.running = False
        self.done = 0
        self.total = 0
        self.error = ""
        self.paused_until: datetime | None = None

    def status(self) -> dict:
        fetched = self.store.relation_fetched()
        return {
            "running": self.running, "done": self.done, "total": self.total, "error": self.error,
            "stored": sum(1 for v in fetched.values() if not v["error"]),
            "paused_until": self.paused_until.isoformat() if self.paused_until else None,
        }

    def due(self) -> list[str]:
        now = self._clock()
        fetched = self.store.relation_fetched()
        out = []
        for c in self._codes():
            f = fetched.get(c)
            if f is None:
                out.append(c)
                continue
            age = now - datetime.fromisoformat(f["fetched_at"])
            if (f["error"] and age > timedelta(hours=RETRY_HOURS)) or age > timedelta(days=REFRESH_DAYS):
                out.append(c)
        return out

    async def run_once(self) -> None:
        if not self.store.company_names() or self._clock() - (self.store.company_names_at() or datetime.min.replace(tzinfo=TAIPEI)) > timedelta(days=7):
            try:
                names = await self._fetch_names()
                if names:
                    self.store.save_company_names(names, self._clock())
            except Exception as exc:  # the names only help matching: crawl anyway
                log.warning("company full names failed: %s", exc)
        todo = self.due()
        self.running, self.done, self.total = bool(todo), 0, len(todo)
        fails = 0
        for code in todo:
            try:
                invest, board = await self._fetch(code)
                self.store.save_relations(code, invest, board, self._clock())
                fails = 0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                fails += 1
                self.error = f"{code}: {type(exc).__name__}"
                self.store.save_relations(code, None, None, self._clock(), error=self.error)
                if fails >= PAUSE_AFTER_FAILS:  # blocked or down: back off instead of hammering
                    self.paused_until = self._clock() + timedelta(seconds=PAUSE_SECONDS)
                    log.warning("relations: %d failures in a row, pausing %ds", fails, PAUSE_SECONDS)
                    await self._sleep(PAUSE_SECONDS)
                    self.paused_until = None
                    fails = 0
            self.done += 1
            await self._sleep(PAGE_DELAY + random.uniform(0, 2))
        self.running = False

    async def run(self) -> None:
        await self._sleep(self._start_delay)
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("relations pass failed: %s", exc)
                self.error = str(exc)
            await self._sleep(6 * 3600)
