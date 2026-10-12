"""Merge quotes + classification + issued shares into stocks, and aggregate industries.

The industry aggregation rules are mirrored in static/js/transform.js — keep them in sync.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping

from .models import ETF_INDUSTRY, OTHER_INDUSTRY, IndustryStat, Kind, Quote, Stock, StockInfo


def fallback_kind(code: str) -> Kind:
    """Classification for codes missing from the ISIN listing."""
    if code.startswith("00"):
        return "etf"
    return "stock" if code.isdigit() and len(code) == 4 else "other"


def merge_stock(quote: Quote, info: StockInfo | None, shares: int | None) -> Stock:
    if info is not None:
        kind, market, industry = info.kind, info.market, info.industry
    else:
        kind, market, industry = fallback_kind(quote.code), "未知", ""
    if kind == "etf":
        industry = ETF_INDUSTRY
    elif not industry:
        industry = OTHER_INDUSTRY
    ref_price = quote.price if quote.price is not None else quote.prev_close
    market_cap = ref_price * shares if ref_price is not None and shares else None
    return Stock(
        code=quote.code,
        name=quote.name,
        price=quote.price,
        change=quote.change,
        change_pct=quote.change_pct,
        week_pct=quote.week_pct,
        amplitude_pct=quote.amplitude_pct,
        open=quote.open,
        high=quote.high,
        low=quote.low,
        prev_close=quote.prev_close,
        volume_lots=quote.volume_lots,
        turnover_100m=quote.turnover_100m,
        industry=industry,
        market=market,
        kind=kind,
        market_cap=market_cap,
    )


def _avg(stocks: list[Stock], attr: str, cap_weighted: bool) -> float | None:
    pairs = [(getattr(s, attr), s.market_cap) for s in stocks if getattr(s, attr) is not None]
    if not pairs:
        return None
    if cap_weighted:
        total = sum(w for _, w in pairs)
        if total > 0:
            return sum(v * w for v, w in pairs) / total
    return sum(v for v, _ in pairs) / len(pairs)


def aggregate_industry(name: str, members: list[Stock]) -> IndustryStat:
    # Cap-weighted only when every member has a market cap; otherwise equal weight (never mixed).
    cap_weighted = all(s.market_cap for s in members)
    up = sum(1 for s in members if s.change is not None and s.change > 0)
    down = sum(1 for s in members if s.change is not None and s.change < 0)
    return IndustryStat(
        name=name,
        change_pct=_avg(members, "change_pct", cap_weighted),
        week_pct=_avg(members, "week_pct", cap_weighted),
        amplitude_pct=_avg(members, "amplitude_pct", cap_weighted=False),
        turnover_100m=sum(s.turnover_100m or 0.0 for s in members),
        up_count=up,
        down_count=down,
        flat_count=len(members) - up - down,
        stock_count=len(members),
    )


def aggregate_industries(stocks: Iterable[Stock], include_etf: bool = False) -> list[IndustryStat]:
    """Aggregate common stocks (plus ETFs when asked). kind == "other" is never aggregated."""
    groups: dict[str, list[Stock]] = defaultdict(list)
    for s in stocks:
        if s.kind == "other" or (s.kind == "etf" and not include_etf):
            continue
        groups[s.industry].append(s)
    stats = [aggregate_industry(name, members) for name, members in groups.items()]
    stats.sort(key=lambda st: (st.change_pct is None, -(st.change_pct or 0.0)))
    return stats


def build_stocks(
    quotes: Iterable[Quote],
    infos: Mapping[str, StockInfo],
    shares: Mapping[str, int],
) -> list[Stock]:
    """Merge quotes with classification. When ISIN data is present, codes missing from it are
    dropped: HiStock keeps ~170 delisted/expired codes with stale prices and zero volume."""
    seen: set[str] = set()
    stocks: list[Stock] = []
    for q in quotes:
        if q.code in seen or (infos and q.code not in infos):
            continue
        seen.add(q.code)
        stocks.append(merge_stock(q, infos.get(q.code), shares.get(q.code)))
    return stocks
