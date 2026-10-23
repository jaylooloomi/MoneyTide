from datetime import date

import pytest

from openmarket.history.finder import (
    FinderParams,
    Intraday,
    bucket_returns,
    candidate_pool,
    co_mentions,
    confirm,
    daily_edges,
    dense_cores,
    intraday_features,
    kind_of,
    known_candidates,
    match_known,
    pair_check,
)

P = FinderParams()


def e(a, b):
    return frozenset((a, b))


def test_dense_cores_do_not_chain():
    # A-B-C-D in a line: no member links to ≥70% of a 3+ group, so only pairs survive
    line = [e("A", "B"), e("B", "C"), e("C", "D")]
    cores = dense_cores(line, 0.7, 3)
    assert cores == []
    # a full triangle plus a hanger-on: the triangle is the core
    edges = [e("A", "B"), e("B", "C"), e("A", "C"), e("C", "D")]
    assert dense_cores(edges, 0.7, 3) == [["A", "B", "C"]]
    # two separate pairs
    assert sorted(dense_cores([e("A", "B"), e("X", "Y")], 0.7, 2)) == [["A", "B"], ["X", "Y"]]


def test_daily_edges_threshold_and_missing_days():
    s = {"A": [1, 2, 3, 4, 5], "B": [1.1, 2.1, 2.9, 4.2, 5], "C": [5, 1, 4, 2, 3], "D": [1, None, None, None, 5]}
    edges = daily_edges("ABCD", s, 0.8)
    assert set(edges) == {e("A", "B")}  # C uncorrelated; D misses too many days


def test_known_candidates_merges_sources():
    rows = [{"code": c, "kind": "stock", "industry": "X", "high": 105, "low": 100, "prev_close": 100, "volume_shares": 500_000} for c in "ABC"]
    s = {"A": [1, 2, 3, 4, 5], "B": [1, 2, 3, 4, 5.5], "C": [1.2, 2, 3.1, 4, 5]}
    groupings = {"industry": lambda r: [r["industry"]], "custom": lambda r: ["題材"]}
    (c,) = known_candidates(rows, groupings, s, P)
    assert c["members"] == ["A", "B", "C"]
    assert [x["grouping"] for x in c["sources"]] == ["industry", "custom"]
    assert len(c["daily"]) == 3
    # 振幅 filter: C moved only 2% that day, so it is not a member
    rows[2].update(high=101, low=99)
    (c,) = known_candidates(rows, groupings, s, P)
    assert c["members"] == ["A", "B"]
    assert known_candidates(rows, groupings, s, FinderParams(min_amplitude=1.5))[0]["members"] == ["A", "B", "C"]
    # volume filter: B traded only 200 張 (< 300)
    rows[1]["volume_shares"] = 200_000
    assert known_candidates(rows, groupings, s, FinderParams(min_amplitude=1.5))[0]["members"] == ["A", "C"]
    assert known_candidates(rows, groupings, s, FinderParams(min_amplitude=1.5, min_volume_lots=100))[0]["members"] == ["A", "B", "C"]


def test_bucket_returns_skip_locked_stretch():
    # prev 100, limit 110: 09:00 105, 09:05 110 (locks), 09:10 110 (locked), 09:15 110
    bars = [("09:00", 105, 105, 105), ("09:05", 110, 110, 110), ("09:10", 110, 110, 110), ("09:15", 110, 110, 110)]
    r = bucket_returns(bars, 110.0)
    assert r[0] == pytest.approx((110 / 105 - 1) * 100)
    assert r[1] is None and r[2] is None  # flat at the limit: not counted


def test_intraday_features_peak_start_lock_bursts():
    row = {"prev_close": 100.0}
    bars = [
        ("09:00", 101, 99, 100, 100, 5000),  # the open auction: not a burst bucket
        ("09:05", 100, 98, 98.5, 100, 100),
        ("09:10", 99, 97, 98, 98, 100),  # low 97: the run starts here
        ("09:15", 104, 98, 104, 98, 900),  # burst (≥ 3 × median 100)
        ("09:20", 110, 104, 110, 104, 120),  # limit 110 reached
        ("13:10", 110, 110, 110, 110, 100),
    ]
    f = intraday_features({date(2026, 1, 2): bars}, {date(2026, 1, 2): row}, date(2026, 1, 2), P)
    assert (f.peak, f.start, f.locked_at) == (20, 10, 20)
    assert f.bursts == {3}


def mk(peak, start=None, locked=None, rets=None, bursts=()):
    return Intraday(returns=rets if rets is not None else [], peak=peak, start=start, locked_at=locked, bursts=set(bursts))


def test_pair_check_rules():
    up = [0.1, 0.3, -0.2, 0.5, 0.1] * 6  # 30 points
    same = [x * 1.1 for x in up]
    other = [(-1) ** i * 0.3 for i in range(30)]
    assert pair_check(mk(60, rets=up), mk(66, rets=same), P)["ok"]
    assert pair_check(mk(60, rets=up), mk(80, rets=same), P)["reason"] == "高點時間差太大"
    assert pair_check(mk(60, rets=up), mk(62, rets=other), P)["reason"] == "分時相關不足"
    assert pair_check(mk(0, rets=up), mk(1, rets=same), P)["reason"] == "開盤即高點（假同步）"
    # both locked at the open with no usable returns: counts as moving together
    assert pair_check(mk(0, locked=0), mk(1, locked=1), P)["ok"]
    # optional requirements
    p = FinderParams(start_gap=5, require_burst=True)
    assert pair_check(mk(60, 10, rets=up), mk(62, 30, rets=same), p)["reason"] == "起漲時間差太大"
    assert pair_check(mk(60, 10, rets=up, bursts={3}), mk(62, 12, rets=same, bursts={4}), p)["reason"] == "沒有同時爆量"
    assert pair_check(mk(60, 10, rets=up, bursts={3}), mk(62, 12, rets=same, bursts={3}), p)["ok"]


def test_confirm_keeps_dense_cores_of_passing_pairs():
    up = [0.1, 0.3, -0.2, 0.5, 0.1] * 6
    feats = {"A": mk(60, rets=up), "B": mk(62, rets=up), "C": mk(64, rets=up), "D": mk(150, rets=up)}
    (g,) = confirm([{"members": ["A", "B", "C", "D"], "sources": [], "daily": {}}], feats, P)
    assert g["members"] == ["A", "B", "C"]  # D peaked 90 minutes later
    assert set(g["pairs"]) == {e("A", "B"), e("A", "C"), e("B", "C")}


def test_candidate_pool_and_match_known():
    rows = [
        {"code": "1", "kind": "stock", "change_pct": 9.9, "close": 10, "market_cap": 1000, "volume_shares": 10, "industry": "X"},
        {"code": "2", "kind": "stock", "change_pct": 1.0, "close": 10, "market_cap": 1000, "volume_shares": 50, "industry": "X"},
        {"code": "3", "kind": "stock", "change_pct": 5.0, "close": 10, "market_cap": 1000, "volume_shares": 1, "industry": "Y"},
        {"code": "E", "kind": "etf", "change_pct": 20.0, "close": 10, "market_cap": 1000, "volume_shares": 99, "industry": ""},
    ]
    pool = candidate_pool(rows, {"3": 9.0}, FinderParams(pool_top=1, new_min_volume_lots=0))
    assert pool == {"1": ["漲幅"], "2": ["週轉率"], "3": ["比重暴增"]}
    # the volume floor (張 = 1,000 shares): only "2" traded ≥ 0.05 張 here
    assert candidate_pool(rows, {"3": 9.0}, FinderParams(pool_top=1, new_min_volume_lots=0.05)) == {"2": ["漲幅", "週轉率"]}
    by = {r["code"]: r for r in rows}
    m = match_known(["1", "2", "3"], by, {"industry": lambda r: [r["industry"]]})
    assert m[0]["group"] == "X" and m[0]["overlap"] == pytest.approx(2 / 3) and m[0]["outside"] == ["3"]
    assert kind_of(m, 3) == "已知族群的延伸"  # 2 of 3 in X
    assert kind_of([{"overlap": 1.0, "outside": []}], 2) == "已知族群"
    assert kind_of([{"overlap": 0.5, "outside": ["b"]}], 2) == "跨族群新組合"  # a pair with one member in a group
    assert kind_of([{"overlap": 0.4, "outside": ["a", "b", "c"]}], 5) == "跨族群新組合" and kind_of([], 2) == "跨族群新組合"


def test_money_size():
    from openmarket.history.finder import money_size

    rows = {"A": {"turnover_yuan": 3e9, "change_pct": 9.9}, "B": {"turnover_yuan": 1e9, "change_pct": 4.1}}
    assert money_size(["A", "B", "Z"], rows, 4e11) == {"turnover_100m": 40.0, "turnover_share": 1.0, "avg_pct": 7.0}
    assert money_size(["A"], rows, 0)["turnover_share"] is None


def test_co_mentions():
    names = {"2327": "國巨*", "2492": "華新科", "6173": "信昌電"}
    titles = ["被動元件大漲 國巨、華新科領軍", "國巨法說會", "信昌電與華新科同步攻頂", "國巨、華新科領軍"]
    assert co_mentions(names, titles) == ["被動元件大漲 國巨、華新科領軍", "信昌電與華新科同步攻頂", "國巨、華新科領軍"]


def test_params_key_changes_with_any_threshold():
    assert FinderParams().key() != FinderParams(daily_r=0.75).key()
    assert FinderParams().key() == FinderParams().key()


def test_store_batch_bars_and_results(tmp_path):
    from datetime import datetime

    from openmarket.history.store import HistoryStore

    s = HistoryStore(tmp_path / "h.sqlite")
    d1, d2 = date(2026, 1, 2), date(2026, 1, 5)
    s.save_yahoo_1m_many([("A", d1, [("09:00", 1, 1, 1, 1, 10)]), ("B", d1, []), ("A", d2, [("09:00", 2, 2, 2, 2, 20)])])
    got = s.yahoo_1m_many(["A", "B", "C"], [d1, d2])
    assert got[("A", d1)] == [("09:00", 1, 1, 1, 1, 10)] and got[("B", d1)] == [] and ("C", d1) not in got
    s.save_finder(d1, "known", "k", {"groups": [1]})
    assert s.finder(d1, "known", "k") == {"groups": [1]} and s.finder(d1, "new", "k") is None
    s.save_day(d1, [], datetime(2026, 1, 2, 15))
    assert s.finder(d1, "known", "k") is None  # a rewritten day drops its results


def test_run_search_end_to_end(tmp_path):
    import asyncio
    import random
    from datetime import datetime, timedelta

    from openmarket.history.finder import run_search
    from openmarket.history.store import HistoryStore

    s = HistoryStore(tmp_path / "h.sqlite")
    rnd = random.Random(3)
    days = [date(2026, 3, 2) + timedelta(days=i) for i in range(28) if (date(2026, 3, 2) + timedelta(days=i)).weekday() < 5][:20]
    price = {c: 100.0 for c in "ABCDX"}
    for d in days:
        common = rnd.uniform(-4, 4)
        rows = []
        for c in "ABCDX":
            move = common + rnd.uniform(-0.3, 0.3) if c in "ABCD" else rnd.uniform(-4, 4)
            prev = price[c]
            price[c] = round(prev * (1 + move / 100), 2)
            rows.append({"code": c, "name": f"n{c}", "market": "上市", "industry": "X" if c != "X" else "Y", "kind": "stock",
                         "close": price[c], "prev_close": prev, "change": price[c] - prev, "change_pct": (price[c] / prev - 1) * 100,
                         "open": prev, "high": max(prev, price[c]) * 1.001, "low": min(prev, price[c]) * 0.999,
                         "volume_shares": 1e6, "turnover_yuan": 1e8, "market_cap": 1e10 * (1 + "ABCDX".index(c))})
        s.save_day(d, rows, datetime(2026, 3, 1))
    day = days[-1]
    sessions = days[-3:]
    peaks = {"A": 60, "B": 65, "C": 60, "D": 150}  # 5-minute bars; D peaks 90 minutes later

    async def fetch(rows, sess, done):
        out = {}
        for r in rows:
            by = {}
            for si, ss in enumerate(sess):
                bars, p = [], 100.0
                for m in range(0, 270, 5):
                    p *= 1 + (0.002 if (m // 5 + si) % 3 else -0.003)
                    hi = p * (1.05 if ss == day and m == peaks[r["code"]] else 1.0)
                    bars.append((f"{9 + m // 60:02d}:{m % 60:02d}", hi, p * 0.999, p, p, 1000.0))
                by[ss] = bars
            out[r["code"]] = (by, 5)
            done()
        return out

    seen = []
    res = asyncio.run(run_search(s, day, "known", FinderParams(daily_r=0.8, min_amplitude=0, min_volume_lots=0), {"industry": lambda r: [r["industry"]]}, fetch, progress=lambda *a: seen.append(a)))
    assert seen[0] == ("daily", 0, 1) and ("fetch", 4, 4) in seen and seen[-1] == ("intraday", 0, 1)
    assert res["stats"]["candidates"] == 1
    (g,) = res["groups"]
    assert [m["code"] for m in g["members"]] == ["A", "B", "C"]  # D dropped on the intraday-high gap
    assert g["kind"] == "已知族群" and g["peak_spread"] == 5 and g["daily_r"] > 0.8


def test_pair_r_fast_path_matches_pearson():
    from openmarket.history.finder import PairR, series_r

    s = {"A": [1.0, -2, 3, 0.5, -1], "B": [0.8, -1.5, 2.0, 1.0, -0.2], "C": [1.0, None, 3, 0.5, -1]}
    pr = PairR(s)
    assert pr("A", "B") == pytest.approx(series_r(s["A"], s["B"], 3))
    assert pr("B", "A") == pr("A", "B")
    assert pr("A", "C") == pytest.approx(series_r(s["A"], s["C"], 3))  # the gap path
