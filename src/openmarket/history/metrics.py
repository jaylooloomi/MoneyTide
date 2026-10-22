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
    """Official industry; only common stocks (ETF/preferred/TDR are not an industry's members)."""
    return [row["industry"]] if row.get("industry") and row.get("kind") == "stock" else []


def mapping_grouping(code_to_groups: dict[str, list[str]]) -> Grouping:
    """Grouping from a code → [group names] map (custom / concept groups; any security kind)."""
    return lambda row: code_to_groups.get(row["code"], [])


def _cap_weight(r: dict) -> float:
    cap, close, prev = r.get("market_cap"), r.get("close"), r.get("prev_close")
    if not cap or not close or not prev:
        return 0.0
    return cap / close * prev


def _leader(members: list[dict]) -> dict | None:
    """bonus-09: the member with the biggest gain that day (the stock leading the group)."""
    best = max((r for r in members if r.get("change_pct") is not None), key=lambda r: r["change_pct"], default=None)
    if best is None:
        return None
    return {"code": best["code"], "name": best["name"], "change_pct": best["change_pct"]}


def group_stats(rows: list[dict], threshold: float, grouping: Grouping = industry_grouping) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
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
            "leader": _leader(members),  # bonus-09
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


def day_stocks(store: HistoryStore, day: date, grouping: Grouping | None = None) -> list[dict]:
    """One day's rows in the live-snapshot Stock shape (so the treemap code is reused).

    With a grouping, `industry` is replaced by the group name and a stock that belongs to
    several groups appears once per group; stocks in no group are left out."""
    dates = store.trading_dates(up_to=day, limit=WEEK_DAYS + 1)
    if not dates or dates[0] != day:
        return []
    rows = store.rows([day] + ([dates[-1]] if len(dates) > WEEK_DAYS else []))
    week_ago = {r["code"]: r["close"] for r in rows.get(dates[-1], [])} if len(dates) > WEEK_DAYS else {}
    out = []
    for r in rows[day]:
        names = grouping(r) if grouping else [r["industry"]]
        if not names:
            continue
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
        if grouping:
            base_row = out.pop()
            out.extend({**base_row, "industry": n, "kind": "stock"} for n in names)
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
        picked = [(r, r["change_pct"]) for r in rows if grouping(r) and r.get("change_pct") is not None and r["change_pct"] >= value]
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
        for r in (r for r in data[to] if grouping(r)):
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
            if not grouping(r):
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


# ---- bonus-02: single-stock history for the history-page info card ----

def stock_history(store: HistoryStore, code: str, to: date, days: int = 20) -> dict | None:
    """The stock's row on `to` plus its closes over the last `days` trading days (oldest first)."""
    rows = store.stock_rows(code, to, days)
    if not rows or rows[-1]["date"] != to.isoformat():
        return None
    last = rows[-1]
    first_close = next((r["close"] for r in rows if r["close"]), None)
    return {
        "code": code,
        "name": last["name"],
        "industry": last["industry"],
        "market": last["market"],
        "date": last["date"],
        "close": last["close"],
        "change": last["change"],
        "change_pct": last["change_pct"],
        "high": last["high"],
        "low": last["low"],
        "volume_lots": last["volume_shares"] / 1000 if last["volume_shares"] is not None else None,
        "turnover_100m": last["turnover_yuan"] / 1e8 if last["turnover_yuan"] is not None else None,
        "market_cap": last["market_cap"],
        "period_pct": (last["close"] / first_close - 1) * 100 if last["close"] and first_close else None,
        "series": [{"date": r["date"], "close": r["close"], "change_pct": r["change_pct"]} for r in rows],
    }


# ---- bonus-04: cumulative group index for the comparison chart ----

MARKET = "全市場"


def group_index(
    store: HistoryStore, days: int, up_to: date | None = None, names: list[str] | None = None,
    top: int = 5, grouping: Grouping = industry_grouping,
) -> dict:
    """Cumulative return (%) of each group's equal-weight daily average, compounded over the last
    `days` trading days, plus the whole market (common stocks) as a benchmark.

    `names` picks the groups; otherwise the `top` groups by period return are returned."""
    dates = sorted(store.trading_dates(up_to=up_to, limit=days))
    by_day = store.rows(dates)
    # one pass per day: equal-weight average change of each group and of the whole market
    daily: dict[str, list] = defaultdict(lambda: [None] * len(dates))
    market_daily: list = [None] * len(dates)
    for i, d in enumerate(dates):
        sums: dict[str, list[float]] = defaultdict(lambda: [0.0, 0])
        msum, mcount = 0.0, 0
        for r in by_day[d]:
            pct = r.get("change_pct")
            if pct is None:
                continue
            if r.get("kind") == "stock":
                msum += pct
                mcount += 1
            for g in grouping(r):
                acc = sums[g]
                acc[0] += pct
                acc[1] += 1
        for g, (total, n) in sums.items():
            daily[g][i] = total / n
        market_daily[i] = msum / mcount if mcount else None

    def compound(values: list) -> list:
        level, out = 1.0, []
        for v in values:
            if v is not None:
                level *= 1 + v / 100
            out.append(round((level - 1) * 100, 4))
        return out

    series = [{"name": n, "values": compound(v)} for n, v in daily.items()]
    if names:
        wanted = set(names)
        series = [x for x in series if x["name"] in wanted]
    else:
        series = sorted(series, key=lambda x: x["values"][-1] if x["values"] else 0, reverse=True)[:top]
    return {"dates": [d.isoformat() for d in dates], "series": series, "market": compound(market_daily)}
