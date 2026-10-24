"""當日沖銷 (day-trading) volume per listed stock: TWSE TWTB4U (selectType=All).

The table 當日沖銷交易標的及成交量值: 證券代號 (col 0), 當日沖銷交易成交股數 (col 3). stat != "OK" (holiday,
not published yet) → None. TPEx publishes no per-stock figure (only the market total), so 上櫃 stocks
have none. 當沖比 = these shares ÷ the day's traded shares.
"""

from __future__ import annotations

from datetime import date

import httpx

from ..models import ParseError
from .http import get_with_retry
from .official import num

URL = "https://www.twse.com.tw/rwd/zh/dayTrading/TWTB4U"


def parse_daytrade(payload: dict) -> dict[str, float] | None:
    """{code: 當沖成交股數}; None when the day is not published."""
    if payload.get("stat") != "OK":
        return None
    table = next((t for t in payload.get("tables", []) if "標的" in (t.get("title") or "")), None)
    out = {}
    for r in (table or {}).get("data", []):
        if len(r) < 4:
            raise ParseError(f"TWTB4U row has {len(r)} columns, expected 6")
        shares = num(r[3])
        if shares is not None:
            out[str(r[0]).strip()] = shares
    return out or None


async def fetch_daytrade_day(client: httpx.AsyncClient, day: date) -> dict[str, float] | None:
    return parse_daytrade((await get_with_retry(client, f"{URL}?date={day:%Y%m%d}&selectType=All&response=json")).json())
