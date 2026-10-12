"""HiStock rank page (https://histock.tw/stock/rank.aspx?p=all) → list[Quote].

Columns are located by header text, not position. Notes from the live page:
- headers carry a sort arrow ("代號▼"), stripped before matching;
- 漲跌 looks like "▲210.00" / "▼-35.00"; 漲跌幅 "+1.20%";
- a flat stock shows "--" in 漲跌 and 漲跌幅 (price == 昨收), so we derive 0 from price/昨收;
- 成交量 uses thousands separators ("1,691").
"""

from __future__ import annotations

import asyncio
import re

import httpx
from lxml import html

from ..models import ParseError, Quote
from .http import get_with_retry

URL = "https://histock.tw/stock/rank.aspx?p=all"  # p=all is required (otherwise 50 rows/page)
MIN_LIVE_ROWS = 1000  # a live page has ~2,500 rows; fewer means a broken/partial page
TABLE_ID = "CPHB1_gv"

COLUMNS = {
    "代號": "code",
    "名稱": "name",
    "價格": "price",
    "漲跌": "change",
    "漲跌幅": "change_pct",
    "周漲跌": "week_pct",
    "振幅": "amplitude_pct",
    "開盤": "open",
    "最高": "high",
    "最低": "low",
    "昨收": "prev_close",
    "成交量": "volume_lots",
    "成交值(億)": "turnover_100m",
}

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _header_key(text: str) -> str:
    return re.sub(r"[\s▼▲]", "", text)


def parse_number(text: str) -> float | None:
    """'▲210.00' → 210.0, '▼-35.00' → -35.0, '+1.20%' → 1.2, '1,691' → 1691.0, '--' → None."""
    cleaned = text.replace(",", "").replace("%", "").replace("▲", "").replace("▼", "").replace("+", "").strip()
    if not cleaned or not _NUM_RE.fullmatch(cleaned):
        return None
    return float(cleaned)


def parse_rank(page: bytes | str) -> list[Quote]:
    try:
        doc = html.fromstring(page)
    except Exception as exc:  # lxml raises several types on garbage input
        raise ParseError(f"HiStock page is not valid HTML: {exc}") from exc
    tables = doc.xpath(f"//table[@id='{TABLE_ID}']")
    if not tables:
        raise ParseError(f"HiStock table #{TABLE_ID} not found")
    rows = tables[0].xpath("./tr|./tbody/tr")
    if not rows:
        raise ParseError("HiStock table has no rows")

    headers = [_header_key(th.text_content()) for th in rows[0].xpath("./th|./td")]
    index = {COLUMNS[h]: i for i, h in enumerate(headers) if h in COLUMNS}
    missing = [h for h, field in COLUMNS.items() if field not in index]
    if missing:
        raise ParseError(f"HiStock header missing columns: {', '.join(missing)}")

    quotes: list[Quote] = []
    for row in rows[1:]:
        cells = [td.text_content().strip() for td in row.xpath("./td")]
        if len(cells) < len(headers):
            continue
        code = cells[index["code"]]
        if not code:
            continue
        values = {f: parse_number(cells[i]) for f, i in index.items() if f not in ("code", "name")}
        price, prev = values["price"], values["prev_close"]
        if values["change"] is None and cells[index["change"]] == "--" and price is not None and prev:
            values["change"] = round(price - prev, 4)
        if values["change_pct"] is None and cells[index["change_pct"]] == "--" and values["change"] is not None and prev:
            values["change_pct"] = round(values["change"] / prev * 100, 4)
        quotes.append(Quote(code=code, name=cells[index["name"]], **values))
    if not quotes:
        raise ParseError("HiStock table contained no data rows")
    return quotes


async def fetch_quotes(client: httpx.AsyncClient) -> list[Quote]:
    resp = await get_with_retry(client, URL)
    quotes = await asyncio.to_thread(parse_rank, resp.content)
    if len(quotes) < MIN_LIVE_ROWS:
        raise ParseError(f"HiStock returned only {len(quotes)} rows (expected > {MIN_LIVE_ROWS})")
    return quotes
