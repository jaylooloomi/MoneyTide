"""HiStock 券商分點買賣日報 (https://histock.tw/stock/branch.aspx?no=CODE&from=YYYYMMDD&to=YYYYMMDD).

One table per page: each row holds a top-seller (券商名稱, 買張, 賣張, 賣超, 均價) on the left and a
top-buyer (券商名稱, 買張, 賣張, 買超, 均價) on the right, 15 of each. from = to = one day. The site's
robots.txt allows /stock/; it is fetched only for the stocks a page opens, slowly (BranchQueue).
"""

from __future__ import annotations

import asyncio
import random
import time as _time
from dataclasses import dataclass
from datetime import date

import httpx
from lxml import html

from ..models import ParseError
from .http import get_with_retry

URL = "https://histock.tw/stock/branch.aspx"


@dataclass(frozen=True, slots=True)
class BranchRow:
    name: str
    buy: float  # 張
    sell: float
    net: float  # 買超 (+) / 賣超 (−)
    avg: float | None  # 均價


def _f(s: str) -> float | None:
    s = (s or "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse_branches(page: str) -> dict:
    """{"buy": [BranchRow…] (largest 買超 first), "sell": [BranchRow…] (largest 賣超 first)}."""
    doc = html.fromstring(page)
    for table in doc.xpath("//table"):
        rows = table.xpath(".//tr")
        if not rows:
            continue
        head = [c.text_content().strip() for c in rows[0].xpath("./th|./td")]
        if head[:1] != ["券商名稱"] or "買超" not in head:
            continue
        buy, sell = [], []
        for tr in rows[1:]:
            c = [x.text_content().strip() for x in tr.xpath("./td")]
            if len(c) < 10:
                continue
            if c[0]:
                sell.append(BranchRow(c[0], _f(c[1]) or 0, _f(c[2]) or 0, _f(c[3]) or 0, _f(c[4])))
            if c[5]:
                buy.append(BranchRow(c[5], _f(c[6]) or 0, _f(c[7]) or 0, _f(c[8]) or 0, _f(c[9])))
        return {"buy": buy, "sell": sell}
    raise ParseError("HiStock branch page: no 券商名稱 table")


class BranchQueue:
    """One HiStock request at a time for the whole app: ≥ min_interval (+ jitter) apart, at most
    daily_cap pages a day, and a long pause after the site refuses (429 / 403)."""

    def __init__(self, client: httpx.AsyncClient, min_interval: float = 5.0, daily_cap: int = 300, pause: float = 1800.0) -> None:
        self._client = client
        self._lock = asyncio.Lock()
        self._min = min_interval
        self._cap = daily_cap
        self._pause = pause
        self._last = 0.0
        self._day = ""
        self._count = 0
        self._blocked_until = 0.0

    def status(self) -> dict:
        return {"today": self._count, "cap": self._cap, "blocked": _time.monotonic() < self._blocked_until}

    async def fetch(self, code: str, day: date) -> dict:
        async with self._lock:
            today = date.today().isoformat()
            if today != self._day:
                self._day, self._count = today, 0
            if _time.monotonic() < self._blocked_until:
                raise RuntimeError("HiStock 暫停中（剛被拒絕過）")
            if self._count >= self._cap:
                raise RuntimeError(f"今天已抓 {self._cap} 頁分點（上限）")
            wait = self._last + self._min + random.uniform(0, 2) - _time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._count += 1
            try:
                r = await get_with_retry(self._client, f"{URL}?no={code}&from={day:%Y%m%d}&to={day:%Y%m%d}", retries=0)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (403, 429):
                    self._blocked_until = _time.monotonic() + self._pause
                raise
            finally:
                self._last = _time.monotonic()
            return parse_branches(r.text)
