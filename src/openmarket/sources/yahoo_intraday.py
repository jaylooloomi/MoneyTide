"""5-minute bars from Yahoo Finance's chart API (unofficial; used only to backfill a group's top members
for days the app did not record itself).

https://query1.finance.yahoo.com/v8/finance/chart/<code>.TW (上市) or .TWO (上櫃)?interval=5m&range=60d
→ chart.result[0]: timestamp[] (epoch, bar start), indicators.quote[0]: open/high/low/close/volume
(null for empty bars). About 54 bars per session (09:00–13:25 starts) and up to 60 days back.
"""

from __future__ import annotations

from datetime import date, datetime

import httpx

from ..config import TAIPEI
from ..models import ParseError
from .http import get_with_retry

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=5m&range={range}"


def symbol_for(code: str, market: str) -> str:
    return f"{code}.{'TWO' if market == '上櫃' else 'TW'}"


def parse_chart(payload: dict) -> dict[date, list[tuple[str, float, float, float]]]:
    """{day: [(HH:MM bar start, high, low, close)]} in Taipei time; empty bars are skipped."""
    try:
        res = payload["chart"]["result"][0]
        stamps = res.get("timestamp") or []
        q = res["indicators"]["quote"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise ParseError("Yahoo chart payload without result") from exc
    out: dict[date, list[tuple[str, float, float, float]]] = {}
    for i, ts in enumerate(stamps):
        h, lo, c = q["high"][i], q["low"][i], q["close"][i]
        if h is None or lo is None or c is None:
            continue
        t = datetime.fromtimestamp(ts, TAIPEI)
        out.setdefault(t.date(), []).append((t.strftime("%H:%M"), float(h), float(lo), float(c)))
    return out


async def fetch_bars(client: httpx.AsyncClient, code: str, market: str, range_: str = "60d") -> dict[date, list]:
    resp = await get_with_retry(client, CHART_URL.format(symbol=symbol_for(code, market), range=range_))
    return parse_chart(resp.json())
