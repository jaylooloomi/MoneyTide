"""Concept-stock groups (概念股族群) from Yahoo 股市.

- Index: https://tw.stock.yahoo.com/class lists ~100 links
  `/class-quote?category=<name>&categoryLabel=概念股`.
- Members: JSON API `/_td-stock/api/resource/StockServices.getClassQuotes;categoryName=<name>;
  categoryLabel=概念股;offset=<n>` → `{"list":[{"symbol":"2330.TW",...}], "pagination":
  {"resultsTotal":62,"nextOffset":"30"|null}}`, 30 per page.
Personal local use only, like the HiStock quotes.
"""

from __future__ import annotations

import asyncio
import html as htmllib
import logging
import re
import urllib.parse
from collections.abc import Awaitable, Callable

import httpx

from ..models import ParseError
from .http import get_with_retry

log = logging.getLogger(__name__)

INDEX_URL = "https://tw.stock.yahoo.com/class"
QUOTES_URL = "https://tw.stock.yahoo.com/_td-stock/api/resource/StockServices.getClassQuotes"
CONCEPT_LABEL = "概念股"
REQUEST_DELAY_SECONDS = 1.0
MAX_PAGES_PER_CONCEPT = 20
MIN_CONCEPTS = 30  # the live index has ~100; fewer means the page changed

_LINK = re.compile(r'href="/class-quote\?([^"]+)"')
_SYMBOL = re.compile(r"^(\d{4,6}[A-Z]?)\.(?:TW|TWO)$")


def parse_concept_index(page: str) -> list[str]:
    """Concept names in page order (deduplicated)."""
    names: list[str] = []
    for query in _LINK.findall(page):
        params = urllib.parse.parse_qs(htmllib.unescape(query))
        if params.get("categoryLabel", [""])[0] != CONCEPT_LABEL:
            continue
        name = params.get("category", [""])[0].strip()
        if name and name not in names:
            names.append(name)
    return names


def parse_concept_page(payload: dict) -> tuple[list[str], int | None]:
    """→ (stock codes on this page, next offset or None)."""
    if not isinstance(payload, dict) or not isinstance(payload.get("list"), list):
        raise ParseError("Yahoo class quotes payload has no list")
    codes = []
    for item in payload["list"]:
        m = _SYMBOL.match(str(item.get("symbol", "")) if isinstance(item, dict) else "")
        if m:
            codes.append(m.group(1))
    nxt = (payload.get("pagination") or {}).get("nextOffset")
    return codes, int(nxt) if nxt not in (None, "") else None


def _quotes_url(name: str, offset: int) -> str:
    q = urllib.parse.quote
    return f"{QUOTES_URL};categoryName={q(name)};categoryLabel={q(CONCEPT_LABEL)};offset={offset}"


async def fetch_concepts(
    client: httpx.AsyncClient,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    progress: Callable[[int, int], None] = lambda done, total: None,
) -> dict[str, list[str]]:
    """concept name → member codes (listed + OTC). Concepts that fail are skipped."""
    names = parse_concept_index((await get_with_retry(client, INDEX_URL)).text)
    if len(names) < MIN_CONCEPTS:
        raise ParseError(f"Yahoo concept index looks changed ({len(names)} concepts)")
    out: dict[str, list[str]] = {}
    for i, name in enumerate(names):
        codes: list[str] = []
        offset: int | None = 0
        pages = 0
        try:
            while offset is not None and pages < MAX_PAGES_PER_CONCEPT:
                await sleep(REQUEST_DELAY_SECONDS)
                page_codes, offset = parse_concept_page((await get_with_retry(client, _quotes_url(name, offset))).json())
                codes.extend(c for c in page_codes if c not in codes)
                pages += 1
        except (httpx.HTTPError, ParseError, ValueError) as exc:
            log.warning("concept %s skipped: %s", name, exc)
        if codes:
            out[name] = codes
        progress(i + 1, len(names))
    if len(out) < MIN_CONCEPTS:
        raise ParseError(f"only {len(out)} concepts loaded")
    return out


def code_to_concepts(concepts: dict[str, list[str]]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for name, codes in concepts.items():
        for c in codes:
            out.setdefault(c, []).append(name)
    return out
