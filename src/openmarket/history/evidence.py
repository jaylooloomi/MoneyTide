"""資金一致性證據: checks that tell co-ordinated buying from coincidence, for K's 🔗 交集 (pure functions).

1. excess_matrix: intraday R after taking out the index (each stock's own β to 大盤 / 櫃買).
2. percentile_of: where a pair's R sits among random pairs of the same day and 漲幅 bucket.
3. minute_evidence: 1-minute volume bursts in the same minute (vs the count chance would give) and
   whether the 1-minute returns line up best at no offset (same-minute orders) rather than ±1–3 minutes.
6. chip_sync: 投信 buying the pair on the same days, 融資 and 法人 direction.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from datetime import date

from .linkage import pair_matrix, pearson

BURST_RATIO = 3.0  # a minute trading ≥ this × the stock's median 1-minute volume is a burst
LAGS = (1, 2, 3)  # minutes either way for the same-minute check
MIN_MINUTE_POINTS = 60
BASELINE_PAIRS = 300


def beta(r: Sequence[float | None], m: Sequence[float | None]) -> float | None:
    pts = [(x, y) for x, y in zip(r, m) if x is not None and y is not None]
    if len(pts) < 20:
        return None
    my = sum(y for _, y in pts) / len(pts)
    var = sum((y - my) ** 2 for _, y in pts)
    if var == 0:
        return None
    mx = sum(x for x, _ in pts) / len(pts)
    return sum((x - mx) * (y - my) for x, y in pts) / var


def residuals(r: Sequence[float | None], m: Sequence[float | None]) -> list[float | None]:
    """r − β·m: what is left of a stock's moves once its index's are taken out (None where either is)."""
    b = beta(r, m)
    if b is None:
        return [None] * len(r)
    return [x - b * y if x is not None and y is not None else None for x, y in zip(r, m)]


def excess_matrix(series: list[list[float | None]], index_of: list[list[float | None] | None], min_points: int = 20) -> list[list[float | None]]:
    """Pairwise R of the residual returns; a stock without its index series keeps no excess R."""
    res = [residuals(s, m) if m is not None else [None] * len(s) for s, m in zip(series, index_of)]
    return pair_matrix(res, min_points=min_points)[0]


def minute_series(bars: Sequence[tuple]) -> tuple[dict[int, float], dict[int, float]]:
    """1-minute bars (HH:MM, high, low, close, open, volume) → ({minute: return %}, {minute: volume})."""
    def mins(t: str) -> int:
        return (int(t[:2]) - 9) * 60 + int(t[3:5])

    close = {mins(b[0]): b[3] for b in bars if b[3]}
    vol = {mins(b[0]): b[5] for b in bars if len(b) > 5 and b[5] is not None}
    ret = {t: (close[t] / close[t - 1] - 1) * 100 for t in close if t - 1 in close and close[t - 1]}
    return ret, vol


def bursts(vol: Mapping[int, float], ratio: float = BURST_RATIO) -> set[int]:
    traded = sorted(v for v in vol.values() if v > 0)
    if len(traded) < 10:
        return set()
    median = traded[len(traded) // 2]
    return {t for t, v in vol.items() if v >= ratio * median}


def lag_r(a: Mapping[int, float], b: Mapping[int, float], k: int) -> float | None:
    pts = [(a[t], b[t + k]) for t in a if t + k in b]
    if len(pts) < MIN_MINUTE_POINTS:
        return None
    return pearson([x for x, _ in pts], [y for _, y in pts])


def minute_evidence(bars_a: Sequence[tuple] | None, bars_b: Sequence[tuple] | None) -> dict | None:
    """{bursts_a, bursts_b, co, expected, r0, r_off} for one pair; None without 1-minute bars for both."""
    if not bars_a or not bars_b:
        return None
    ra, va = minute_series(bars_a)
    rb, vb = minute_series(bars_b)
    ba, bb = bursts(va), bursts(vb)
    both = set(va) & set(vb)
    co = len(ba & bb & both)
    expected = (len(ba & both) * len(bb & both) / len(both)) if both else None
    r0 = lag_r(ra, rb, 0)
    offs = [x for k in LAGS for x in (lag_r(ra, rb, k), lag_r(ra, rb, -k)) if x is not None]
    return {
        "bursts_a": len(ba), "bursts_b": len(bb), "co": co,
        "expected": round(expected, 2) if expected is not None else None,
        "r0": round(r0, 3) if r0 is not None else None,
        "r_off": round(max(offs), 3) if offs else None,
    }


PCT_BUCKETS = (-100.0, -5.0, -2.0, 2.0, 5.0, 9.5, 100.0)


def bucket_of(pct: float | None) -> int | None:
    if pct is None:
        return None
    for i in range(len(PCT_BUCKETS) - 1):
        if PCT_BUCKETS[i] <= pct < PCT_BUCKETS[i + 1]:
            return i
    return len(PCT_BUCKETS) - 2


def percentile_of(value: float | None, pool: Mapping[str, Sequence[float | None]], exclude: set[str], seed: str,
                  pairs: int = BASELINE_PAIRS, min_points: int = 15) -> dict | None:
    """Where `value` (a pair's R) sits among the R of random pairs drawn from `pool` ({code: series}):
    {pct: share of random pairs below it (0–100), n: pairs used, median}. Seeded, so it is stable."""
    if value is None:
        return None
    codes = sorted(c for c in pool if c not in exclude)
    if len(codes) < 4:
        return None
    rnd = random.Random(seed)
    rs = []
    tries = 0
    while len(rs) < pairs and tries < pairs * 4:
        tries += 1
        a, b = rnd.sample(codes, 2)
        pts = [(x, y) for x, y in zip(pool[a], pool[b]) if x is not None and y is not None]
        if len(pts) < min_points:
            continue
        r = pearson([x for x, _ in pts], [y for _, y in pts])
        if r is not None:
            rs.append(r)
    if len(rs) < 30:
        return None
    rs.sort()
    below = sum(1 for r in rs if r < value)
    return {"pct": round(below / len(rs) * 100), "n": len(rs), "median": round(rs[len(rs) // 2], 3)}


def chip_sync(a: str, b: str, trust: Mapping[date, Mapping[str, float]], inst_today: Mapping[str, float],
              margin_today: Mapping[str, tuple]) -> dict:
    """投信 on the same days (both net buy / both net sell, over the given days), today's 法人 and 融資 direction."""
    both_buy = both_sell = days = 0
    for day in trust.values():
        x, y = day.get(a), day.get(b)
        if x is None or y is None:
            continue
        days += 1
        both_buy += x > 0 and y > 0
        both_sell += x < 0 and y < 0
    sign = lambda v: None if v is None else (v > 0) - (v < 0)  # noqa: E731
    mchg = lambda c: (margin_today[c][1] - margin_today[c][0]) if c in margin_today else None  # noqa: E731
    return {
        "trust_days": days, "trust_both_buy": both_buy, "trust_both_sell": both_sell,
        "inst_a": sign(inst_today.get(a)), "inst_b": sign(inst_today.get(b)),
        "margin_a": sign(mchg(a)), "margin_b": sign(mchg(b)),
    }
