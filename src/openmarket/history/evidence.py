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


BRANCH_TOP = 5  # a branch in both stocks' top this many 買超 counts as the same buyer


def shared_buyers(a: Mapping | None, b: Mapping | None) -> dict | None:
    """Branches among the top 買超 of both stocks: {shared: [{name, a_net, b_net, a_rank, b_rank}], strong}
    (strong: one of them is in both top BRANCH_TOP); None without both days' data."""
    if not a or not b:
        return None
    ra = {r["name"]: (i + 1, r["net"]) for i, r in enumerate(a.get("buy", []))}
    rb = {r["name"]: (i + 1, r["net"]) for i, r in enumerate(b.get("buy", []))}
    shared = [
        {"name": n, "a_rank": ra[n][0], "a_net": ra[n][1], "b_rank": rb[n][0], "b_net": rb[n][1]}
        for n in ra if n in rb and ra[n][1] > 0 and rb[n][1] > 0
    ]
    shared.sort(key=lambda x: x["a_rank"] + x["b_rank"])
    return {"shared": shared, "strong": any(x["a_rank"] <= BRANCH_TOP and x["b_rank"] <= BRANCH_TOP for x in shared)}


def concentration(data: Mapping | None, volume_shares: float | None, top: int = 15) -> float | None:
    """籌碼集中度 % = (前 15 大買超分點的買超 + 前 15 大賣超分點的賣超(負)) ÷ 當日成交張數 × 100, as the
    Taiwan 籌碼 sites define it: > 0 the biggest buyers took more than the biggest sellers gave. None
    without 分點 or volume."""
    if not data or "error" in data or not volume_shares or not (data.get("buy") or data.get("sell")):
        return None  # an empty page (HiStock had no rows that day) is no data, not 0%
    net = sum(r.get("net", 0) for r in data.get("buy", [])[:top]) + sum(r.get("net", 0) for r in data.get("sell", [])[:top])
    return round(net / (volume_shares / 1000) * 100, 1)


def buyer_cost(data: Mapping | None, top: int = 5) -> float | None:
    """主力成本: the top `top` 買超 分點's 均價, weighted by their 買超張數 (HiStock's 均價 per branch);
    None without 分點 or prices."""
    rows = [r for r in (data or {}).get("buy", [])[:top] if r.get("avg") and r.get("net", 0) > 0] if data and "error" not in data else []
    net = sum(r["net"] for r in rows)
    return round(sum(r["avg"] * r["net"] for r in rows) / net, 2) if net else None


def buy_streaks(days: list[Mapping | None], top: int = 5) -> dict[str, int]:
    """主力連續買超: for the top `top` 買超 分點 of days[0] (the shown day), how many trading days in a row,
    counting back, each one was among that day's 買超 (top 15). days: newest first, one entry per trading
    day (None = no 分點 stored that day, which ends the count — a gap is not a buy)."""
    if not days or not days[0] or "error" in days[0]:
        return {}
    out = {}
    for r in days[0].get("buy", [])[:top]:
        n = 0
        for d in days:
            if not d or "error" in d or not any(x["name"] == r["name"] and x.get("net", 0) > 0 for x in d.get("buy", [])):
                break
            n += 1
        out[r["name"]] = n
    return out


def group_branches(members: list[str], data: Mapping[str, Mapping], top: int = 15) -> dict | None:
    """分點 of a group from the stored days: {common: [{name, ranks: {code: rank}, nets: {code: 張}}] (branches
    among the top `top` 買超 of 2+ members, most members first), ok (most pairs share a top-5 buyer),
    have: members with data}; None when fewer than two members have it."""
    have = [c for c in members if data.get(c) and "error" not in data[c]]
    if len(have) < 2:
        return None
    seen: dict[str, dict] = {}
    for c in have:
        for i, r in enumerate(data[c].get("buy", [])[:top]):
            if r.get("net", 0) > 0:
                e = seen.setdefault(r["name"], {"name": r["name"], "ranks": {}, "nets": {}})
                e["ranks"][c] = i + 1
                e["nets"][c] = r["net"]
    common = [e for e in seen.values() if len(e["ranks"]) >= 2]
    common.sort(key=lambda e: (-len(e["ranks"]), sum(e["ranks"].values())))
    pairs = [shared_buyers(data[a], data[b]) for i, a in enumerate(have) for b in have[i + 1:]]
    strong = [p["strong"] for p in pairs if p is not None]
    return {"common": common[:5], "ok": (sum(strong) * 2 > len(strong)) if strong else None, "have": len(have)}
