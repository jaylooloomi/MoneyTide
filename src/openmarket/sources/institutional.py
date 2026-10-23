"""Daily net buy/sell by the three institutional investor groups (三大法人), in shares.

- TWSE T86 (ALLBUT0999): 外陸資(不含外資自營商) net = col 4, 外資自營商 net = col 7, 投信 net = col 10,
  自營商 net = col 11, 三大法人 net = col 18. stat != "OK" (holiday, not published yet) → None.
- TPEx dailyTrade (sect=EW): tables[0] with 外資合計 net = col 10, 投信 net = col 13, 自營商合計 net
  = col 22, 三大法人合計 = col 23. An empty table → None.
Amounts are derived later from the day's close (shares × close).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date

import httpx

from ..models import ParseError
from .http import get_with_retry
from .official import num

TWSE_URL = "https://www.twse.com.tw/rwd/zh/fund/T86"
TPEX_URL = "https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade"


@dataclass(frozen=True, slots=True)
class InstRow:
    code: str
    foreign: float
    trust: float
    dealer: float
    total: float


def _n(v) -> float:
    x = num(v)
    return x if x is not None else 0.0


def parse_twse_inst(payload: dict) -> list[InstRow] | None:
    if payload.get("stat") != "OK":
        return None
    rows = []
    for r in payload.get("data", []):
        if len(r) < 19:
            raise ParseError(f"T86 row has {len(r)} columns, expected 19")
        rows.append(InstRow(str(r[0]).strip(), _n(r[4]) + _n(r[7]), _n(r[10]), _n(r[11]), _n(r[18])))
    return rows or None


def parse_tpex_inst(payload: dict) -> list[InstRow] | None:
    tables = payload.get("tables") or []
    data = tables[0].get("data", []) if tables else []
    rows = []
    for r in data:
        if len(r) < 24:
            raise ParseError(f"TPEx dailyTrade row has {len(r)} columns, expected 24")
        rows.append(InstRow(str(r[0]).strip(), _n(r[10]), _n(r[13]), _n(r[22]), _n(r[23])))
    return rows or None


async def fetch_inst_day(
    client: httpx.AsyncClient, day: date, sleep: Callable[[float], Awaitable[None]], delay: float
) -> list[InstRow] | None:
    """Both markets for `day`; None when neither has data (holiday or not published yet)."""
    twse = parse_twse_inst((await get_with_retry(client, f"{TWSE_URL}?date={day:%Y%m%d}&selectType=ALLBUT0999&response=json")).json())
    await sleep(delay)
    tpex = parse_tpex_inst((await get_with_retry(client, f"{TPEX_URL}?type=Daily&sect=EW&date={day:%Y/%m/%d}&response=json")).json())
    if twse is None and tpex is None:
        return None
    return (twse or []) + (tpex or [])
