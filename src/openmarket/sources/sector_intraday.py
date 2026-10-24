"""TWSE 每 5 秒指數統計 (MI_5MINS_INDEX) for one day: the 類股指數 on N's 5-minute axis.

One request a day gives every 上市 類股指數 (水泥類指數 … 其他類指數, plus 加權 and the 未含 sets) every 5
seconds from 09:00:00 to 13:30:00. A stock's 5-minute bucket i (09:00 + 5i … +5) closes at 09:00 + 5(i+1),
so the index close of bucket i is the last value at or before that second; the 09:00:00 row is the
previous close / open and belongs to no bucket. stat != "OK" (holiday, not published yet) → None.
上市 only: TPEx publishes no per-industry intraday index.
"""

from __future__ import annotations

from datetime import date

import httpx

from ..models import ParseError
from .http import get_with_retry
from .official import num

URL = "https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_INDEX"
BUCKETS = 54  # 09:00–13:30 in 5-minute buckets (finder.BUCKETS)


def parse_sector_intraday(payload: dict) -> dict[str, list[float | None]] | None:
    """{index name: [close of bucket 0 … 53]} (None where no value came); None when the day is not published."""
    if payload.get("stat") != "OK":
        return None
    fields = payload.get("fields") or []
    if not fields or fields[0] != "時間":
        raise ParseError(f"MI_5MINS_INDEX fields start with {fields[:1]!r}, expected 時間")
    names = [str(f).strip() for f in fields[1:]]
    out: dict[str, list[float | None]] = {n: [None] * BUCKETS for n in names}
    for r in payload.get("data") or []:
        try:
            h, m, s = (int(x) for x in str(r[0]).split(":"))
        except ValueError:
            continue
        sec = (h - 9) * 3600 + m * 60 + s
        if sec <= 0:
            continue
        b = (sec - 1) // 300  # 09:00:05 … 09:05:00 → bucket 0
        if b >= BUCKETS:
            continue
        for n, v in zip(names, r[1:]):
            x = num(v)
            if x is not None:
                out[n][b] = x  # rows come in time order: the last one in the bucket wins
    return out


async def fetch_sector_intraday(client: httpx.AsyncClient, day: date) -> dict[str, list[float | None]] | None:
    resp = await get_with_retry(client, f"{URL}?date={day:%Y%m%d}&response=json")
    try:
        payload = resp.json()
    except ValueError as exc:
        raise ParseError("MI_5MINS_INDEX did not return JSON") from exc
    return parse_sector_intraday(payload)
