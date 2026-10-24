"""除權息參考價 (TWSE TWT49U, TPEx exDailyQ) for a date range: the 昨收 of an ex-rights day.

On an ex-rights / ex-dividend day TWSE marks 漲跌 'X' and TPEx writes 除息／除權, so the day row has no
change; the official change of that day is against the 除權息參考價, which these tables give. One
request covers a whole month on either site.
"""

from __future__ import annotations

import re
from datetime import date

import httpx

from ..models import ParseError
from .http import get_with_retry
from .official import num

TWSE_URL = "https://www.twse.com.tw/rwd/zh/exRight/TWT49U"
TPEX_URL = "https://www.tpex.org.tw/web/stock/exright/dailyquo/exDailyQ_result.php"


def roc_date(text: str) -> date | None:
    """'115年08月03日' / '115/08/03' → 2026-08-03."""
    m = re.match(r"\s*(\d{2,3})\D(\d{1,2})\D(\d{1,2})", str(text))
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    try:
        return date(y + 1911, mo, d)
    except ValueError:
        return None


def parse_refs(rows: list, i_date: int, i_code: int, i_ref: int) -> dict[date, dict[str, float]]:
    out: dict[date, dict[str, float]] = {}
    for r in rows:
        if len(r) <= max(i_date, i_code, i_ref):
            continue
        d, ref = roc_date(r[i_date]), num(r[i_ref])
        if d is not None and ref:
            out.setdefault(d, {})[str(r[i_code]).strip()] = ref
    return out


def parse_twse_exright(payload: dict) -> dict[date, dict[str, float]]:
    """{day: {code: 除權息參考價}}; an empty range (stat not OK) → {}."""
    if payload.get("stat") != "OK":
        return {}
    fields = [str(f).strip() for f in payload.get("fields") or []]
    try:
        return parse_refs(payload.get("data") or [], fields.index("資料日期"), fields.index("股票代號"), fields.index("除權息參考價"))
    except ValueError as exc:
        raise ParseError(f"TWT49U fields changed: {fields[:6]!r}") from exc


def parse_tpex_exright(payload: dict) -> dict[date, dict[str, float]]:
    out: dict[date, dict[str, float]] = {}
    for t in payload.get("tables") or []:
        fields = [str(f).strip() for f in t.get("fields") or []]
        try:
            got = parse_refs(t.get("data") or [], fields.index("除權息日期"), fields.index("代號"), fields.index("除權息參考價"))
        except ValueError as exc:
            raise ParseError(f"exDailyQ fields changed: {fields[:6]!r}") from exc
        for d, refs in got.items():
            out.setdefault(d, {}).update(refs)
    return out


async def fetch_twse_exright(client: httpx.AsyncClient, start: date, end: date) -> dict[date, dict[str, float]]:
    return parse_twse_exright((await get_with_retry(client, f"{TWSE_URL}?startDate={start:%Y%m%d}&endDate={end:%Y%m%d}&response=json")).json())


async def fetch_tpex_exright(client: httpx.AsyncClient, start: date, end: date) -> dict[date, dict[str, float]]:
    roc = lambda d: f"{d.year - 1911}/{d.month:02d}/{d.day:02d}"  # noqa: E731
    return parse_tpex_exright((await get_with_retry(client, f"{TPEX_URL}?l=zh-tw&d={roc(start)}&ed={roc(end)}")).json())
