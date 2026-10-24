from __future__ import annotations

from collections.abc import Callable
from itertools import takewhile
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, HTTPException, Query

from ..config import TAIPEI

from .ingest import INDEX_MARKETS, HistoryCollector, index_window
from .finder import INST_STREAK_DAYS, inst_streak
from .linkage import group_r20
from .metrics import METRICS, Grouping, day_stocks, flow_baseline, group_flows, group_stats, industry_grouping, movers, rotation, stock_history, group_index, group_periods, group_rank_change
from .store import HistoryStore


def _date(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise HTTPException(422, f"invalid date {text!r}, expected YYYY-MM-DD") from exc


GROUPINGS = ("industry", "custom", "concept", "chain", "news")


def create_history_router(
    get_store: Callable[[], HistoryStore],
    get_collector: Callable[[], HistoryCollector | None],
    get_grouping: Callable[[str], Grouping | None] = lambda name: industry_grouping if name == "industry" else None,
) -> APIRouter:
    r = APIRouter(prefix="/api/history")

    def grouping_of(name: str, day: date | None = None) -> Grouping:
        # the news grouping changes with the day: endpoints that have a date ask for that day's themes
        lookup = f"news@{day.isoformat()}" if name == "news" and day else name
        g = get_grouping(lookup) if name in GROUPINGS else None
        if g is None:
            raise HTTPException(422, f"unknown or unavailable grouping {name!r}")
        return g

    @r.get("/days")
    def days() -> dict:
        store = get_store()
        collector = get_collector()
        items = sorted(store.days().items(), reverse=True)
        return {
            "days": [{"date": d.isoformat(), "status": s} for d, s in items],
            "backfill": collector.state.to_dict() if collector else {"running": False, "done": 0, "total": 0, "error": ""},
        }

    @r.get("/day/{day}")
    def day(day: str, grouping: str = "industry") -> dict:
        d = _date(day)
        if not get_store().day_rows(d):
            raise HTTPException(404, f"no data for {day}")
        stocks = day_stocks(get_store(), d, None if grouping == "industry" else grouping_of(grouping, d))
        return {"date": d.isoformat(), "stocks": stocks}

    @r.get("/groups")
    def groups(
        day: str = Query(..., alias="date"), threshold: float = Query(5, ge=0, le=10), grouping: str = "industry"
    ) -> dict:
        d = _date(day)
        g = grouping_of(grouping, d)
        rows = get_store().day_rows(d)
        if not rows:
            raise HTTPException(404, f"no data for {day}")
        stats = group_stats(rows, threshold, g)
        ranks = group_rank_change(get_store(), d, g)  # bonus-18
        for st in stats:
            st.update(ranks.get(st["name"], {"rank": None, "rank_change": None}))
        return {"date": d.isoformat(), "threshold": threshold, "groups": stats}

    @r.get("/rotation")
    def rotation_(
        days: int = Query(20, ge=2, le=250),
        metric: str = Query("strong_ratio"),
        threshold: float = Query(5, ge=0, le=10),
        to: str | None = None,
        grouping: str = "industry",
    ) -> dict:
        if metric not in METRICS:
            raise HTTPException(422, f"metric must be one of {METRICS}")
        g = grouping_of(grouping)
        return rotation(get_store(), days, metric, threshold, up_to=_date(to) if to else None, grouping=g)

    @r.get("/movers")
    def movers_(
        to: str,
        mode: str = Query("day", pattern="^(day|range|streak)$"),
        value: float = Query(5, ge=0, le=1000),
        start: str | None = Query(None, alias="from"),
        grouping: str = "industry",
    ) -> dict:
        g = grouping_of(grouping, _date(to))
        try:
            return movers(get_store(), _date(to), mode, value, start=_date(start) if start else None, grouping=g)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    def stock_inst(store: HistoryStore, code: str, d: date) -> dict | None:
        """三大法人 of one stock on d for its card: 外資／投信／自營／合計 in 張 and the 連買／連賣 streak
        (on trading days, stopping at the first one without 法人); None while d has no 法人 for it."""
        split = store.inst_split(d).get(code)
        if split is None:
            return None
        have = store.inst_dates()
        days = list(takewhile(lambda x: x in have, store.trading_dates(up_to=d, limit=INST_STREAK_DAYS)))
        one = [{"members": [{"code": code}]}]
        lots = lambda v: round(v / 1000)  # noqa: E731
        return {
            "foreign": lots(split[0]), "trust": lots(split[1]), "dealer": lots(split[2]), "total": lots(sum(split)),
            "streak": inst_streak(one, store.inst_net(days, [code]), days)[0]["inst_streak"],
            "trust_streak": inst_streak(one, store.inst_trust(days, [code]), days)[0]["inst_streak"],
        }

    # bonus-02: one stock's card data with a short price history
    @r.get("/stock/{code}")
    def stock(code: str, to: str, days: int = Query(20, ge=2, le=250)) -> dict:
        data = stock_history(get_store(), code, _date(to), days)
        if data is None:
            raise HTTPException(404, f"no data for {code} on {to}")
        return {**data, "inst": stock_inst(get_store(), code, _date(to))}

    # bonus-04: cumulative group index comparison
    @r.get("/index")
    def index(
        days: int = Query(20, ge=2, le=250),
        to: str | None = None,
        groups: str | None = None,
        top: int = Query(5, ge=1, le=20),
        grouping: str = "industry",
    ) -> dict:
        g = grouping_of(grouping)
        names = [n for n in (groups or "").split(",") if n] or None
        return group_index(get_store(), days, up_to=_date(to) if to else None, names=names, top=top, grouping=g)

    # bonus-10: 5/20/60-day group returns (loaded separately so the ranking renders first)
    @r.get("/periods")
    def periods(day: str = Query(..., alias="date"), grouping: str = "industry") -> dict:
        g = grouping_of(grouping, _date(day))
        return {"date": day, "groups": group_periods(get_store(), _date(day), grouping=g)}

    # money flow (spec 2026-10-23-money-flow-design.md)
    @r.get("/flows")
    def flows(day: str = Query(..., alias="date"), grouping: str = "industry") -> dict:
        d = _date(day)
        g = grouping_of(grouping, d)
        out = group_flows(get_store(), d, g)
        r20 = group_r20(get_store(), d, g)  # linkage: mean pairwise 20-day R of the top members
        for name, v in out.items():
            v["r20"] = r20.get(name)
        return {"date": day, "groups": out}

    @r.get("/flow-baseline")
    def baseline(grouping: str = "industry") -> dict:
        store = get_store()
        return flow_baseline(store, grouping_of(grouping), before=live_quote_day(store, datetime.now(TAIPEI)))

    # bonus-14: breadth calendar (one row per stored trading day)
    @r.get("/calendar")
    def calendar() -> dict:
        return {"days": get_store().daily_breadth()}

    # bonus-16: 20-day average turnover per industry and market (for the live 量能 column)
    @r.get("/turnover-avg")
    def turnover_avg(days: int = Query(20, ge=1, le=120)) -> dict:
        return get_store().group_turnover_avg(days)

    # G panel: TAIEX + TPEx daily candles with market strength per day
    @r.get("/market-index")
    def market_index(days: int = Query(250, ge=1, le=500)) -> dict:
        store = get_store()
        out = index_timeline(store, days)
        done = sum((m, mo) in store.index_months() for mo in index_window(datetime.now(TAIPEI)) for m in INDEX_MARKETS)
        collector = get_collector()
        out["backfill"] = {
            "months_done": done,
            "months_total": len(index_window(datetime.now(TAIPEI))) * len(INDEX_MARKETS),
            "running": bool(collector and collector.index_state.running),
            "error": collector.index_state.error if collector else "",
        }
        return out

    # bonus-24: per-stock 20-day average turnover before today (for the live 量比 colour)
    @r.get("/stock-turnover-avg")
    def stock_turnover(days: int = Query(20, ge=1, le=60)) -> dict:
        return stock_turnover_avg(get_store(), days, before=live_quote_day(get_store(), datetime.now(TAIPEI)))

    return r


# ---- bonus-24: per-stock average turnover --------------------------------------------


def live_quote_day(store: HistoryStore, now: datetime) -> date:
    """The trading day the live snapshot shows: today from 09:00 on a weekday; before the open and
    at weekends the quotes are still the last session's, i.e. the latest stored trading day."""
    local = now.astimezone(TAIPEI)
    if local.weekday() < 5 and local.time() >= time(9, 0):
        return local.date()
    latest = store.trading_dates(up_to=local.date(), limit=1)
    return latest[0] if latest else local.date()


def stock_turnover_avg(store: HistoryStore, days: int, before: date) -> dict:
    """Average daily turnover (元) per code over the latest `days` stored trading days strictly
    before `before` (so today's own volume never dilutes its baseline). Codes need a value on at
    least half of those days. {"as_of": date, "days": n, "avg": {code: 元}}; cached per day set."""
    dates = store.trading_dates(up_to=before - timedelta(days=1), limit=days)
    if not dates:
        return {"as_of": None, "days": 0, "avg": {}}
    key = ("stock_turnover_avg", dates[0], days)
    cached = store.derived_cache.get(key)
    if cached is not None:
        return cached
    sums: dict[str, float] = {}
    counts: dict[str, int] = {}
    for rows in store.rows(dates).values():
        for r in rows:
            t = r.get("turnover_yuan")
            if t is None:
                continue
            sums[r["code"]] = sums.get(r["code"], 0.0) + t
            counts[r["code"]] = counts.get(r["code"], 0) + 1
    need = (len(dates) + 1) // 2
    avg = {c: round(sums[c] / n) for c, n in counts.items() if n >= need and sums[c] > 0}
    result = {"as_of": dates[0].isoformat(), "days": len(dates), "avg": avg}
    store.derived_cache[key] = result
    return result


# ---- G panel: index timeline -----------------------------------------------------------

STRONG_PCT = 5.0  # same threshold as the B ranking's default ≥5% share


def index_timeline(store: HistoryStore, days: int) -> dict:
    """Union of index days and stored stock days, oldest first, the last `days` of them.
    twse/tpex are null where that market has no index row; strength is null without stock data."""
    from .metrics import LIMIT_PCT

    index = store.index_rows()
    strength = store.daily_strength(STRONG_PCT, LIMIT_PCT)
    dates = sorted(set(index) | {d.isoformat() for d in store.trading_dates()})[-days:]
    rows = []
    for d in dates:
        by_market = index.get(d, {})
        s = strength.get(d)
        rows.append({
            "date": d,
            "twse": by_market.get("上市"),
            "tpex": by_market.get("上櫃"),
            "strong_ratio": s["strong_ratio"] if s else None,
            "limit_up": s["limit_up"] if s else None,
            "has_stocks": s is not None,
        })
    return {"days": rows}
