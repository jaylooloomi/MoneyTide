"""How tightly a group's members move together (spec 2026-10-23-linkage-design.md).

- Daily: Pearson correlation of daily % changes between the top-N members by market cap, over the
  last 20 and 60 trading days; the group's R is the mean of the pairwise values.
- Intraday: correlation of 5-minute returns (within each session, never across the overnight gap)
  over the last 1–3 sessions, from the app's own recorded polls or, for days it did not record,
  Yahoo 5-minute bars.
- Peak timing (日內最高點時間): the minute each member first reaches its 09:00–13:00 high (recorded polls, else Yahoo
  1-minute bars for the last ~30 days, else the 5-minute bars); the spread (std, minutes) and how
  long after the leader (largest cap) the others peak.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date

from .metrics import Grouping
from .store import HistoryStore

TOP_N = 8
MIN_POINTS = 10  # pairs with fewer common observations are left out
HIGH_R = 0.7
LOW_R = 0.3
SYNC_MIN = 10
SCATTER_MIN = 60


def pearson(a: list[float], b: list[float]) -> float | None:
    n = len(a)
    if n < 3:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va == 0 or vb == 0:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (va * vb) ** 0.5


def pair_matrix(series: list[list[float | None]], min_points: int = MIN_POINTS) -> tuple[list[list[float | None]], float | None]:
    """Pairwise correlations over positions where both series have values, and their mean."""
    n = len(series)
    m: list[list[float | None]] = [[None] * n for _ in range(n)]
    vals = []
    for i in range(n):
        m[i][i] = 1.0
        for j in range(i + 1, n):
            pts = [(x, y) for x, y in zip(series[i], series[j]) if x is not None and y is not None]
            r = pearson([x for x, _ in pts], [y for _, y in pts]) if len(pts) >= min_points else None
            m[i][j] = m[j][i] = round(r, 3) if r is not None else None
            if r is not None:
                vals.append(r)
    return m, (round(sum(vals) / len(vals), 3) if vals else None)


INTRADAY_HIGH_R = 0.5  # 5-minute returns are far noisier than daily ones
INTRADAY_LOW_R = 0.2


def verdict_r(r: float | None, high: float = HIGH_R, low: float = LOW_R) -> str:
    if r is None:
        return "資料不足"
    if r > high:
        return "群體圍攻"
    if r < low:
        return "單兵作戰"
    return "中度連動"


def verdict_timing(std_min: float | None) -> str:
    if std_min is None:
        return "資料不足"
    if std_min <= SYNC_MIN:
        return "高度同步"
    if std_min >= SCATTER_MIN:
        return "時間錯落"
    return "普通"


def top_members(rows: list[dict], grouping: Grouping, group: str, n: int = TOP_N) -> list[dict]:
    seen, members = set(), []
    for r in rows:
        if r.get("kind") == "stock" and group in grouping(r) and r["code"] not in seen:
            seen.add(r["code"])
            members.append(r)
    members.sort(key=lambda r: -(r.get("market_cap") or 0))
    return members[:n]


def daily_linkage(store: HistoryStore, day: date, codes: list[str], windows: Iterable[int] = (20, 60)) -> dict:
    windows = list(windows)
    dates = sorted(store.trading_dates(up_to=day, limit=max(windows)))
    by_day = store.change_rows(dates)
    pct = {d: {r["code"]: r["change_pct"] for r in by_day[d]} for d in dates}
    out = {}
    for w in windows:
        span = dates[-w:]
        series = [[pct[d].get(c) for d in span] for c in codes]
        matrix, mean = pair_matrix(series)
        out[f"r{w}"] = mean
        out[f"matrix{w}"] = matrix
    return out


def group_r20(store: HistoryStore, day: date, grouping: Grouping) -> dict[str, float | None]:
    """Mean pairwise 20-day R of every group's top members (the B column), cached per day."""
    key = ("link_r20", getattr(grouping, "cache_key", None), day)
    if key[1] is not None and key in store.derived_cache:
        return store.derived_cache[key]
    rows = store.day_rows(day)
    names = {g for r in rows if r.get("kind") == "stock" for g in grouping(r)}
    dates = sorted(store.trading_dates(up_to=day, limit=20))
    by_day = store.change_rows(dates)
    pct = {d: {r["code"]: r["change_pct"] for r in by_day[d]} for d in dates}
    out = {}
    for name in names:
        codes = [r["code"] for r in top_members(rows, grouping, name)]
        if len(codes) < 2:
            out[name] = None
            continue
        _, out[name] = pair_matrix([[pct[d].get(c) for d in dates] for c in codes])
    if key[1] is not None:
        store.derived_cache[key] = out
    return out


# ---- intraday ---------------------------------------------------------------------------------

def minutes(hhmm: str) -> int:
    h, m = int(hhmm[:2]), int(hhmm[3:5])
    return h * 60 + m - 9 * 60


def bucket_closes(points: list[tuple[str, float]], size: int = 5) -> dict[int, float]:
    """Recorded polls → last price per `size`-minute bucket (bucket = minutes since 09:00 // size)."""
    out: dict[int, float] = {}
    for ts, price in points:
        out[minutes(ts) // size] = price
    return out


def returns(closes: Mapping[int, float], buckets: list[int]) -> list[float | None]:
    """Bucket-to-bucket % returns on a shared bucket axis (None where either end is missing)."""
    out = []
    for a, b in zip(buckets, buckets[1:]):
        x, y = closes.get(a), closes.get(b)
        out.append((y / x - 1) * 100 if x and y else None)
    return out


PEAK_END = 240  # minutes after 09:00: the intraday high is taken over 09:00–13:00


def peak_minute_from_ticks(points: list[tuple[str, float]]) -> int | None:
    points = [p for p in points if minutes(p[0]) <= PEAK_END]
    if not points:
        return None
    best = max(p for _, p in points)
    return next(minutes(ts) for ts, p in points if p == best)


def peak_minute_from_bars(bars: list[tuple]) -> int | None:
    """bars: (HH:MM, high, low, close); the bar start of the first bar reaching the 09:00–13:00 high."""
    bars = [b for b in bars if minutes(b[0]) <= PEAK_END]
    if not bars:
        return None
    best = max(b[1] for b in bars)
    return next(minutes(b[0]) for b in bars if b[1] == best)


def race_points(points: list[tuple], prev_close: float | None) -> list[list[float]]:
    """(HH:MM[:SS], price) polls or bar closes → [[minute since 09:00, % change]], last value per minute.
    The 漲幅賽跑 animation in K replays these from 09:00 to 13:30."""
    if not prev_close:
        return []
    by_minute: dict[int, float] = {}
    for ts, price in points:
        m = minutes(ts)
        if 0 <= m <= 270 and price:
            by_minute[m] = round((price / prev_close - 1) * 100, 2)
    return [[m, v] for m, v in sorted(by_minute.items())]


def peak_stats(peaks: list[int | None]) -> tuple[float | None, float | None]:
    """(std of peak minutes, mean delay of the others after the leader = peaks[0])."""
    known = [p for p in peaks if p is not None]
    if len(known) < 2:
        return None, None
    mean = sum(known) / len(known)
    std = (sum((p - mean) ** 2 for p in known) / len(known)) ** 0.5
    lag = None
    if peaks[0] is not None:
        others = [p - peaks[0] for p in peaks[1:] if p is not None]
        lag = sum(others) / len(others) if others else None
    return round(std, 1), (round(lag, 1) if lag is not None else None)


def fmt_minute(m: int | None) -> str | None:
    if m is None:
        return None
    return f"{9 + m // 60:02d}:{m % 60:02d}"
