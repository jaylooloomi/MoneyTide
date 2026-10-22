"""Background polling and the current snapshot.

Quotes are fetched on the market-clock schedule. Reference data (ISIN classification, issued
shares) is loaded from the JSON cache and refreshed in the background when older than 7 days —
the ISIN page is slow (~50 s), so it never blocks the first heatmap.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from datetime import datetime, timedelta

from .config import REFRESH_MIN_INTERVAL_SECONDS, STATIC_CACHE_MAX_AGE_DAYS, TAIPEI
from .market_clock import is_market_open, next_fetch_time
from .models import Quote, Snapshot, StockInfo
from .snapshot import build_stocks
from .storage import JsonCache, SettingsStore

log = logging.getLogger(__name__)

QuoteFetcher = Callable[[], Awaitable[list[Quote]]]
InfoFetcher = Callable[[], Awaitable[dict[str, StockInfo]]]
SharesFetcher = Callable[[], Awaitable[dict[str, int]]]
Clock = Callable[[], datetime]

MAX_IDLE_SLEEP_SECONDS = 5.0
REFERENCE_RETRY = timedelta(hours=1)


class RefreshTooSoon(Exception):
    def __init__(self, retry_after: float) -> None:
        super().__init__(f"refresh allowed again in {retry_after:.0f}s")
        self.retry_after = retry_after


def _now_taipei() -> datetime:
    return datetime.now(TAIPEI)


class Poller:
    def __init__(
        self,
        *,
        fetch_quotes: QuoteFetcher,
        fetch_infos: InfoFetcher,
        fetch_shares: SharesFetcher,
        info_cache: JsonCache,
        shares_cache: JsonCache,
        settings: SettingsStore,
        clock: Clock = _now_taipei,
    ) -> None:
        self._fetch_quotes = fetch_quotes
        self._fetch_infos = fetch_infos
        self._fetch_shares = fetch_shares
        self._info_cache = info_cache
        self._shares_cache = shares_cache
        self._settings = settings
        self._clock = clock

        self._quotes: list[Quote] = []
        self._infos: dict[str, StockInfo] = {}
        self._shares: dict[str, int] = {}
        self._quote_error = ""
        self._reference_errors: dict[str, str] = {}
        self._fetch_count = 0  # successful quote fetches (= Snapshot.version)
        self._attempts = 0  # finished quote fetch attempts
        self._as_of: datetime | None = None
        self._force_next = False
        self._reference_task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._reference_saved_at: dict[str, datetime] = {}
        self._reference_attempted_at: dict[str, datetime] = {}
        self.last_fetch: datetime | None = None

        self.snapshot = Snapshot(message="載入中…")
        self.boot_id = secrets.token_hex(4)
        self.revision = 0
        self._snapshot_json = b""
        self._wake = asyncio.Event()
        self._fetch_lock = asyncio.Lock()
        self._rebuild()

    # ---- reference data -------------------------------------------------
    # Each dataset ("infos", "shares") is refreshed when missing or older than 7 days; a failed
    # attempt is retried at most once per REFERENCE_RETRY (the ISIN page is ~9 MB).

    def load_reference_from_cache(self) -> None:
        """Load cached reference data; an unreadable or outdated cache is treated as missing."""
        decoders = {
            "infos": (self._info_cache, lambda data: {c: StockInfo(**v) for c, v in data.items()}),
            "shares": (self._shares_cache, lambda data: {c: int(v) for c, v in data.items()}),
        }
        for name, (cache, decode) in decoders.items():
            loaded = cache.load()
            if not loaded:
                continue
            try:
                value = decode(loaded[0])
                saved_at = loaded[1]
                saved_at - self._clock()  # naive timestamps raise TypeError here
            except (TypeError, ValueError, AttributeError, KeyError) as exc:
                log.warning("ignoring unreadable %s cache %s: %s", name, cache.path, exc)
                continue
            if name == "infos":
                self._infos = value
            else:
                self._shares = value
            self._reference_saved_at[name] = saved_at
        self._rebuild()

    def _reference_due(self, name: str, now: datetime) -> bool:
        saved = self._reference_saved_at.get(name)
        if saved is not None and now - saved < timedelta(days=STATIC_CACHE_MAX_AGE_DAYS):
            return False
        attempted = self._reference_attempted_at.get(name)
        return attempted is None or now - attempted >= REFERENCE_RETRY

    async def refresh_reference(self) -> None:
        now = self._clock()
        jobs = []
        if self._reference_due("infos", now):
            jobs.append(self._refresh_reference("infos", now))
        if self._reference_due("shares", now):
            jobs.append(self._refresh_reference("shares", now))
        if jobs:
            await asyncio.gather(*jobs)

    async def _refresh_reference(self, name: str, now: datetime) -> None:
        self._reference_attempted_at[name] = now
        label = "產業分類" if name == "infos" else "股本資料"
        try:
            if name == "infos":
                infos = await self._fetch_infos()
                self._info_cache.save({c: asdict(i) for c, i in infos.items()}, now)
                self._infos = infos
            else:
                shares = await self._fetch_shares()
                self._shares_cache.save(shares, now)
                self._shares = shares
        except Exception as exc:
            log.warning("%s fetch failed: %s", name, exc)
            self._reference_errors[name] = f"{label}更新失敗（{_short(exc)}）"
        else:
            self._reference_saved_at[name] = now
            self._reference_errors.pop(name, None)
        self._rebuild()

    def _start_reference_refresh(self) -> None:
        now = self._clock()
        if not (self._reference_due("infos", now) or self._reference_due("shares", now)):
            return
        if self._reference_task is None or self._reference_task.done():
            self._reference_task = asyncio.create_task(self.refresh_reference())

    # ---- quotes -------------------------------------------------------

    async def fetch_once(self) -> None:
        async with self._fetch_lock:
            now = self._clock()
            self.last_fetch = now
            try:
                quotes = await self._fetch_quotes()
            except Exception as exc:
                log.warning("quote fetch failed: %s", exc)
                self._quote_error = f"報價抓取失敗（{_short(exc)}），顯示上一次資料"
            else:
                self._quotes = quotes
                self._quote_error = ""
                self._fetch_count += 1
                self._as_of = self._clock()
            self._attempts += 1
            self._rebuild()

    def request_refresh(self) -> None:
        """Manual refresh; throttled to one fetch per REFRESH_MIN_INTERVAL_SECONDS.
        A request while a fetch is running is coalesced into that fetch."""
        if self._fetch_lock.locked():
            return
        if self.last_fetch is not None:
            elapsed = (self._clock() - self.last_fetch).total_seconds()
            if elapsed < REFRESH_MIN_INTERVAL_SECONDS:
                raise RefreshTooSoon(REFRESH_MIN_INTERVAL_SECONDS - elapsed)
        self._force_next = True
        self._wake_up()

    def settings_changed(self) -> None:
        self._wake_up()

    def _wake_up(self) -> None:
        """asyncio.Event is not thread-safe; API handlers may run in worker threads."""
        loop = self._loop
        if loop is not None and loop.is_running():
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is not loop:
                loop.call_soon_threadsafe(self._wake.set)
                return
        self._wake.set()

    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        self.load_reference_from_cache()
        self._start_reference_refresh()
        try:
            while True:
                try:
                    await self._step()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    # Never let an unexpected error end polling for good.
                    log.exception("poll loop error")
                    await asyncio.sleep(MAX_IDLE_SLEEP_SECONDS)
        finally:
            if self._reference_task is not None:
                self._reference_task.cancel()

    async def _step(self) -> None:
        now = self._clock()
        last_failed = bool(self._quote_error) or (self._attempts > 0 and self._fetch_count == 0)
        due = next_fetch_time(now, self.last_fetch, self._settings.poll_seconds, last_failed)
        if self._force_next or due <= now:
            self._force_next = False
            await self.fetch_once()
            self._start_reference_refresh()
            return
        wait = min((due - now).total_seconds(), MAX_IDLE_SLEEP_SECONDS)
        self._wake.clear()
        try:
            await asyncio.wait_for(self._wake.wait(), timeout=wait)
        except TimeoutError:
            pass
        # idle housekeeping: market_open flips at 09:00/13:30; failed reference data is retried
        if self.snapshot.market_open != is_market_open(self._clock()):
            self._rebuild()
        self._start_reference_refresh()

    # ---- snapshot -----------------------------------------------------

    def _rebuild(self) -> None:
        stocks = build_stocks(self._quotes, self._infos, self._shares)
        if self._fetch_count:
            status = "stale" if self._quote_error else "ok"
        else:
            status = "error" if self._attempts else "loading"
        messages = [m for m in [self._quote_error, *self._reference_errors.values()] if m]
        if status == "loading":
            messages.insert(0, "載入中…")
        if self._quotes and not self._infos:
            messages.append("尚無產業分類資料，全部歸類為「其他」")
        snap = Snapshot(
            version=self._fetch_count,
            as_of=self._as_of.isoformat() if self._as_of else None,
            status=status,
            message="；".join(messages),
            market_open=is_market_open(self._clock()),
            stocks=stocks,
        )
        body = json.dumps(snap.to_dict(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if body != self._snapshot_json:
            self.snapshot = snap
            self._snapshot_json = body
            self.revision += 1

    @property
    def infos(self) -> dict[str, StockInfo]:
        return self._infos

    @property
    def shares(self) -> dict[str, int]:
        return self._shares

    @property
    def snapshot_json(self) -> bytes:
        return self._snapshot_json

    @property
    def etag(self) -> str:
        return f'"{self.boot_id}-{self.revision}"'


def _short(exc: BaseException) -> str:
    text = str(exc) or type(exc).__name__
    return text if len(text) <= 120 else text[:117] + "..."
