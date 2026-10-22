"""Official after-close daily quotes (TWSE MI_INDEX, TPEx otc) — the source for history.

Notes from the live endpoints:
- TWSE 漲跌(+/-) is HTML ("<p style= color:green>-</p>"), values '+', '-', ' ' (flat) or 'X'
  (ex-rights: the price difference is not against yesterday's close → change unknown).
- TPEx 漲跌 is signed text ("+0.19", "-1.20", "0.00"), or "除息"/"除權"/"---" (unknown).
- No trade: TWSE close "--", TPEx close "----".
- Non-trading day: TWSE stat "很抱歉，沒有符合條件的資料!"; TPEx returns an empty table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

from ..models import Market, ParseError
from .http import get_with_retry

TWSE_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
TPEX_URL = "https://www.tpex.org.tw/www/zh-tw/afterTrading/otc"
TWSE_TABLE = "每日收盤行情"
TPEX_TABLE = "上櫃股票每日收盤行情"


@dataclass(frozen=True, slots=True)
class DailyRow:
    code: str
    name: str
    market: Market
    close: float | None
    change: float | None
    open: float | None
    high: float | None
    low: float | None
    volume_shares: float | None
    turnover_yuan: float | None
    shares: int | None = None  # issued shares (TPEx only)


_NUM = re.compile(r"^-?\d+(?:\.\d+)?$")


def num(text: Any) -> float | None:
    s = re.sub(r"<[^>]+>", "", str(text)).replace(",", "").replace("+", "").strip()
    return float(s) if _NUM.match(s) else None


def _fields(table: dict) -> dict[str, int]:
    return {re.sub(r"<[^>]+>|\s", "", f): i for i, f in enumerate(table.get("fields", []))}


def _need(idx: dict[str, int], names: list[str], source: str) -> list[int]:
    missing = [n for n in names if n not in idx]
    if missing:
        raise ParseError(f"{source} fields missing: {', '.join(missing)}")
    return [idx[n] for n in names]


def parse_twse_day(payload: dict) -> list[DailyRow] | None:
    """None when the day has no data (holiday)."""
    if payload.get("stat") != "OK":
        if "沒有符合條件" in str(payload.get("stat", "")):
            return None
        raise ParseError(f"TWSE stat: {payload.get('stat')}")
    tables = [t for t in payload.get("tables", []) if TWSE_TABLE in t.get("title", "")]
    if not tables:
        return None
    t = tables[0]
    i_code, i_name, i_vol, i_amt, i_open, i_high, i_low, i_close, i_sign, i_diff = _need(
        _fields(t),
        ["證券代號", "證券名稱", "成交股數", "成交金額", "開盤價", "最高價", "最低價", "收盤價", "漲跌(+/-)", "漲跌價差"],
        "TWSE",
    )
    rows = []
    for r in t.get("data", []):
        sign = re.sub(r"<[^>]+>", "", str(r[i_sign])).strip()
        diff = num(r[i_diff])
        if sign == "X" or diff is None:
            change = None
        else:
            change = -diff if sign == "-" else (diff if sign == "+" else 0.0)
        close = num(r[i_close])
        rows.append(DailyRow(
            code=str(r[i_code]).strip(), name=str(r[i_name]).strip(), market="上市",
            close=close, change=change if close is not None else None,
            open=num(r[i_open]), high=num(r[i_high]), low=num(r[i_low]),
            volume_shares=num(r[i_vol]), turnover_yuan=num(r[i_amt]),
        ))
    return rows


def parse_tpex_day(payload: dict) -> list[DailyRow] | None:
    tables = [t for t in payload.get("tables", []) if TPEX_TABLE in t.get("title", "")]
    if not tables:
        raise ParseError("TPEx daily table not found")
    t = tables[0]
    if not t.get("data"):
        return None
    i_code, i_name, i_close, i_chg, i_open, i_high, i_low, i_vol, i_amt, i_shares = _need(
        _fields(t),
        ["代號", "名稱", "收盤", "漲跌", "開盤", "最高", "最低", "成交股數", "成交金額(元)", "發行股數"],
        "TPEx",
    )
    rows = []
    for r in t["data"]:
        close = num(r[i_close])
        shares = num(r[i_shares])
        rows.append(DailyRow(
            code=str(r[i_code]).strip(), name=str(r[i_name]).strip(), market="上櫃",
            close=close, change=num(r[i_chg]) if close is not None else None,
            open=num(r[i_open]), high=num(r[i_high]), low=num(r[i_low]),
            volume_shares=num(r[i_vol]), turnover_yuan=num(r[i_amt]),
            shares=int(shares) if shares else None,
        ))
    return rows


async def fetch_twse_day(client: httpx.AsyncClient, day: date) -> list[DailyRow] | None:
    resp = await get_with_retry(client, f"{TWSE_URL}?date={day:%Y%m%d}&type=ALLBUT0999&response=json")
    return parse_twse_day(resp.json())


async def fetch_tpex_day(client: httpx.AsyncClient, day: date) -> list[DailyRow] | None:
    resp = await get_with_retry(client, f"{TPEX_URL}?date={day:%Y/%m/%d}&type=EW&response=json")
    return parse_tpex_day(resp.json())
