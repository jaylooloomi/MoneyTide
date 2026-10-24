"""TWSE 類股指數 for one day (MI_INDEX type=IND): the 電子／金融／傳產 benchmarks of C.

From the table 價格指數(臺灣證券交易所): 電子工業類指數, 金融保險類指數 and 未含金融電子指數 (taken as
傳產), each with 收盤指數 (col 1), 漲跌 sign (col 2, an HTML snippet holding + or -) and 漲跌點數 (col 3).
stat != "OK" (holiday, not published yet) → None. 上市 only: TPEx has no matching set.
"""

from __future__ import annotations

from datetime import date

import httpx

from ..models import ParseError
from .http import get_with_retry
from .official import num

URL = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
# C's row name → the official index name
SECTORS = {"電子": "電子工業類指數", "金融": "金融保險類指數", "傳產": "未含金融電子指數"}


def parse_sector_indices(payload: dict) -> dict[str, tuple[float, float]] | None:
    """{電子|金融|傳產: (close, change in points)}; None when the day is not published."""
    if payload.get("stat") != "OK":
        return None
    wanted = {v: k for k, v in SECTORS.items()}
    out: dict[str, tuple[float, float]] = {}
    for t in payload.get("tables", []):
        if "臺灣證券交易所" not in (t.get("title") or ""):
            continue
        for r in t.get("data", []):
            name = str(r[0]).strip() if r else ""
            if name not in wanted:
                continue
            if len(r) < 4:
                raise ParseError(f"MI_INDEX row has {len(r)} columns, expected 6")
            close, points = num(r[1]), num(r[3])
            if close is None or points is None:
                continue
            sign = -1 if "-" in str(r[2]) else 1
            out[wanted[name]] = (close, sign * points)
    return out or None


async def fetch_sector_day(client: httpx.AsyncClient, day: date) -> dict[str, tuple[float, float]] | None:
    return parse_sector_indices((await get_with_retry(client, f"{URL}?date={day:%Y%m%d}&type=IND&response=json")).json())
