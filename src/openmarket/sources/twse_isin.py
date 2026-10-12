"""TWSE ISIN listing (strMode=2 上市, strMode=4 上櫃) → code → StockInfo.

The page is MS950 (= Python cp950) with no meta charset: decode explicitly. Never use 'big5' —
it fails on 碁/恒 and lxml's big5 parser silently truncates the document.
Rows have 7 cells; a 1-cell row is a section header ("股票", "ETF", "特別股", ...), in a different
order per page. Code and name are joined by the first U+3000 (names may contain ASCII spaces).
The listed page is ~9 MB (mostly warrants) and can take ~50 s: httpx's 15 s timeout is per read.
"""

from __future__ import annotations

import asyncio

import httpx
from lxml import html

from ..models import Kind, Market, ParseError, StockInfo
from .http import get_with_retry

TWSE_URL = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
TPEX_URL = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"

STOCK_SECTIONS = {"股票", "創新板", "臺灣創新板"}
ETF_SECTION = "ETF"
SKIP_SECTIONS_PREFIX = ("上市認購(售)權證", "上櫃認購(售)權證")  # tens of thousands of rows, never quoted
HEADER_FIRST_CELL = "有價證券代號及名稱"


def _decode(page: bytes | str) -> str:
    if isinstance(page, str):
        return page
    return page.decode("cp950", errors="replace")


def _market(text: str) -> Market:
    if text.startswith("上市"):
        return "上市"
    if text.startswith("上櫃"):
        return "上櫃"
    return "未知"


def _kind(section: str, cfi: str) -> Kind:
    # ETN (CMXXXU), TDR (EDSDDR), REIT/ABS, 特別股 → "other" (kept out of the heatmap).
    if cfi.startswith("CE") or section == ETF_SECTION:
        return "etf"
    if section in STOCK_SECTIONS:
        return "stock"
    return "other"


def parse_isin(page: bytes | str) -> dict[str, StockInfo]:
    try:
        doc = html.fromstring(_decode(page))
    except Exception as exc:
        raise ParseError(f"ISIN page is not valid HTML: {exc}") from exc

    out: dict[str, StockInfo] = {}
    section = ""
    saw_header = False
    for tr in doc.iter("tr"):
        cells = [c.text_content().strip() for c in tr.xpath("./td|./th")]
        if not cells:
            continue
        if cells[0] == HEADER_FIRST_CELL:
            if len(cells) < 6 or cells[4] != "產業別" or cells[5] != "CFICode":
                raise ParseError(f"ISIN header changed: {cells}")
            saw_header = True
            continue
        if len(cells) == 1:
            section = cells[0]
            continue
        if not saw_header or len(cells) < 6 or section.startswith(SKIP_SECTIONS_PREFIX):
            continue
        code, _, name = cells[0].partition("　")
        code, name = code.strip(), name.strip()
        if not code:
            continue
        out[code] = StockInfo(
            code=code,
            name=name,
            industry=cells[4],
            market=_market(cells[3]),
            kind=_kind(section, cells[5]),
        )
    if not saw_header:
        raise ParseError("ISIN table header not found")
    if not out:
        raise ParseError("ISIN table contained no rows")
    return out


async def fetch_isin(client: httpx.AsyncClient) -> dict[str, StockInfo]:
    twse = await get_with_retry(client, TWSE_URL)
    tpex = await get_with_retry(client, TPEX_URL)
    listed = await asyncio.to_thread(parse_isin, twse.content)
    otc = await asyncio.to_thread(parse_isin, tpex.content)
    return {**listed, **otc}
