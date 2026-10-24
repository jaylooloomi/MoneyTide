"""Daily 融資融券 (margin purchase / short sale) balances per stock, in 張 (lots).

- TWSE MI_MARGN (selectType=ALL): the table titled 融資融券彙總; 融資 前日餘額 = col 5, 今日餘額 =
  col 6; 融券 前日餘額 = col 11, 今日餘額 = col 12. stat != "OK" (holiday, not published yet) → None.
- TPEx margin/balance: tables[0]; 前資餘額 = col 2, 資餘額 = col 6, 前券餘額 = col 10, 券餘額 =
  col 14. An empty table → None.
融資 rising = leveraged (mostly retail) money buying in; 融券 rising = short sellers adding.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date

import httpx

from ..models import ParseError
from .http import get_with_retry
from .official import num

TWSE_URL = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN"
TPEX_URL = "https://www.tpex.org.tw/www/zh-tw/margin/balance"


@dataclass(frozen=True, slots=True)
class MarginRow:
    code: str
    margin_prev: float  # 融資 previous-day balance (張)
    margin_bal: float  # 融資 balance today
    short_prev: float  # 融券 previous-day balance
    short_bal: float  # 融券 balance today


def _n(v) -> float:
    x = num(v)
    return x if x is not None else 0.0


def parse_twse_margin(payload: dict) -> list[MarginRow] | None:
    if payload.get("stat") != "OK":
        return None
    table = next((t for t in payload.get("tables", []) if "彙總" in (t.get("title") or "")), None)
    rows = []
    for r in (table or {}).get("data", []):
        if len(r) < 13:
            raise ParseError(f"MI_MARGN row has {len(r)} columns, expected 16")
        rows.append(MarginRow(str(r[0]).strip(), _n(r[5]), _n(r[6]), _n(r[11]), _n(r[12])))
    return rows or None


def parse_tpex_margin(payload: dict) -> list[MarginRow] | None:
    tables = payload.get("tables") or []
    data = tables[0].get("data", []) if tables else []
    rows = []
    for r in data:
        if len(r) < 15:
            raise ParseError(f"TPEx margin row has {len(r)} columns, expected 20")
        rows.append(MarginRow(str(r[0]).strip(), _n(r[2]), _n(r[6]), _n(r[10]), _n(r[14])))
    return rows or None


async def fetch_margin_day(
    client: httpx.AsyncClient, day: date, sleep: Callable[[float], Awaitable[None]], delay: float
) -> list[MarginRow] | None:
    """Both markets for `day`; None when neither has data (holiday or not published yet)."""
    twse = parse_twse_margin((await get_with_retry(client, f"{TWSE_URL}?date={day:%Y%m%d}&selectType=ALL&response=json")).json())
    await sleep(delay)
    tpex = parse_tpex_margin((await get_with_retry(client, f"{TPEX_URL}?date={day:%Y/%m/%d}&response=json")).json())
    if twse is None and tpex is None:
        return None
    return (twse or []) + (tpex or [])
