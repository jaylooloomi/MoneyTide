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
IndexFetcher = Callable[[str, date], Awaitable[list]]  # (market, any day of the month) -> IndexRow list
InstFetcher = Callable[[date], Awaitable[list | None]]  # day -> InstRow list, None when not published
MarginFetcher = Callable[[date], Awaitable[list | None]]  # day -> MarginRow list, None when not published
INST_DAYS = 250  # 三大法人 backfill window (stored trading days)
DAYTRADE_DAYS = 60  # TWSE 當日沖銷 backfill window (one request a day)
SECTOR_DAYS = 120  # TWSE 類股指數 backfill window (one request a day)
MARGIN_DAYS = 120  # 融資融券 backfill window (two requests a day, so a shorter first backfill)


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
        fetch_index: IndexFetcher | None = None,
        fetch_inst: InstFetcher | None = None,
        fetch_margin: MarginFetcher | None = None,
        fetch_sectors: Callable[[date], Awaitable[dict | None]] | None = None,
        fetch_daytrade: Callable[[date], Awaitable[dict | None]] | None = None,
        fetch_exrights: Callable[[date, date], Awaitable[dict]] | None = None,
        fetch_daytrade_tpex: Callable[[date], Awaitable[dict | None]] | None = None,
    ) -> None:
        self.store = store
        self._fetch_twse = fetch_twse
        self._fetch_tpex = fetch_tpex
        self._reference = reference
        self._clock = clock
        self._sleep = sleep
        self._delay = request_delay
        self.state = BackfillState()
        self._fetch_index = fetch_index
        self.index_state = BackfillState()
        self._fetch_inst = fetch_inst
        self.inst_state = BackfillState()
        self._fetch_margin = fetch_margin
        self.margin_state = BackfillState()
        self._fetch_sectors = fetch_sectors
        self.sector_state = BackfillState()
        self._fetch_daytrade = fetch_daytrade
        self.daytrade_state = BackfillState()
        self._fetch_exrights = fetch_exrights
        self._fetch_daytrade_tpex = fetch_daytrade_tpex
        self.exright_state = BackfillState()

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
        await self.collect_index()
        await self.collect_inst()
        await self.collect_margin()
        await self.collect_sectors()
        await self.collect_daytrade()
        await self.collect_exrights()
        await asyncio.to_thread(warm_history_cache, self.store)  # bonus-19

    async def collect_index(self) -> None:
        """Fetch the index months that are missing or stale (see index_months_to_fetch)."""
        if self._fetch_index is None:
            return
        now = self._clock()
        todo = index_months_to_fetch(self.store.index_months(), now)
        self.index_state = BackfillState(running=bool(todo), total=len(todo))
        for market, month in todo:
            try:
                rows = await self._fetch_index(market, date.fromisoformat(month + "-01"))
                self.store.save_index_month(market, month, rows, self._clock())
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("index fetch %s %s failed: %s", market, month, exc)
                self.index_state.error = f"{market} {month}: {exc}"
            self.index_state.done += 1
            await self._sleep(self._delay)
        self.index_state.running = False

    async def collect_inst(self) -> None:
        """三大法人 for stored trading days that have none yet (newest first)."""
        if self._fetch_inst is None:
            return
        known = self.store.inst_dates()
        todo = [d for d in self.store.trading_dates(limit=INST_DAYS) if d not in known]
        self.inst_state = BackfillState(running=bool(todo), total=len(todo))
        for d in todo:
            try:
                rows = await self._fetch_inst(d)
                local = self._clock().astimezone(TAIPEI)
                if rows is None and d == local.date() and local.time() < DAILY_GIVE_UP:
                    pass  # published later in the evening: try again next pass
                else:
                    self.store.save_inst_day(d, rows, self._clock())
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("institutional data for %s failed: %s", d, exc)
                self.inst_state.error = f"{d}: {exc}"
            self.inst_state.done += 1
            await self._sleep(self._delay)
        self.inst_state.running = False

    async def collect_margin(self) -> None:
        """融資融券 for stored trading days that have none yet (newest first), like collect_inst."""
        if self._fetch_margin is None:
            return
        known = self.store.margin_dates()
        todo = [d for d in self.store.trading_dates(limit=MARGIN_DAYS) if d not in known]
        self.margin_state = BackfillState(running=bool(todo), total=len(todo))
        for d in todo:
            try:
                rows = await self._fetch_margin(d)
                local = self._clock().astimezone(TAIPEI)
                if rows is None and d == local.date() and local.time() < DAILY_GIVE_UP:
                    pass  # published later in the evening: try again next pass
                else:
                    self.store.save_margin_day(d, rows, self._clock())
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("margin data for %s failed: %s", d, exc)
                self.margin_state.error = f"{d}: {exc}"
            self.margin_state.done += 1
            await self._sleep(self._delay)
        self.margin_state.running = False

    async def collect_sectors(self) -> None:
        """TWSE 電子／金融／傳產 類股指數 for stored trading days that have none yet (newest first)."""
        if self._fetch_sectors is None:
            return
        from ..sources.sector_index import SECTORS

        known = self.store.sector_dates(next(iter(SECTORS)))
        todo = [d for d in self.store.trading_dates(limit=SECTOR_DAYS) if d not in known]
        self.sector_state = BackfillState(running=bool(todo), total=len(todo))
        for d in todo:
            try:
                rows = await self._fetch_sectors(d)
                local = self._clock().astimezone(TAIPEI)
                if rows is None and d == local.date() and local.time() < DAILY_GIVE_UP:
                    pass  # published later in the afternoon: try again next pass
                else:
                    self.store.save_sector_day(d, rows, SECTORS, self._clock())
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("sector indices for %s failed: %s", d, exc)
                self.sector_state.error = f"{d}: {exc}"
            self.sector_state.done += 1
            await self._sleep(self._delay)
        self.sector_state.running = False

    async def collect_daytrade(self) -> None:
        """TWSE 當日沖銷 for stored trading days that have none yet (newest first); a day the site has
        nothing for is retried on later passes until DAILY_GIVE_UP, then left alone."""
        if self._fetch_daytrade is None:
            return
        with self.store._conn() as c:
            tried = {date.fromisoformat(r["date"]) for r in c.execute("SELECT date FROM daytrade_day")}
        todo = [d for d in self.store.trading_dates(limit=DAYTRADE_DAYS) if d not in tried]
        self.daytrade_state = BackfillState(running=bool(todo), total=len(todo))
        for d in todo:
            try:
                rows = await self._fetch_daytrade(d)
                local = self._clock().astimezone(TAIPEI)
                if rows is None and d == local.date() and local.time() < DAILY_GIVE_UP:
                    pass  # published in the evening: try again next pass
                else:
                    self.store.save_daytrade_day(d, rows, self._clock())
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("day-trading data for %s failed: %s", d, exc)
                self.daytrade_state.error = f"{d}: {exc}"
            self.daytrade_state.done += 1
            await self._sleep(self._delay)
        self.daytrade_state.running = False
        await self.collect_daytrade_tpex()

    async def collect_daytrade_tpex(self) -> None:
        """TPEx 當日沖銷 for the same window, tracked apart (the TWSE days were stored before TPEx had any)."""
        if self._fetch_daytrade_tpex is None:
            return
        tried = self.store.daytrade_tpex_tried()
        todo = [d for d in self.store.trading_dates(limit=DAYTRADE_DAYS) if d not in tried]
        for d in todo:
            try:
                rows = await self._fetch_daytrade_tpex(d)
                local = self._clock().astimezone(TAIPEI)
                if not (rows is None and d == local.date() and local.time() < DAILY_GIVE_UP):
                    self.store.save_daytrade_tpex_day(d, rows, self._clock())
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("TPEx day-trading data for %s failed: %s", d, exc)
            await self._sleep(self._delay)

    async def collect_exrights(self) -> None:
        """除權息參考價 for the stored days whose rows lack a 昨收, one request per month and site."""
        if self._fetch_exrights is None:
            return
        gaps = self.store.ex_rights_gaps()
        months = sorted({(d.year, d.month) for d in gaps}, reverse=True)
        self.exright_state = BackfillState(running=bool(months), total=len(months))
        for y, mo in months:
            days = [d for d in gaps if (d.year, d.month) == (y, mo)]
            try:
                refs = await self._fetch_exrights(min(days), max(days))
                for d in days:
                    self.store.fill_ex_rights(d, refs.get(d, {}), self._clock())
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("ex-rights reference prices for %s-%02d failed: %s", y, mo, exc)
                self.exright_state.error = f"{y}-{mo:02d}: {exc}"
            self.exright_state.done += 1
            await self._sleep(self._delay)
        self.exright_state.running = False

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


# ---- market index history (G panel) ---------------------------------------------------

INDEX_MONTHS = 13  # the current month plus the 12 before it
INDEX_MARKETS = ("上市", "上櫃")


def index_window(now: datetime) -> list[str]:
    """'YYYY-MM' of the current month and the INDEX_MONTHS - 1 before it, newest first."""
    local = now.astimezone(TAIPEI)
    y, m = local.year, local.month
    out = []
    for _ in range(INDEX_MONTHS):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return out


def index_months_to_fetch(fetched: dict[tuple[str, str], datetime], now: datetime) -> list[tuple[str, str]]:
    """(market, month) pairs to (re)fetch, newest first. A month is due when it was never fetched,
    or when it was fetched before the latest 15:30 close that falls inside it (so the current month
    refreshes once a day after the close, and last month once more after its final session)."""
    local = now.astimezone(TAIPEI)
    ready_today = datetime.combine(local.date(), DAILY_READY, TAIPEI)
    latest_ready = ready_today if local >= ready_today else ready_today - timedelta(days=1)
    due = []
    for month in index_window(now):
        y, m = int(month[:4]), int(month[5:])
        first_next = date(y + (m == 12), m % 12 + 1, 1)
        month_last_ready = datetime.combine(first_next - timedelta(days=1), DAILY_READY, TAIPEI)
        needed = min(latest_ready, month_last_ready)
        for market in INDEX_MARKETS:
            got = fetched.get((market, month))
            if got is None or got.astimezone(TAIPEI) < needed:
                due.append((market, month))
    return due
