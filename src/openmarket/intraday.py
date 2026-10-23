"""Records every live poll during the session into the history store (intraday_tick), so the linkage
panel has minute-level prices for all listed stocks without any extra data source.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, time

from .config import TAIPEI
from .history.store import HistoryStore

log = logging.getLogger(__name__)

SESSION_START = time(9, 0)
SESSION_END = time(13, 40)  # includes the 13:35 post-close fetch with the closing prices
CHECK_SECONDS = 10
KEEP_DAYS = 20


class IntradayRecorder:
    def __init__(self, *, store: HistoryStore, get_poller: Callable[[], object | None],
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        self.store = store
        self._get_poller = get_poller
        self._sleep = sleep
        self._last_version: int | None = None

    def record_once(self) -> bool:
        p = self._get_poller()
        snap = getattr(p, "snapshot", None)
        if snap is None or not snap.as_of or snap.version == self._last_version:
            return False
        at = datetime.fromisoformat(snap.as_of).astimezone(TAIPEI)
        if at.weekday() >= 5 or not (SESSION_START <= at.time() <= SESSION_END):
            return False
        prices = {s.code: s.price for s in snap.stocks if s.kind == "stock" and s.price is not None}
        if not prices:
            return False
        self._last_version = snap.version
        self.store.save_tick(at.date(), at.strftime("%H:%M:%S"), prices, keep_days=KEEP_DAYS)
        return True

    async def run(self) -> None:
        while True:
            try:
                await asyncio.to_thread(self.record_once)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("intraday recorder error")
            await self._sleep(CHECK_SECONDS)
