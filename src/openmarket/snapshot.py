"""Merge quotes + classification + issued shares into stocks.

Industry aggregation happens in the browser (static/js/transform.js), because it depends on the
user's filters; keeping a single implementation avoids two copies of the weighting rules.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from .models import ETF_INDUSTRY, OTHER_INDUSTRY, Kind, Quote, Stock, StockInfo


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
