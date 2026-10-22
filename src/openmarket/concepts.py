"""Background loader for concept-stock groups, cached in data/concepts_cache.json for 7 days."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from .config import STATIC_CACHE_MAX_AGE_DAYS, TAIPEI
from .sources.yahoo_concepts import code_to_concepts
from .storage import JsonCache

log = logging.getLogger(__name__)

RETRY = timedelta(hours=1)


class ConceptLoader:
    def __init__(
        self,
        *,
        cache: JsonCache,
        fetch: Callable[[Callable[[int, int], None]], Awaitable[dict[str, list[str]]]],
        clock: Callable[[], datetime] = lambda: datetime.now(TAIPEI),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._cache = cache
        self._fetch = fetch
        self._clock = clock
        self._sleep = sleep
        self.concepts: dict[str, list[str]] = {}
        self.mapping: dict[str, list[str]] = {}
        self.saved_at: datetime | None = None
        self.running = False
        self.done = 0
        self.total = 0
        self.error = ""
        self._attempted_at: datetime | None = None

    def status(self) -> dict:
        return {
            "ready": bool(self.concepts),
            "count": len(self.concepts),
            "saved_at": self.saved_at.isoformat() if self.saved_at else None,
            "running": self.running,
            "done": self.done,
            "total": self.total,
            "error": self.error,
        }

    def _set(self, concepts: dict[str, list[str]], saved_at: datetime) -> None:
        self.concepts = concepts
        self.mapping = code_to_concepts(concepts)
        self.saved_at = saved_at

    def load_cache(self) -> None:
        loaded = self._cache.load()
        if not loaded:
            return
        data, saved_at = loaded
        try:
            concepts = {str(k): [str(c) for c in v] for k, v in data.items()}
            saved_at - self._clock()
        except (AttributeError, TypeError, ValueError) as exc:
            log.warning("ignoring unreadable concepts cache: %s", exc)
            return
        self._set(concepts, saved_at)

    def due(self, now: datetime) -> bool:
        if self.saved_at and now - self.saved_at < timedelta(days=STATIC_CACHE_MAX_AGE_DAYS):
            return False
        return self._attempted_at is None or now - self._attempted_at >= RETRY

    def _progress(self, done: int, total: int) -> None:
        self.done, self.total = done, total

    async def refresh(self) -> None:
        now = self._clock()
        self._attempted_at = now
        self.running, self.done, self.total = True, 0, 0
        try:
            concepts = await self._fetch(self._progress)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("concept groups fetch failed: %s", exc)
            self.error = str(exc) or type(exc).__name__
        else:
            self._cache.save(concepts, now)
            self._set(concepts, now)
            self.error = ""
        finally:
            self.running = False

    async def run(self) -> None:
        self.load_cache()
        while True:
            try:
                if self.due(self._clock()):
                    await self.refresh()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("concept loader error")
            await self._sleep(600)
