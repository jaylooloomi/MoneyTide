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


def _latest_final_fetch(local: datetime) -> datetime:
    """The most recent trading-day 13:35 at or before `local`."""
    day = local if local.time() >= FINAL_FETCH else local - timedelta(days=1)
    while day.weekday() >= 5:
        day = day - timedelta(days=1)
    return _at(day, FINAL_FETCH)


def _scheduled_fetch_time(local: datetime, last: datetime, poll_seconds: int) -> datetime:
    if is_trading_day(local):
        open_at, close_at, final_at = _at(local, OPEN), _at(local, CLOSE), _at(local, FINAL_FETCH)
        if open_at <= local < close_at:
            candidate = open_at if last < open_at else last + timedelta(seconds=poll_seconds)
            return final_at if candidate >= close_at else candidate
    # Out of session: catch up a missed closing fetch (e.g. the laptop slept through 13:35).
    latest_final = _latest_final_fetch(local)
    if last < latest_final:
        return latest_final
    if is_trading_day(local):
        if local < _at(local, OPEN):
            return _at(local, OPEN)
        if local < _at(local, FINAL_FETCH):
            return _at(local, FINAL_FETCH)
    return _next_open(local)


def next_fetch_time(
    now: datetime, last_fetch: datetime | None, poll_seconds: int, last_failed: bool = False
) -> datetime:
    """When the poller should fetch next. Returns `now` (or earlier) when a fetch is due.

    - Never fetched → due immediately (startup fetch, any time of day).
    - In session → every `poll_seconds`; a fetch that would land in 13:30–13:35 is pushed to 13:35.
    - The 13:35 closing fetch is caught up whenever the latest one was missed (sleep, restart).
    - Otherwise → next trading day 09:00.
    - After a failed attempt, retry every `poll_seconds` even out of session.
    """
    local = _local(now)
    if last_fetch is None:
        return local
    last = _local(last_fetch)
    scheduled = _scheduled_fetch_time(local, last, poll_seconds)
    if not last_failed:
        return scheduled
    retry = last + timedelta(seconds=poll_seconds)
    if is_trading_day(retry) and _at(retry, CLOSE) <= retry < _at(retry, FINAL_FETCH):
        retry = _at(retry, FINAL_FETCH)
    return min(scheduled, retry)
