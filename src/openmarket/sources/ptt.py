"""PTT 股版 (https://www.ptt.cc/bbs/Stock/) article titles, newest pages first.

- Each index page lists ~20 posts as `<div class="title"><a href="/bbs/Stock/M.<epoch>.A.xxx.html">title</a>`;
  deleted posts have no link. On the newest page, pinned posts follow `<div class="r-list-sep">`.
- The post time is the epoch in the file name, so dates are exact (no year guessing from "M/DD").
- "‹ 上頁" links to the previous (older) page. Public board pages; fetched with a pause between pages.
"""

from __future__ import annotations

import html as htmllib
import re
from collections.abc import Awaitable, Callable
from datetime import date, datetime

import httpx

from ..config import TAIPEI
from .http import get_with_retry

BASE = "https://www.ptt.cc"
INDEX = "/bbs/Stock/index.html"
PAGE_DELAY_SECONDS = 2.0
MAX_PAGES = 400

_POST = re.compile(r'<div class="title">\s*<a href="(/bbs/Stock/M\.(\d+)\.A\.[0-9A-F]+\.html)">(.*?)</a>', re.S)
_PREV = re.compile(r'href="(/bbs/Stock/index\d+\.html)">&lsaquo; 上頁')
_TAG = re.compile(r"^\s*(Re:\s*|Fw:\s*)*\[[^\]]{1,4}\]\s*")


def clean_title(raw: str) -> str:
    """Plain text without the reply prefix and the [新聞]/[標的] tag."""
    return _TAG.sub("", htmllib.unescape(raw)).strip()


def parse_index(page: str) -> tuple[list[tuple[date, str]], str | None]:
    """([(post date, title)], link to the previous page)."""
    body = page.split('<div class="r-list-sep">')[0]  # pinned posts below the separator
    posts = []
    for _href, epoch, title in _POST.findall(body):
        when = datetime.fromtimestamp(int(epoch), TAIPEI).date()
        text = clean_title(title)
        if text:
            posts.append((when, text))
    prev = _PREV.search(page)
    return posts, prev.group(1) if prev else None


async def fetch_titles_since(
    client: httpx.AsyncClient,
    since: date,
    sleep: Callable[[float], Awaitable[None]],
    delay: float = PAGE_DELAY_SECONDS,
    max_pages: int = MAX_PAGES,
) -> dict[date, list[str]]:
    """Titles per day from the newest page back to `since` (inclusive)."""
    out: dict[date, list[str]] = {}
    path: str | None = INDEX
    for i in range(max_pages):
        if path is None:
            break
        if i:
            await sleep(delay)
        resp = await get_with_retry(client, BASE + path)
        posts, path = parse_index(resp.text)
        for d, title in posts:
            if d >= since:
                out.setdefault(d, []).append(title)
        if posts and max(d for d, _ in posts) < since:
            break
    return out


def make_ptt_client() -> httpx.AsyncClient:
    """PTT asks for an over-18 confirmation on some boards; the cookie skips it."""
    from ..config import HTTP_TIMEOUT_SECONDS, USER_AGENT

    return httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT}, cookies={"over18": "1"}, follow_redirects=True)
