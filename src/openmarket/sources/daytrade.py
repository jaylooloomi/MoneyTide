"""當日沖銷 (day-trading) volume per stock: TWSE TWTB4U (selectType=All) and TPEx 現股當沖交易統計.

TWSE: the table 當日沖銷交易標的及成交量值, 證券代號 (col 0), 當日沖銷交易成交股數 (col 3); stat != "OK"
(holiday, not published yet) → None. TPEx (intraday_trading_stat_result.php): table 0 is the market
total, table 1 one row per stock with 當日沖銷交易成交股數 (col 3); no rows → None.
當沖比 = these shares ÷ the day's traded shares.
"""

from __future__ import annotations

from datetime import date

import httpx

from ..models import ParseError
from .http import get_with_retry
from .official import num

URL = "https://www.twse.com.tw/rwd/zh/dayTrading/TWTB4U"
TPEX_URL = "https://www.tpex.org.tw/web/stock/trading/intraday_stat/intraday_trading_stat_result.php"


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


def parse_tpex_daytrade(payload: dict) -> dict[str, float] | None:
    """{code: 當沖成交股數} from TPEx's per-stock table; None when the day has none."""
    out = {}
    for t in payload.get("tables") or []:
        fields = [str(f).strip() for f in t.get("fields") or []]
        if "證券代號" not in fields or "當日沖銷交易成交股數" not in fields:
            continue
        i_code, i_sh = fields.index("證券代號"), fields.index("當日沖銷交易成交股數")
        for r in t.get("data") or []:
            if len(r) > max(i_code, i_sh) and (shares := num(r[i_sh])) is not None:
                out[str(r[i_code]).strip()] = shares
    return out or None


async def fetch_tpex_daytrade_day(client: httpx.AsyncClient, day: date) -> dict[str, float] | None:
    roc = f"{day.year - 1911}/{day.month:02d}/{day.day:02d}"
    resp = await get_with_retry(client, f"{TPEX_URL}?l=zh-tw&d={roc}")
    try:
        return parse_tpex_daytrade(resp.json())
    except ValueError as exc:
        raise ParseError("TPEx 當沖 did not return JSON") from exc
