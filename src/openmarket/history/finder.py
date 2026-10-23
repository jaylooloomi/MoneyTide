"""N · 資金連動搜尋: find stocks that one pool of money moved together.

Two searches share one funnel, cheapest test first (spec: memory linkage-finder-pending):

- 找法1 (known): inside every group of the known groupings (官方產業 / 自訂 / 概念股 / 細產業 / 新聞族群).
- 找法2 (new): a candidate pool from the day's rankings (漲幅, 週轉率, 成交比重暴增), then the found
  groups are matched back to the known groupings (已知 / 延伸 / 跨族群新組合).

Funnel per pair: daily correlation (local data) → intraday 5-minute correlation over the last few
sessions, limit-up-locked stretches left out → the intraday high (09:00–13:00) within a few minutes
of each other, not merely both at the 09:00 open. Pairs become groups only as dense cores (every
member passes with at least `dense` of the others), never by chaining A~B~C.

Every threshold is a FinderParams field: the user expects to tune them. Market-beta removal is
deliberately not applied yet (to be validated later).
"""

from __future__ import annotations

import json
import math
import operator
from collections.abc import Awaitable, Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import date
from itertools import combinations

from .linkage import align_bars, amplitude_pct, limit_up_pct, minutes, pearson, turnover_rate
from .store import HistoryStore

FINDER_VERSION = 2  # part of the cache key: bump when the search logic changes, so stored results are redone
PEAK_END = 240  # the intraday high is taken over 09:00–13:00
OPEN_MINUTES = 2  # a high at 09:00–09:02 is the open, not a signal (unless locked limit-up)
BUCKETS = 54  # 5-minute buckets 09:00–13:25


@dataclass(frozen=True)
class FinderParams:
    daily_window: int = 20  # 找法1: days of daily % changes
    daily_r: float = 0.8
    new_daily_window: int = 10  # 找法2: a new combination has little history yet
    new_daily_r: float = 0.8
    intraday_r: float = 0.5  # 5-minute returns
    intraday_sessions: int = 3
    intraday_min_points: int = 20
    peak_gap: int = 8  # minutes between intraday highs
    start_gap: int | None = None  # 起漲時間 gap; None = shown, not required
    require_burst: bool = False  # need a 5-minute window where both traded ≥ burst_ratio × their median
    burst_ratio: float = 3.0
    dense: float = 0.7  # each member passes with ≥ this share of the group
    min_size: int = 2
    pool_top: int = 50  # 找法2: top N of each ranking
    pool_sources: tuple[str, ...] = ("gain", "turnover", "share_z")
    share_window: int = 20  # days behind the 成交比重暴增 z-score
    groupings: tuple[str, ...] = ("industry", "custom", "concept", "chain", "news")
    max_fetch: int = 400  # at most this many stocks get intraday bars (largest candidate sets first)

    def key(self) -> str:
        return json.dumps({**asdict(self), "v": FINDER_VERSION}, sort_keys=True, ensure_ascii=False)


GROUPING_LABELS = {"industry": "官方產業", "custom": "自訂族群", "concept": "概念股", "chain": "細產業", "news": "新聞族群"}


# ---- stage A: daily ------------------------------------------------------------------------------

def daily_series(store: HistoryStore, day: date, window: int) -> dict[str, list[float | None]]:
    """{code: daily % changes over the last `window` trading days up to `day`} for common stocks traded that day."""
    dates = sorted(store.trading_dates(up_to=day, limit=window))
    if not dates or dates[-1] != day:
        return {}
    by_day = store.change_rows(dates)
    today = {r["code"] for r in by_day[day] if r.get("change_pct") is not None}
    kinds = {r["code"]: r.get("kind") for r in store.day_rows(day)}
    out: dict[str, list[float | None]] = {}
    for i, d in enumerate(dates):
        for r in by_day[d]:
            c = r["code"]
            if c in today and kinds.get(c) == "stock":
                out.setdefault(c, [None] * len(dates))[i] = r["change_pct"]
    return out


def series_r(a: list, b: list, min_points: int) -> float | None:
    pts = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    if len(pts) < min_points:
        return None
    return pearson([x for x, _ in pts], [y for _, y in pts])


class PairR:
    """Daily R between any two stocks, each pair computed once (the same pair recurs across groupings).

    A stock with no missing day is standardised up front, so its R with another complete one is a
    single dot product; a pair with gaps goes through the plain Pearson on the shared days."""

    def __init__(self, series: Mapping[str, list]):
        self.series = series
        n = len(next(iter(series.values()))) if series else 0
        self.n = n
        self.need = max(3, n - 2)  # most of the window (all but 2 days)
        self.z: dict[str, list[float]] = {}
        for c, s in series.items():
            if n >= 3 and None not in s:
                m = sum(s) / n
                sd = (sum((x - m) ** 2 for x in s) / n) ** 0.5
                if sd > 0:
                    self.z[c] = [(x - m) / sd for x in s]
        self.memo: dict[tuple[str, str], float | None] = {}

    def __call__(self, a: str, b: str) -> float | None:
        key = (a, b) if a < b else (b, a)
        if key in self.memo:
            return self.memo[key]
        za, zb = self.z.get(a), self.z.get(b)
        if za is not None and zb is not None:
            r = sum(map(operator.mul, za, zb)) / self.n
        else:
            r = series_r(self.series[a], self.series[b], self.need)
        self.memo[key] = r
        return r


def daily_edges(codes: Iterable[str], series: Mapping[str, list] | PairR, threshold: float) -> dict[frozenset, float]:
    """Pairs with daily R ≥ threshold → {frozenset({a, b}): r}. Needs most of the window (all but 2 days)."""
    pr = series if isinstance(series, PairR) else PairR(series)
    codes = sorted({c for c in codes if c in pr.series})
    out = {}
    for a, b in combinations(codes, 2):
        r = pr(a, b)
        if r is not None and r >= threshold:
            out[frozenset((a, b))] = r
    return out


def dense_cores(edges: Iterable[frozenset], dense: float, min_size: int) -> list[list[str]]:
    """Groups where every member is linked to ≥ dense × (size − 1) of the others.

    Seeded from the best-connected stock: its connected component is peeled (the weakest member out)
    until dense; then the next seed. Members of a found core are not reused."""
    adj: dict[str, set[str]] = {}
    for e in edges:
        a, b = tuple(e)
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    left = set(adj)
    cores = []
    while left:
        seed = max(left, key=lambda v: (len(adj[v] & left), v))
        comp, todo = {seed}, [seed]
        while todo:
            v = todo.pop()
            for w in adj[v] & left:
                if w not in comp:
                    comp.add(w)
                    todo.append(w)
        group = set(comp)
        while len(group) >= min_size:
            need = math.ceil(dense * (len(group) - 1))
            worst = min(group, key=lambda v: (len(adj[v] & group), v))
            if len(adj[worst] & group) >= need:
                break
            group.discard(worst)
        if len(group) >= min_size and seed in group:
            cores.append(sorted(group))
            left -= group
        else:
            left.discard(seed)
    return cores


def known_candidates(rows: list[dict], groupings: Mapping[str, Callable[[dict], list[str]]], series: Mapping[str, list], p: FinderParams) -> list[dict]:
    """找法1 stage A: dense daily cores inside each known group; the same member set from several
    groupings is one candidate listing all its sources."""
    by_members: dict[tuple, dict] = {}
    pr = PairR(series)
    for gname, grouping in groupings.items():
        groups: dict[str, list[str]] = {}
        for r in rows:
            if r.get("kind") == "stock" and r["code"] in series:
                for g in grouping(r):
                    groups.setdefault(g, []).append(r["code"])
        for g, codes in groups.items():
            if len(codes) < p.min_size:
                continue
            edges = daily_edges(codes, pr, p.daily_r)
            for core in dense_cores(edges, p.dense, p.min_size):
                key = tuple(core)
                c = by_members.setdefault(key, {"members": core, "sources": [], "daily": {}})
                c["sources"].append({"grouping": gname, "label": GROUPING_LABELS.get(gname, gname), "group": g})
                c["daily"].update({e: r for e, r in edges.items() if e <= set(core)})
    return list(by_members.values())


def share_z(store: HistoryStore, day: date, window: int) -> dict[str, float]:
    """成交比重暴增: each stock's share of the market's turnover today as a z-score vs the previous `window` days."""
    dates = sorted(store.trading_dates(up_to=day, limit=window + 1))
    if len(dates) < 3 or dates[-1] != day:
        return {}
    rows = store.rows(dates)
    shares: dict[str, list[float]] = {}
    for i, d in enumerate(dates):
        total = sum(r.get("turnover_yuan") or 0 for r in rows[d] if r.get("kind") == "stock")
        if not total:
            continue
        for r in rows[d]:
            if r.get("kind") == "stock":
                shares.setdefault(r["code"], [0.0] * len(dates))[i] = (r.get("turnover_yuan") or 0) / total * 100
    out = {}
    for c, s in shares.items():
        hist, now = s[:-1], s[-1]
        m = sum(hist) / len(hist)
        sd = (sum((x - m) ** 2 for x in hist) / len(hist)) ** 0.5
        out[c] = (now - m) / max(sd, 0.01)
    return out


def candidate_pool(rows: list[dict], z: Mapping[str, float], p: FinderParams) -> dict[str, list[str]]:
    """找法2: top `pool_top` common stocks of each ranking → {code: [sources]}."""
    stocks = [r for r in rows if r.get("kind") == "stock" and r.get("change_pct") is not None]
    rankers = {
        "gain": ("漲幅", lambda r: r.get("change_pct")),
        "turnover": ("週轉率", turnover_rate),
        "share_z": ("比重暴增", lambda r: z.get(r["code"])),
    }
    pool: dict[str, list[str]] = {}
    for src in p.pool_sources:
        label, key = rankers[src]
        ranked = sorted((r for r in stocks if key(r) is not None), key=lambda r: -key(r))[: p.pool_top]
        for r in ranked:
            pool.setdefault(r["code"], []).append(label)
    return pool


# ---- stage B/C: intraday -------------------------------------------------------------------------

@dataclass
class Intraday:
    """One stock's intraday features: 5-minute returns over the sessions (locked stretches left out),
    and for the shown day the high / 起漲 minutes, limit-up lock and volume bursts."""
    returns: list[float | None] = field(default_factory=list)
    peak: int | None = None
    start: int | None = None
    locked_at: int | None = None
    bursts: set[int] = field(default_factory=set)
    resolution: int = 1


def bucket_returns(bars: list[tuple], limit: float | None) -> list[float | None]:
    """5-minute close-to-close returns on the fixed 09:00–13:25 axis; a step where both closes sit at
    the limit-up price (locked) is None, so a flat locked line does not count as 'not moving together'."""
    close: dict[int, float] = {}
    for b in bars:
        m = minutes(b[0])
        if 0 <= m < BUCKETS * 5:
            close[m // 5] = b[3]
    out = []
    for i in range(BUCKETS - 1):
        x, y = close.get(i), close.get(i + 1)
        if not x or not y:
            out.append(None)
        elif limit and x >= limit - 0.001 and y >= limit - 0.001:
            out.append(None)
        else:
            out.append((y / x - 1) * 100)
    return out


def intraday_features(by_session: Mapping[date, list[tuple]], rows_by_session: Mapping[date, dict], day: date, p: FinderParams, resolution: int = 1) -> Intraday:
    """Bars (HH:MM, high, low, close[, open, volume]) per session, already aligned to official prices."""
    f = Intraday(resolution=resolution)
    for s in sorted(by_session):
        row = rows_by_session.get(s) or {}
        pct = limit_up_pct(row.get("prev_close"))
        limit = row["prev_close"] * (1 + pct / 100) if pct is not None else None
        f.returns.extend(bucket_returns(by_session[s], limit))
    bars = [b for b in by_session.get(day, []) if 0 <= minutes(b[0]) <= 270]
    row = rows_by_session.get(day) or {}
    if not bars:
        return f
    window = [b for b in bars if minutes(b[0]) <= PEAK_END]
    if window:
        hi = max(b[1] for b in window)
        f.peak = next(minutes(b[0]) for b in window if b[1] == hi)
        before = [b for b in window if minutes(b[0]) <= f.peak]
        lo = min(b[2] for b in before)
        f.start = max(minutes(b[0]) for b in before if b[2] == lo)  # the last touch of the low before the run
    pct = limit_up_pct(row.get("prev_close"))
    if pct is not None:
        limit = row["prev_close"] * (1 + pct / 100)
        f.locked_at = next((minutes(b[0]) for b in bars if b[3] >= limit - 0.001), None)
    vol: dict[int, float] = {}
    for b in bars:
        if len(b) > 5 and b[5] is not None:
            vol[minutes(b[0]) // 5] = vol.get(minutes(b[0]) // 5, 0) + b[5]
    inner = sorted(v for k, v in vol.items() if 0 < k < BUCKETS and v > 0)  # the open / close auctions aside
    if inner:
        med = inner[len(inner) // 2]
        f.bursts = {k for k, v in vol.items() if 0 < k < BUCKETS and v >= p.burst_ratio * med}
    return f


def pair_check(a: Intraday, b: Intraday, p: FinderParams) -> dict:
    """Stage B/C for one pair → {ok, intraday_r, peak_gap, start_gap, burst, reason}."""
    r = series_r(a.returns, b.returns, p.intraday_min_points)
    both_locked = a.locked_at is not None and b.locked_at is not None
    out = {"intraday_r": r, "peak_gap": None, "start_gap": None, "burst": sorted(a.bursts & b.bursts), "ok": False, "reason": ""}
    if r is None:
        if not both_locked:  # too few points (locked all day) only passes when both are locked
            out["reason"] = "分時資料不足"
            return out
    elif r < p.intraday_r:
        out["reason"] = "分時相關不足"
        return out
    if a.peak is None or b.peak is None:
        out["reason"] = "沒有高點時間"
        return out
    out["peak_gap"] = abs(a.peak - b.peak)
    if a.start is not None and b.start is not None:
        out["start_gap"] = abs(a.start - b.start)
    if max(a.peak, b.peak) <= OPEN_MINUTES and not both_locked:
        out["reason"] = "開盤即高點（假同步）"
        return out
    if out["peak_gap"] > p.peak_gap:
        out["reason"] = "高點時間差太大"
        return out
    if p.start_gap is not None and (out["start_gap"] is None or out["start_gap"] > p.start_gap):
        out["reason"] = "起漲時間差太大"
        return out
    if p.require_burst and not out["burst"]:
        out["reason"] = "沒有同時爆量"
        return out
    out["ok"] = True
    return out


def confirm(candidates: list[dict], feats: Mapping[str, Intraday], p: FinderParams) -> list[dict]:
    """Stage B/C on each candidate's pairs; the passing pairs become dense cores again."""
    found = []
    seen = set()
    for c in candidates:
        checks = {}
        for a, b in combinations(c["members"], 2):
            if a in feats and b in feats:
                checks[frozenset((a, b))] = pair_check(feats[a], feats[b], p)
        ok = [e for e, ch in checks.items() if ch["ok"]]
        for core in dense_cores(ok, p.dense, p.min_size):
            key = tuple(core)
            if key in seen:
                continue
            seen.add(key)
            inside = {e: ch for e, ch in checks.items() if e <= set(core)}
            found.append({**c, "members": core, "pairs": inside, "daily": {e: r for e, r in c.get("daily", {}).items() if e <= set(core)}})
    return found


# ---- describing a found group -------------------------------------------------------------------

def match_known(members: list[str], rows_by_code: Mapping[str, dict], groupings: Mapping[str, Callable[[dict], list[str]]]) -> list[dict]:
    """The best-overlapping known group per grouping: [{grouping, label, group, overlap, outside}]."""
    out = []
    for gname, grouping in groupings.items():
        count: dict[str, list[str]] = {}
        for c in members:
            row = rows_by_code.get(c)
            for g in grouping(row) if row else []:
                count.setdefault(g, []).append(c)
        if not count:
            continue
        g, inside = max(count.items(), key=lambda kv: (len(kv[1]), kv[0]))
        out.append({"grouping": gname, "label": GROUPING_LABELS.get(gname, gname), "group": g, "overlap": len(inside) / len(members), "outside": [c for c in members if c not in inside]})
    out.sort(key=lambda m: -m["overlap"])
    return out


def kind_of(matches: list[dict], size: int) -> str:
    """已知族群: all in one known group; 延伸: at least half and at least 2 of them in one (the rest
    are the stocks that 'should not' move with it); otherwise 跨族群新組合 (a lone member in some
    group, as in most pairs, is no known group at all)."""
    if not matches:
        return "跨族群新組合"
    best = matches[0]
    inside = size - len(best.get("outside", []))
    if best["overlap"] >= 0.999:
        return "已知族群"
    if best["overlap"] >= 0.5 and inside >= 2:
        return "已知族群的延伸"
    return "跨族群新組合"


def co_mentions(names: Mapping[str, str], titles: Iterable[str], limit: int = 3) -> list[str]:
    """Headlines naming at least two of the members (動機的證據)."""
    clean = {c: n.rstrip("*＊ ").replace("-KY", "") for c, n in names.items() if n}
    out = []
    for t in titles:
        hit = [c for c, n in clean.items() if len(n) >= 2 and n in t]
        if len(hit) >= 2 and t not in out:
            out.append(t)
            if len(out) >= limit:
                break
    return out


def describe(g: dict, rows_by_code: Mapping[str, dict], feats: Mapping[str, Intraday], groupings: Mapping[str, Callable], titles: list[str], inst: Mapping[str, float]) -> dict:
    members = g["members"]
    fmt = lambda m: None if m is None else f"{9 + m // 60:02d}:{m % 60:02d}"  # noqa: E731
    pairs = g.get("pairs", {})
    vals = lambda key: [ch[key] for ch in pairs.values() if ch.get(key) is not None]  # noqa: E731
    mean = lambda xs: round(sum(xs) / len(xs), 3) if xs else None  # noqa: E731
    peaks = [feats[c].peak for c in members if c in feats and feats[c].peak is not None]
    starts = [feats[c].start for c in members if c in feats and feats[c].start is not None]
    burst = sorted(set.intersection(*[feats[c].bursts for c in members if c in feats]) if all(c in feats for c in members) else set())
    matches = match_known(members, rows_by_code, groupings)
    names = {c: rows_by_code[c]["name"] for c in members if c in rows_by_code}
    return {
        "members": [
            {
                "code": c,
                "name": names.get(c, c),
                "change_pct": rows_by_code.get(c, {}).get("change_pct"),
                "turnover_rate": turnover_rate(rows_by_code[c]) if c in rows_by_code else None,
                "amplitude_pct": amplitude_pct(rows_by_code[c]) if c in rows_by_code else None,
                "peak": fmt(feats[c].peak) if c in feats else None,
                "start": fmt(feats[c].start) if c in feats else None,
                "locked_at": fmt(feats[c].locked_at) if c in feats else None,
                "inst_net": inst.get(c),
            }
            for c in members
        ],
        "sources": g.get("sources", []),
        "pool": g.get("pool", {}),
        "daily_r": mean(list(g.get("daily", {}).values())),
        "intraday_r": mean(vals("intraday_r")),
        "peak_spread": (max(peaks) - min(peaks)) if len(peaks) >= 2 else None,
        "start_spread": (max(starts) - min(starts)) if len(starts) >= 2 else None,
        "together_bursts": [fmt(b * 5) for b in burst],
        "matches": matches[:3],
        "kind": kind_of(matches, len(members)),
        "news": co_mentions(names, titles),
        "inst_net": sum(v for c in members if (v := inst.get(c)) is not None) or None,
        "resolution": max((feats[c].resolution for c in members if c in feats), default=1),
    }


# ---- one full search ----------------------------------------------------------------------------

_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="finder")

FetchBars = Callable[[list[dict], list[date]], Awaitable[dict[str, tuple[dict[date, list], int]]]]


async def run_search(
    store: HistoryStore,
    day: date,
    method: str,
    p: FinderParams,
    groupings: Mapping[str, Callable[[dict], list[str]]],
    fetch: FetchBars,
    titles: list[str] | None = None,
) -> dict:
    """找法1 ('known') or 找法2 ('new') for `day`. `fetch(rows, sessions)` returns
    {code: ({session: bars}, resolution minutes)} — the only network step, run for stage-A survivors only."""
    import asyncio
    import time

    loop = asyncio.get_running_loop()

    async def off(fn, *args):  # a pool of N's own: the shared one is busy with start-up backfills
        return await loop.run_in_executor(_POOL, fn, *args)

    timing: dict[str, float] = {}
    t = time.perf_counter()
    rows = [r for r in store.day_rows(day) if r.get("kind") == "stock"]
    by_code = {r["code"]: r for r in rows}
    if method == "known":
        series = await off(daily_series, store, day, p.daily_window)
        cands = await off(known_candidates, rows, groupings, series, p)
        pool_size = None
    else:
        z = await off(share_z, store, day, p.share_window)
        pool = candidate_pool(rows, z, p)
        series = await off(daily_series, store, day, p.new_daily_window)
        edges = await off(daily_edges, list(pool), series, p.new_daily_r)
        cands = [
            {"members": core, "sources": [], "pool": {c: pool[c] for c in core}, "daily": {e: r for e, r in edges.items() if e <= set(core)}}
            for core in dense_cores(edges, p.dense, p.min_size)
        ]
        pool_size = len(pool)
    timing["daily"] = round(time.perf_counter() - t, 2)

    t = time.perf_counter()
    need: list[str] = []
    for c in sorted(cands, key=lambda c: -len(c["members"])):  # the largest candidate sets first
        for code in c["members"]:
            if code not in need:
                need.append(code)
    need = need[: p.max_fetch]
    sessions = sorted(store.trading_dates(up_to=day, limit=p.intraday_sessions))
    got = await fetch([by_code[c] for c in need if c in by_code], sessions) if need else {}
    timing["fetch"] = round(time.perf_counter() - t, 2)

    t = time.perf_counter()
    session_rows = {s: {r["code"]: r for r in rs} for s, rs in store.rows(sessions).items()}
    feats = {}
    for code, (by_session, resolution) in got.items():
        aligned = {s: align_bars(b, session_rows.get(s, {}).get(code, {})) for s, b in by_session.items()}
        feats[code] = intraday_features(aligned, {s: session_rows.get(s, {}).get(code, {}) for s in sessions}, day, p, resolution)
    found = confirm(cands, feats, p)
    inst = store.inst_net([day]).get(day, {})
    groups = [describe(g, by_code, feats, groupings, titles or [], inst) for g in found]
    groups.sort(key=lambda g: (-len(g["members"]), -(g["intraday_r"] or 0)))
    timing["intraday"] = round(time.perf_counter() - t, 2)
    return {
        "date": day.isoformat(),
        "method": method,
        "params": asdict(p),
        "groupings": [GROUPING_LABELS.get(g, g) for g in groupings],
        "stats": {"candidates": len(cands), "pool": pool_size, "fetched": len(got), "groups": len(groups), "seconds": timing},
        "groups": groups,
    }
