"""Build daily history rows and keep the store filled (one-year backfill + daily after close)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from ..config import TAIPEI
from ..models import StockInfo
from ..sources.official import DailyRow
from .store import HistoryStore

log = logging.getLogger(__name__)

BACKFILL_DAYS = 365
REQUEST_DELAY_SECONDS = 3.0  # TWSE blocks clients that request too fast
DAILY_READY = time(15, 30)  # official after-close data is published by then
DAILY_GIVE_UP = time(20, 0)  # after this, an empty "today" is treated as a non-trading day
RETRY_INTERVAL = timedelta(minutes=30)

DayFetcher = Callable[[date], Awaitable[list[DailyRow] | None]]


def build_rows(
    day_rows: list[DailyRow], infos: Mapping[str, StockInfo], shares: Mapping[str, int]
) -> list[dict]:
    """Merge official rows with classification. Codes unknown to ISIN are skipped."""
    out = []
    for r in day_rows:
        info = infos.get(r.code)
        if info is None:
            continue
        prev = r.close - r.change if r.close is not None and r.change is not None else None
        pct = r.change / prev * 100 if prev and r.change is not None else None
        n_shares = r.shares or shares.get(r.code)
        ref = r.close if r.close is not None else prev
        out.append({
            "code": r.code,
            "name": r.name,
            "market": r.market,
            "industry": info.industry or "其他",
            "kind": info.kind,
            "close": r.close,
            "prev_close": round(prev, 4) if prev is not None else None,
            "change": r.change,
            "change_pct": round(pct, 4) if pct is not None else None,
            "open": r.open,
            "high": r.high,
            "low": r.low,
            "volume_shares": r.volume_shares,
            "turnover_yuan": r.turnover_yuan,
            "market_cap": ref * n_shares if ref and n_shares and info.kind == "stock" else None,
        })
    return out


@dataclass
class BackfillState:
    running: bool = False
    done: int = 0
    total: int = 0
    error: str = ""

    def to_dict(self) -> dict:
        return {"running": self.running, "done": self.done, "total": self.total, "error": self.error}


class HistoryCollector:
    def __init__(
        self,
        *,
        store: HistoryStore,
        fetch_twse: DayFetcher,
        fetch_tpex: DayFetcher,
        reference: Callable[[], tuple[Mapping[str, StockInfo], Mapping[str, int]]],
        clock: Callable[[], datetime] = lambda: datetime.now(TAIPEI),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        request_delay: float = REQUEST_DELAY_SECONDS,
    ) -> None:
        self.store = store
        self._fetch_twse = fetch_twse
        self._fetch_tpex = fetch_tpex
        self._reference = reference
        self._clock = clock
        self._sleep = sleep
        self._delay = request_delay
        self.state = BackfillState()

    def pending_days(self, now: datetime) -> list[date]:
        """Weekdays within the backfill window that are not stored yet, newest first."""
        local = now.astimezone(TAIPEI)
        today = local.date()
        known = self.store.days()
        days = []
        for i in range(BACKFILL_DAYS + 1):
            d = today - timedelta(days=i)
            if d.weekday() >= 5 or d in known:
                continue
            if d == today and local.time() < DAILY_READY:
                continue
            days.append(d)
        return days

    async def collect_day(self, day: date) -> str:
        """Fetch and store one day. Returns 'ok', 'no_data' or 'not_ready'."""
        twse = await self._fetch_twse(day)
        await self._sleep(self._delay)
        tpex = await self._fetch_tpex(day)
        now = self._clock()
        local = now.astimezone(TAIPEI)
        is_today = day == local.date()
        if twse is None and tpex is None:
            if is_today and local.time() < DAILY_GIVE_UP:
                return "not_ready"
            self.store.mark_no_data(day, now)
            return "no_data"
        if is_today and (twse is None or tpex is None) and local.time() < DAILY_GIVE_UP:
            return "not_ready"  # one market not published yet
        infos, shares = self._reference()
        self.store.save_day(day, build_rows((twse or []) + (tpex or []), infos, shares), now)
        return "ok"

    async def run_once(self) -> None:
        """One pass over every pending day (newest first)."""
        infos, _ = self._reference()
        if not infos:
            return  # wait for the ISIN classification
        pending = self.pending_days(self._clock())
        self.state = BackfillState(running=bool(pending), total=len(pending))
        for day in pending:
            try:
                await self.collect_day(day)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("history fetch for %s failed: %s", day, exc)
                self.state.error = f"{day}: {exc}"
            self.state.done += 1
            await self._sleep(self._delay)
        self.state.running = False
        await asyncio.to_thread(warm_history_cache, self.store)  # bonus-19

    async def run(self) -> None:
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("history collector error")
            infos, _ = self._reference()
            await self._sleep(60 if not infos else RETRY_INTERVAL.total_seconds())


# ---- bonus-19: warm the derived-results cache so the first history visit is fast ----

WARM_DAYS = 60  # the longest window the history page asks for by default (5/20/60-day columns)


def warm_history_cache(store: HistoryStore) -> None:
    """Precompute what the history page predictably needs right after a (re)start: per-day
    official-industry averages for the latest WARM_DAYS trading days and the 20-day turnover
    averages. Cheap when already cached; errors are logged, never raised."""
    from .metrics import daily_group_avgs, industry_grouping  # local: metrics imports store too

    try:
        dates = sorted(store.trading_dates(limit=WARM_DAYS))
        if dates:
            daily_group_avgs(store, dates, industry_grouping)
            store.group_turnover_avg(20)
    except Exception:
        log.exception("history cache warm-up failed")
