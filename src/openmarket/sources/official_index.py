"""Official monthly index history: TAIEX (TWSE) and the TPEx index, with each market's turnover.

Endpoints (one request per month each, checked 2026-10-23):
- TWSE MI_5MINS_HIST: 日期 (ROC "115/09/01"), 開盤指數, 最高指數, 最低指數, 收盤指數
- TWSE FMTQIK:        日期 (ROC), 成交股數, 成交金額 (元), 成交筆數, 發行量加權股價指數, 漲跌點數
- TPEx inx:           tables[0] 日期 (AD "2026/09/01"), 開市, 最高, 最低, 收市, 漲/跌
- TPEx tradingIndex:  tables[0] 日期 (ROC), 成交股數 (千股), 金額 (千元), 筆數, 櫃買指數, 漲/跌
Values are thousands-separated strings (TPEx index columns may be numbers). Parsing is
positional because the column titles differ between endpoints; row lengths are checked.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date

import httpx

from ..models import Market, ParseError
from .http import get_with_retry
from .official import num

TWSE_OHLC_URL = "https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST"
TWSE_TURNOVER_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK"
TPEX_OHLC_URL = "https://www.tpex.org.tw/www/zh-tw/indexInfo/inx"
TPEX_TURNOVER_URL = "https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingIndex"


@dataclass(frozen=True, slots=True)
class IndexRow:
    date: date
    market: Market
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    change: float | None
    turnover_yuan: float | None


def parse_date(text: object) -> date:
    """'115/09/01' (ROC) or '2026/09/01' (AD)."""
    parts = str(text).strip().split("/")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ParseError(f"bad index date {text!r}")
    y, m, d = (int(p) for p in parts)
    return date(y + 1911 if y < 1911 else y, m, d)


def _rows(payload: dict, width: int, source: str) -> list[list]:
    """Data rows of a TWSE (top-level) or TPEx (tables[0]) payload; [] for an empty month."""
    stat = str(payload.get("stat", "ok")).lower()
    if "tables" in payload:
        tables = payload.get("tables") or []
        data = tables[0].get("data", []) if tables else []
    else:
        if stat != "ok":
            return []  # "很抱歉，沒有符合條件的資料!" for months without data
        data = payload.get("data", [])
    for r in data:
        if len(r) < width:
            raise ParseError(f"{source}: row has {len(r)} columns, expected {width}")
    return data


def parse_twse_ohlc(payload: dict) -> dict[date, tuple]:
    return {parse_date(r[0]): (num(r[1]), num(r[2]), num(r[3]), num(r[4])) for r in _rows(payload, 5, "MI_5MINS_HIST")}


def parse_twse_turnover(payload: dict) -> dict[date, tuple]:
    """{day: (turnover 元, change points)}"""
    return {parse_date(r[0]): (num(r[2]), num(r[5])) for r in _rows(payload, 6, "FMTQIK")}


def parse_tpex_ohlc(payload: dict) -> dict[date, tuple]:
    """{day: (open, high, low, close, change)}"""
    return {
        parse_date(r[0]): (num(r[1]), num(r[2]), num(r[3]), num(r[4]), num(r[5]))
        for r in _rows(payload, 6, "TPEx inx")
    }


def parse_tpex_turnover(payload: dict) -> dict[date, tuple]:
    """{day: (turnover 元, change points)} — the source reports thousands of 元."""
    out = {}
    for r in _rows(payload, 6, "TPEx tradingIndex"):
        amount = num(r[2])
        out[parse_date(r[0])] = (amount * 1000 if amount is not None else None, num(r[5]))
    return out


def merge_twse(ohlc: dict[date, tuple], turnover: dict[date, tuple]) -> list[IndexRow]:
    days = sorted(set(ohlc) | set(turnover))
    rows = []
    for d in days:
        o, h, lo, c = ohlc.get(d, (None, None, None, None))
        amount, change = turnover.get(d, (None, None))
        rows.append(IndexRow(d, "上市", o, h, lo, c, change, amount))
    return rows


def merge_tpex(ohlc: dict[date, tuple], turnover: dict[date, tuple]) -> list[IndexRow]:
    days = sorted(set(ohlc) | set(turnover))
    rows = []
    for d in days:
        o, h, lo, c, change = ohlc.get(d, (None, None, None, None, None))
        amount, change2 = turnover.get(d, (None, None))
        rows.append(IndexRow(d, "上櫃", o, h, lo, c, change if change is not None else change2, amount))
    return rows


async def fetch_index_month(
    client: httpx.AsyncClient,
    market: Market,
    month: date,
    sleep: Callable[[float], Awaitable[None]],
    delay: float,
) -> list[IndexRow]:
    """Both requests for one market and month (`month` is any day in it), `delay` apart."""
    first = month.replace(day=1)
    if market == "上市":
        a = (await get_with_retry(client, f"{TWSE_OHLC_URL}?date={first:%Y%m%d}&response=json")).json()
        await sleep(delay)
        b = (await get_with_retry(client, f"{TWSE_TURNOVER_URL}?date={first:%Y%m%d}&response=json")).json()
        return merge_twse(parse_twse_ohlc(a), parse_twse_turnover(b))
    a = (await get_with_retry(client, f"{TPEX_OHLC_URL}?date={first:%Y/%m/%d}&response=json")).json()
    await sleep(delay)
    b = (await get_with_retry(client, f"{TPEX_TURNOVER_URL}?date={first:%Y/%m/%d}&response=json")).json()
    return merge_tpex(parse_tpex_ohlc(a), parse_tpex_turnover(b))
