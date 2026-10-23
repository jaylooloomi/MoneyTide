"""5-minute bars from Yahoo Finance's chart API (unofficial; used only to backfill a group's top members
for days the app did not record itself).

https://query1.finance.yahoo.com/v8/finance/chart/<code>.TW (上市) or .TWO (上櫃)?interval=5m&range=60d
→ chart.result[0]: timestamp[] (epoch, bar start), indicators.quote[0]: open/high/low/close/volume
(null for empty bars). About 54 bars per session (09:00–13:25 starts) and up to 60 days back.

1-minute bars (for the peak time) come from the same API with interval=1m and a period1/period2
window; Yahoo keeps them for about 30 days and serves at most 8 days per request.
"""

from __future__ import annotations

from datetime import date, datetime, time

import httpx

from ..config import TAIPEI
from ..models import ParseError
from .http import get_with_retry

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=5m&range={range}"
DAY_1M_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m&period1={start}&period2={end}"
ONE_MINUTE_DAYS = 29  # Yahoo drops 1m bars after about 30 days


# K's two benchmark rows: Yahoo symbol → (name, market of the official index row)
INDEX_SYMBOLS = {"^TWII": ("大盤（加權）", "上市"), "IX0043.TWO": ("櫃買（OTC）", "上櫃")}


def symbol_for(code: str, market: str) -> str:
    if code in INDEX_SYMBOLS:  # an index is already a Yahoo symbol
        return code
    return f"{code}.{'TWO' if market == '上櫃' else 'TW'}"


def parse_chart(payload: dict) -> dict[date, list[tuple]]:
    """{day: [(HH:MM bar start, high, low, close, open, volume shares)]} in Taipei time; empty bars are
    skipped. open / volume are None when Yahoo leaves them out (older cached bars have 4 fields)."""
    try:
        res = payload["chart"]["result"][0]
        stamps = res.get("timestamp") or []
        q = res["indicators"]["quote"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise ParseError("Yahoo chart payload without result") from exc
    out: dict[date, list[tuple]] = {}
    opens = q.get("open") or [None] * len(stamps)
    vols = q.get("volume") or [None] * len(stamps)
    for i, ts in enumerate(stamps):
        h, lo, c = q["high"][i], q["low"][i], q["close"][i]
        if h is None or lo is None or c is None:
            continue
        t = datetime.fromtimestamp(ts, TAIPEI)
        o, v = opens[i], vols[i]
        out.setdefault(t.date(), []).append(
            (t.strftime("%H:%M"), float(h), float(lo), float(c), float(o) if o is not None else None, float(v) if v is not None else None)
        )
    return out


async def fetch_bars(client: httpx.AsyncClient, code: str, market: str, range_: str = "60d") -> dict[date, list]:
    resp = await get_with_retry(client, CHART_URL.format(symbol=symbol_for(code, market), range=range_))
    return parse_chart(resp.json())


async def fetch_day_1m(client: httpx.AsyncClient, code: str, market: str, day: date) -> list:
    """One session's 1-minute bars [(HH:MM, high, low, close)]; empty when Yahoo has none."""
    start = int(datetime.combine(day, time(9, 0), TAIPEI).timestamp())
    end = int(datetime.combine(day, time(13, 31), TAIPEI).timestamp())
    resp = await get_with_retry(client, DAY_1M_URL.format(symbol=symbol_for(code, market), start=start, end=end))
    return parse_chart(resp.json()).get(day, [])


async def fetch_span_1m(client: httpx.AsyncClient, code: str, market: str, first: date, last: date) -> dict[date, list]:
    """1-minute bars for every session from `first` to `last` in one request (Yahoo allows 8 days of
    1m per request); a longer span falls back to one request per day."""
    if (last - first).days > 7:
        out = {}
        d = first
        while d <= last:
            out[d] = await fetch_day_1m(client, code, market, d)
            d = date.fromordinal(d.toordinal() + 1)
        return out
    start = int(datetime.combine(first, time(9, 0), TAIPEI).timestamp())
    end = int(datetime.combine(last, time(13, 31), TAIPEI).timestamp())
    resp = await get_with_retry(client, DAY_1M_URL.format(symbol=symbol_for(code, market), start=start, end=end))
    return parse_chart(resp.json())
