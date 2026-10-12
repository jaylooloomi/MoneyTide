"""Trading-session rules for TWSE/TPEx (Asia/Taipei). Pure functions; `now` is always injected."""

from __future__ import annotations

from datetime import datetime, time, timedelta

from .config import TAIPEI

OPEN = time(9, 0)
CLOSE = time(13, 30)
FINAL_FETCH = time(13, 35)


def _local(now: datetime) -> datetime:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(TAIPEI)


def _at(day: datetime, t: time) -> datetime:
    return day.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)


def is_trading_day(now: datetime) -> bool:
    return _local(now).weekday() < 5


def is_market_open(now: datetime) -> bool:
    """True on weekdays for 09:00 <= t < 13:30 (Taipei time)."""
    local = _local(now)
    return is_trading_day(local) and OPEN <= local.time() < CLOSE


def _next_open(local: datetime) -> datetime:
    day = local
    if day.time() >= OPEN:
        day = day + timedelta(days=1)
    while day.weekday() >= 5:
        day = day + timedelta(days=1)
    return _at(day, OPEN)


def next_fetch_time(now: datetime, last_fetch: datetime | None, poll_seconds: int) -> datetime:
    """When the poller should fetch next. Returns `now` (or earlier) when a fetch is due.

    - Never fetched → due immediately (startup fetch, any time of day).
    - In session → every `poll_seconds`; a fetch that would land in 13:30–13:35 is pushed to 13:35.
    - 13:35 final fetch once per trading day (caught up if the app was idle at 13:35).
    - Otherwise → next trading day 09:00.
    """
    local = _local(now)
    if last_fetch is None:
        return local
    last = _local(last_fetch)

    if is_trading_day(local):
        open_at, close_at, final_at = _at(local, OPEN), _at(local, CLOSE), _at(local, FINAL_FETCH)
        if local < open_at:
            return open_at
        if local < close_at:
            candidate = max(last + timedelta(seconds=poll_seconds), open_at)
            return final_at if candidate >= close_at else candidate
        if last < final_at:
            return final_at
    return _next_open(local)
