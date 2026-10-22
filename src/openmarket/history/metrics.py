"""Group strength metrics over stored history. Groupings map a row to one or more group names."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import date

from .store import HistoryStore

LIMIT_PCT = 9.5  # 台股漲跌幅限制 10%，≥9.5% 視為漲停（價格跳動造成的誤差）
WEEK_DAYS = 5

Grouping = Callable[[dict], Iterable[str]]
METRICS = ("avg_pct", "cap_pct", "strong_ratio", "breadth", "limit_up")


def industry_grouping(row: dict) -> list[str]:
    return [row["industry"]] if row.get("industry") else []


def _stocks(rows: Iterable[dict]) -> list[dict]:
    return [r for r in rows if r.get("kind") == "stock"]


def _cap_weight(r: dict) -> float:
    cap, close, prev = r.get("market_cap"), r.get("close"), r.get("prev_close")
    if not cap or not close or not prev:
        return 0.0
    return cap / close * prev


def group_stats(rows: list[dict], threshold: float, grouping: Grouping = industry_grouping) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in _stocks(rows):
        for g in grouping(r):
            groups[g].append(r)
    out = []
    for name, members in groups.items():
        pcts = [r["change_pct"] for r in members if r.get("change_pct") is not None]
        weighted = [(r["change_pct"], _cap_weight(r)) for r in members if r.get("change_pct") is not None]
        weighted = [(v, w) for v, w in weighted if w > 0]
        total_w = sum(w for _, w in weighted)
        up = sum(1 for r in members if (r.get("change") or 0) > 0)
        down = sum(1 for r in members if (r.get("change") or 0) < 0)
        out.append({
            "name": name,
            "count": len(members),
            "avg_pct": sum(pcts) / len(pcts) if pcts else None,
            "cap_pct": sum(v * w for v, w in weighted) / total_w if total_w else None,
            "strong_count": sum(1 for p in pcts if p >= threshold),
            "strong_ratio": sum(1 for p in pcts if p >= threshold) / len(pcts) * 100 if pcts else None,
            "limit_up": sum(1 for p in pcts if p >= LIMIT_PCT),
            "limit_down": sum(1 for p in pcts if p <= -LIMIT_PCT),
            "up": up,
            "down": down,
            "breadth": up / (up + down) * 100 if up + down else None,
            "turnover": sum(r.get("turnover_yuan") or 0 for r in members),
        })
    out.sort(key=lambda g: (g["strong_ratio"] is None, -(g["strong_ratio"] or 0), -(g["avg_pct"] or 0)))
    return out


def rotation(
    store: HistoryStore, days: int, metric: str, threshold: float, up_to: date | None = None,
    grouping: Grouping = industry_grouping,
) -> dict:
    if metric not in METRICS:
        raise ValueError(f"metric must be one of {METRICS}")
    dates = sorted(store.trading_dates(up_to=up_to, limit=days))
    by_day = store.rows(dates)
    table: dict[str, list] = defaultdict(lambda: [None] * len(dates))
    for i, d in enumerate(dates):
        for g in group_stats(by_day[d], threshold, grouping):
            table[g["name"]][i] = g[metric]
    groups = [{"name": n, "values": v} for n, v in table.items()]
    # strongest recent groups first: mean of the last 3 values
    def recent(g):
        tail = [x for x in g["values"][-3:] if x is not None]
        return sum(tail) / len(tail) if tail else float("-inf")
    groups.sort(key=recent, reverse=True)
    return {"dates": [d.isoformat() for d in dates], "metric": metric, "groups": groups}


def day_stocks(store: HistoryStore, day: date) -> list[dict]:
    """One day's rows in the live-snapshot Stock shape (so the treemap code is reused)."""
    dates = store.trading_dates(up_to=day, limit=WEEK_DAYS + 1)
    if not dates or dates[0] != day:
        return []
    rows = store.rows([day] + ([dates[-1]] if len(dates) > WEEK_DAYS else []))
    week_ago = {r["code"]: r["close"] for r in rows.get(dates[-1], [])} if len(dates) > WEEK_DAYS else {}
    out = []
    for r in rows[day]:
        prev, close = r["prev_close"], r["close"]
        base = week_ago.get(r["code"])
        out.append({
            "code": r["code"], "name": r["name"], "market": r["market"], "industry": r["industry"],
            "kind": r["kind"], "price": close, "change": r["change"], "change_pct": r["change_pct"],
            "week_pct": (close / base - 1) * 100 if close and base else None,
            "amplitude_pct": (r["high"] - r["low"]) / prev * 100 if r["high"] and r["low"] and prev else None,
            "open": r["open"], "high": r["high"], "low": r["low"], "prev_close": prev,
            "volume_lots": r["volume_shares"] / 1000 if r["volume_shares"] is not None else None,
            "turnover_100m": r["turnover_yuan"] / 1e8 if r["turnover_yuan"] is not None else None,
            "market_cap": r["market_cap"],
        })
    return out


def movers(
    store: HistoryStore, to: date, mode: str, value: float, start: date | None = None,
    grouping: Grouping = industry_grouping,
) -> dict:
    """Stocks that rose together, grouped.

    mode=day:    change_pct on `to` >= value
    mode=range:  cumulative return from the close before `start` to `to` >= value
    mode=streak: consecutive up days ending at `to` >= value
    """
    if mode == "day":
        rows = store.rows([to]).get(to, [])
        picked = [(r, r["change_pct"]) for r in _stocks(rows) if r.get("change_pct") is not None and r["change_pct"] >= value]
        label = "漲幅"
    elif mode == "range":
        if start is None or start > to:
            raise ValueError("range mode needs start <= to")
        dates = [d for d in store.trading_dates(up_to=to) if d >= start]
        before = store.trading_dates(up_to=start, limit=2)
        base_day = next((d for d in before if d < start), None)
        if not dates or base_day is None:
            return {"mode": mode, "groups": []}
        data = store.rows([base_day, to])
        base = {r["code"]: r["close"] for r in data[base_day]}
        picked = []
        for r in _stocks(data[to]):
            b = base.get(r["code"])
            if r["close"] and b:
                ret = (r["close"] / b - 1) * 100
                if ret >= value:
                    picked.append((r, ret))
        label = "區間漲幅"
    elif mode == "streak":
        dates = store.trading_dates(up_to=to, limit=60)
        data = store.rows(dates)
        by_code: dict[str, list] = defaultdict(list)
        for d in dates:  # newest first
            for r in data[d]:
                by_code[r["code"]].append(r)
        latest = {r["code"]: r for r in data.get(to, [])}
        picked = []
        for code, r in latest.items():
            if r.get("kind") != "stock":
                continue
            streak = 0
            for row in by_code[code]:
                if (row.get("change") or 0) > 0:
                    streak += 1
                else:
                    break
            if streak >= value:
                picked.append((r, float(streak)))
        label = "連漲天數"
    else:
        raise ValueError("mode must be day, range or streak")

    groups: dict[str, list] = defaultdict(list)
    for r, metric in picked:
        for g in grouping(r):
            groups[g].append({"code": r["code"], "name": r["name"], "value": metric, "change_pct": r.get("change_pct"), "close": r.get("close")})
    out = [{"name": n, "stocks": sorted(s, key=lambda x: -x["value"])} for n, s in groups.items()]
    out.sort(key=lambda g: (-len(g["stocks"]), -max(x["value"] for x in g["stocks"])))
    return {"mode": mode, "label": label, "groups": out}
