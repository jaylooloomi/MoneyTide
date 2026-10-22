from __future__ import annotations

from collections.abc import Callable
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from .ingest import HistoryCollector
from .metrics import METRICS, Grouping, day_stocks, group_stats, industry_grouping, movers, rotation, stock_history
from .store import HistoryStore


def _date(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise HTTPException(422, f"invalid date {text!r}, expected YYYY-MM-DD") from exc


GROUPINGS = ("industry", "custom", "concept")


def create_history_router(
    get_store: Callable[[], HistoryStore],
    get_collector: Callable[[], HistoryCollector | None],
    get_grouping: Callable[[str], Grouping | None] = lambda name: industry_grouping if name == "industry" else None,
) -> APIRouter:
    r = APIRouter(prefix="/api/history")

    def grouping_of(name: str) -> Grouping:
        g = get_grouping(name) if name in GROUPINGS else None
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
        stocks = day_stocks(get_store(), d, None if grouping == "industry" else grouping_of(grouping))
        return {"date": d.isoformat(), "stocks": stocks}

    @r.get("/groups")
    def groups(
        day: str = Query(..., alias="date"), threshold: float = Query(5, ge=0, le=10), grouping: str = "industry"
    ) -> dict:
        d = _date(day)
        g = grouping_of(grouping)
        rows = get_store().day_rows(d)
        if not rows:
            raise HTTPException(404, f"no data for {day}")
        return {"date": d.isoformat(), "threshold": threshold, "groups": group_stats(rows, threshold, g)}

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
        g = grouping_of(grouping)
        try:
            return movers(get_store(), _date(to), mode, value, start=_date(start) if start else None, grouping=g)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    # bonus-02: one stock's card data with a short price history
    @r.get("/stock/{code}")
    def stock(code: str, to: str, days: int = Query(20, ge=2, le=250)) -> dict:
        data = stock_history(get_store(), code, _date(to), days)
        if data is None:
            raise HTTPException(404, f"no data for {code} on {to}")
        return data

    return r
