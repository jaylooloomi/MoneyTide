"""Which index a stock's intraday moves are measured against, for the excess R (扣大盤／類股).

A 上市 stock is measured against its 類股指數 (TWSE MI_5MINS_INDEX) when its industry has an index and at
least SECTOR_MIN_STOCKS 上市 stocks: in a small industry the index is mostly the group itself, and taking
it out would take out the very co-movement being looked for, so those use 大盤 instead. 上櫃 stocks use
櫃買 (TPEx has no per-industry intraday index). basis "market" uses 大盤／櫃買 for everyone.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date

SECTOR_MIN_STOCKS = 15
MARKET_FACTORS = {"上市": ("^TWII", "大盤"), "上櫃": ("IX0043.TWO", "櫃買")}


def sector_index_name(industry: str | None) -> str | None:
    """半導體業 → 半導體類指數, 水泥工業 → 水泥類指數, 電機機械 → 電機機械類指數."""
    if not industry:
        return None
    base = industry.removesuffix("工業").removesuffix("業")
    return f"{base}類指數" if base else None


def industry_sizes(rows: Iterable[Mapping]) -> dict[str, int]:
    """上市 common stocks per industry (the rows of one day)."""
    out: dict[str, int] = {}
    for r in rows:
        if r.get("market") == "上市" and r.get("kind", "stock") == "stock" and r.get("industry"):
            out[r["industry"]] = out.get(r["industry"], 0) + 1
    return out


def factor_of(row: Mapping, sizes: Mapping[str, int], sectors: set[str], basis: str = "sector") -> tuple[str, str] | None:
    """(factor key, label) for one stock: a 類股指數 name, ^TWII or IX0043.TWO; None for an unknown market."""
    market = MARKET_FACTORS.get(row.get("market"))
    if market is None:
        return None
    if basis == "sector" and row.get("market") == "上市":
        name = sector_index_name(row.get("industry"))
        if name in sectors and sizes.get(row.get("industry"), 0) >= SECTOR_MIN_STOCKS:
            return name, name.removesuffix("指數")
    return market


def sector_returns(closes_by_day: Mapping[date, Mapping[str, list]], sessions: list[date], name: str) -> list[float | None] | None:
    """One 類股指數's 5-minute returns over the sessions (53 a session, as finder.bucket_returns);
    None when a session is missing, so a stock is never measured against half an index."""
    out: list[float | None] = []
    for s in sessions:
        closes = closes_by_day.get(s, {}).get(name)
        if not closes:
            return None
        out.extend((y / x - 1) * 100 if x and y else None for x, y in zip(closes, closes[1:]))
    return out
