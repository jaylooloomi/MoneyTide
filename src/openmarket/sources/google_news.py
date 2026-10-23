"""Headlines for one stock around one day, from the Google News RSS search.

https://news.google.com/rss/search?q=<query>&hl=zh-TW&gl=TW&ceid=TW:zh-Hant with the query
`"<name>" <code> after:<day-2> before:<day+3>`; items carry <title> ("headline - source"), <link>,
<pubDate> (RFC 822) and <source>. Only titles, sources and links are kept (no article bodies).
"""

from __future__ import annotations

import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime

import httpx

from ..config import TAIPEI
from .http import get_with_retry

RSS_URL = "https://news.google.com/rss/search"
WINDOW_DAYS = 2  # news within ±2 days of the trading day
MAX_ITEMS = 8


@dataclass(frozen=True, slots=True)
class Headline:
    title: str
    source: str
    url: str
    published: datetime | None

    def to_dict(self) -> dict:
        return {"title": self.title, "source": self.source, "url": self.url,
                "published": self.published.isoformat() if self.published else None}


def news_url(name: str, code: str, day: date) -> str:
    q = f'"{name}" {code} after:{day - timedelta(days=WINDOW_DAYS):%Y-%m-%d} before:{day + timedelta(days=WINDOW_DAYS + 1):%Y-%m-%d}'
    return f"{RSS_URL}?{urllib.parse.urlencode({'q': q, 'hl': 'zh-TW', 'gl': 'TW', 'ceid': 'TW:zh-Hant'})}"


def parse_rss(xml_text: str, day: date, limit: int = MAX_ITEMS) -> list[Headline]:
    """Items published within ±WINDOW_DAYS of `day` (Taipei), newest first, deduplicated by title."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    lo, hi = day - timedelta(days=WINDOW_DAYS), day + timedelta(days=WINDOW_DAYS)
    out: list[Headline] = []
    seen: set[str] = set()
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        source = (item.findtext("source") or "").strip()
        url = (item.findtext("link") or "").strip()
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3].strip()
        try:
            published = parsedate_to_datetime(item.findtext("pubDate") or "").astimezone(TAIPEI)
        except (TypeError, ValueError):
            published = None
        if published is not None and not (lo <= published.date() <= hi):
            continue
        if not title or not url.startswith("http") or title in seen:
            continue
        seen.add(title)
        out.append(Headline(title, source, url, published))
    out.sort(key=lambda h: h.published or datetime.min.replace(tzinfo=TAIPEI), reverse=True)
    return out[:limit]


async def fetch_headlines(client: httpx.AsyncClient, name: str, code: str, day: date) -> list[Headline]:
    resp = await get_with_retry(client, news_url(name, code, day))
    return parse_rss(resp.text, day)
