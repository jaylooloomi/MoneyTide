from __future__ import annotations

from collections.abc import Callable
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from .ingest import HistoryCollector
from .metrics import METRICS, day_stocks, group_stats, movers, rotation
from .store import HistoryStore


def _date(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise HTTPException(422, f"invalid date {text!r}, expected YYYY-MM-DD") from exc


def create_history_router(get_store: Callable[[], HistoryStore], get_collector: Callable[[], HistoryCollector | None]) -> APIRouter:
    r = APIRouter(prefix="/api/history")

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
    def day(day: str) -> dict:
        d = _date(day)
        stocks = day_stocks(get_store(), d)
        if not stocks:
            raise HTTPException(404, f"no data for {day}")
        return {"date": d.isoformat(), "stocks": stocks}

    @r.get("/groups")
    def groups(day: str = Query(..., alias="date"), threshold: float = Query(5, ge=0, le=10)) -> dict:
        d = _date(day)
        rows = get_store().day_rows(d)
        if not rows:
            raise HTTPException(404, f"no data for {day}")
        return {"date": d.isoformat(), "threshold": threshold, "groups": group_stats(rows, threshold)}

    @r.get("/rotation")
    def rotation_(
        days: int = Query(20, ge=2, le=250),
        metric: str = Query("strong_ratio"),
        threshold: float = Query(5, ge=0, le=10),
        to: str | None = None,
    ) -> dict:
        if metric not in METRICS:
            raise HTTPException(422, f"metric must be one of {METRICS}")
        return rotation(get_store(), days, metric, threshold, up_to=_date(to) if to else None)

    @r.get("/movers")
    def movers_(
        to: str,
        mode: str = Query("day", pattern="^(day|range|streak)$"),
        value: float = Query(5, ge=0, le=1000),
        start: str | None = Query(None, alias="from"),
    ) -> dict:
        try:
            return movers(get_store(), _date(to), mode, value, start=_date(start) if start else None)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    return r
