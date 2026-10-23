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

import math
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


HOT_TURNOVER = 5.0  # M: 週轉率 ≥ 5%
HOT_AMPLITUDE = 3.0  # and 振幅 > 3%
HOT_MAX = 60  # at most this many (the highest turnover first); keeps the Yahoo fetches bounded


def turnover_rate(r: dict) -> float | None:
    """週轉率 %: shares traded / shares outstanding (market cap ÷ close)."""
    cap, close, vol = r.get("market_cap"), r.get("close"), r.get("volume_shares")
    if not cap or not close or vol is None:
        return None
    return vol / (cap / close) * 100


def amplitude_pct(r: dict) -> float | None:
    """振幅 %: (high − low) / previous close."""
    h, lo, prev = r.get("high"), r.get("low"), r.get("prev_close")
    return (h - lo) / prev * 100 if h and lo and prev else None


def hot_members(rows: list[dict], min_turnover: float = HOT_TURNOVER, min_amp: float = HOT_AMPLITUDE, limit: int = HOT_MAX) -> tuple[list[dict], int]:
    """Common stocks with 週轉率 ≥ min_turnover and 振幅 > min_amp → (members, how many matched).
    The `limit` highest-turnover ones are kept, then ordered by market cap (the leader first, like K)."""
    hot = [
        r for r in rows
        if r.get("kind") == "stock"
        and (turnover_rate(r) or 0) >= min_turnover
        and (amplitude_pct(r) or 0) > min_amp
    ]
    hot.sort(key=lambda r: -(turnover_rate(r) or 0))
    kept = hot[:limit]
    kept.sort(key=lambda r: -(r.get("market_cap") or 0))
    return kept, len(hot)


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


# TWSE / TPEx stock tick sizes (升降單位) by price band
TICKS = ((10, 0.01), (50, 0.05), (100, 0.1), (500, 0.5), (1000, 1.0), (float("inf"), 5.0))


def tick_size(price: float) -> float:
    return next(t for top, t in TICKS if price < top)


def limit_up_pct(prev_close: float | None) -> float | None:
    """% change at the limit-up price: prev close × 1.1 rounded down to its tick (so 9.5–10%, not 10)."""
    if not prev_close:
        return None
    raw = prev_close * 1.1
    tick = tick_size(raw)
    price = int(raw / tick + 1e-9) * tick
    return round((price / prev_close - 1) * 100, 2)


def limit_down_pct(prev_close: float | None) -> float | None:
    """% change at the limit-down price: prev close × 0.9 rounded up to its tick."""
    if not prev_close:
        return None
    raw = prev_close * 0.9
    tick = tick_size(raw)
    price = math.ceil(raw / tick - 1e-9) * tick
    return round((price / prev_close - 1) * 100, 2)


def minute_bars(bars: list[tuple]) -> list[list]:
    """Yahoo bars (HH:MM, high, low, close[, open, volume]) → [[minute, open, high, low, close, volume]]."""
    out = []
    for b in bars:
        m = minutes(b[0])
        if not 0 <= m <= 270:
            continue
        o = b[4] if len(b) > 4 and b[4] is not None else b[3]
        out.append([m, o, b[1], b[2], b[3], b[5] if len(b) > 5 else None])
    return out


def tick_bars(points: list[tuple[str, float]]) -> list[list]:
    """Recorded polls → per-minute [[minute, open, high, low, close, None]] (polls carry no volume)."""
    by: dict[int, list] = {}
    for ts, p in points:
        m = minutes(ts)
        if not 0 <= m <= 270 or not p:
            continue
        b = by.get(m)
        if b is None:
            by[m] = [m, p, p, p, p, None]
        else:
            b[2], b[3], b[4] = max(b[2], p), min(b[3], p), p
    return [by[m] for m in sorted(by)]


def with_close_bar(bars: list[list], day_row: dict) -> list[list]:
    """End on 13:30 with the official close; its volume is what the bars left out of the day's total."""
    close = day_row.get("close")
    if not bars or close is None:
        return bars
    bars = [b for b in bars if b[0] < 270]
    vols = [b[5] for b in bars]
    total = day_row.get("volume_shares")
    rest = total - sum(vols) if total is not None and all(v is not None for v in vols) else None
    return bars + [[270, close, close, close, close, rest if rest is not None and rest > 0 else (0 if rest is not None else None)]]


def race_points(points: list[tuple], prev_close: float | None) -> list[list[float]]:
    """(HH:MM[:SS], high, close) bars or (ts, price, price) polls → [[minute since 09:00, close %, high %]]:
    the last close and the highest high per minute. K's animated timeline replays these from 09:00 to
    13:30; its moving high dot uses the highs, so it lands where peak_minute_from_* put the 日內最高點."""
    if not prev_close:
        return []
    pct = lambda p: round((p / prev_close - 1) * 100, 2)  # noqa: E731
    by_minute: dict[int, list[float]] = {}
    for ts, high, close in points:
        m = minutes(ts)
        if not (0 <= m <= 270 and high and close):
            continue
        prev = by_minute.get(m)
        by_minute[m] = [pct(close), max(pct(high), prev[1]) if prev else pct(high)]
    return [[m, c, h] for m, (c, h) in sorted(by_minute.items())]


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
