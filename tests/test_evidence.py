import random
from datetime import date

from openmarket.history.evidence import bucket_of, chip_sync, excess_matrix, minute_evidence, percentile_of, residuals


def test_excess_r_tells_a_shared_buyer_from_the_index():
    rnd = random.Random(1)
    idx = [rnd.gauss(0, 1) for _ in range(150)]
    flow = [rnd.gauss(0, 1) for _ in range(150)]  # money buying A and B, not the market
    a = [m + f + rnd.gauss(0, 0.3) for m, f in zip(idx, flow)]
    b = [m + f + rnd.gauss(0, 0.3) for m, f in zip(idx, flow)]
    c = [m + rnd.gauss(0, 1) for m in idx]  # only the index in common with A
    m = excess_matrix([a, b, c], [idx, idx, idx])
    assert m[0][1] > 0.8  # A and B: still alike after the index is taken out
    assert abs(m[0][2]) < 0.3  # A and C were only alike through the index
    assert excess_matrix([a, b], [idx, None])[0][1] is None  # no index series → no excess R
    assert residuals([1.0, None], [1.0, 2.0]) == [None, None]  # too few points for a β


def _bars(prices, vols):
    return [(f"{9 + i // 60:02d}:{i % 60:02d}", p, p, p, p, v) for i, (p, v) in enumerate(zip(prices, vols))]


def test_minute_evidence_bursts_and_same_minute_sync():
    rnd = random.Random(2)
    shocks = [rnd.gauss(0, 0.3) for _ in range(200)]
    pa, pb = [100.0], [50.0]
    for s in shocks:
        pa.append(pa[-1] * (1 + (s + rnd.gauss(0, 0.05)) / 100))
        pb.append(pb[-1] * (1 + (s + rnd.gauss(0, 0.05)) / 100))
    va = [100] * 201
    vb = [100] * 201
    for t in (30, 60, 90, 120):  # bursts in the same minutes
        va[t] = vb[t] = 1000
    va[150] = 1000  # A alone
    ev = minute_evidence(_bars(pa, va), _bars(pb, vb))
    assert ev["co"] == 4 and ev["bursts_a"] == 5 and ev["bursts_b"] == 4
    assert ev["expected"] < 1  # 5 × 4 / 201 by chance
    assert ev["r0"] > 0.9 and ev["r_off"] < 0.3  # alike in the same minute, not one minute apart
    assert minute_evidence(None, _bars(pb, vb)) is None


def test_baseline_percentile_buckets_and_chips():
    rnd = random.Random(3)
    pool = {f"S{i}": [rnd.gauss(0, 1) for _ in range(20)] for i in range(40)}  # unrelated stocks: R around 0
    hi = percentile_of(0.8, pool, set(), "seed")
    assert hi["pct"] >= 95 and hi["n"] >= 30
    assert percentile_of(0.8, pool, set(), "seed") == hi  # seeded: the same answer each time
    assert percentile_of(-0.5, pool, set(), "seed")["pct"] <= 10
    assert percentile_of(None, pool, set(), "seed") is None and percentile_of(0.5, {"A": [1]}, set(), "s") is None
    assert [bucket_of(x) for x in (-9.9, -3, 0, 3, 7, 9.9, None)] == [0, 1, 2, 3, 4, 5, None]
    trust = {date(2026, 3, 2): {"A": 5, "B": 3}, date(2026, 3, 3): {"A": -1, "B": -2}, date(2026, 3, 4): {"A": 1, "B": -1}}
    ch = chip_sync("A", "B", trust, {"A": 10, "B": -5}, {"A": (100, 120, 0, 0), "B": (50, 40, 0, 0)})
    assert ch == {"trust_days": 3, "trust_both_buy": 1, "trust_both_sell": 1, "inst_a": 1, "inst_b": -1, "margin_a": 1, "margin_b": -1}



def test_shared_buyers_top_five_in_both():
    from openmarket.history.evidence import shared_buyers

    a = {"buy": [{"name": "凱基-台北", "net": 466}, {"name": "元大", "net": 200}, {"name": "富邦", "net": 50}]}
    b = {"buy": [{"name": "國泰", "net": 300}] + [{"name": f"X{i}", "net": 10} for i in range(5)] + [{"name": "元大", "net": 5}, {"name": "凱基-台北", "net": 120}]}
    s = shared_buyers(a, b)
    assert [x["name"] for x in s["shared"]] == ["凱基-台北", "元大"]  # by combined rank (a tie keeps A's order)
    assert s["shared"][0] == {"name": "凱基-台北", "a_rank": 1, "a_net": 466, "b_rank": 8, "b_net": 120}
    assert s["strong"] is False  # in both lists, but not in B's top 5
    b2 = {"buy": [{"name": "國泰", "net": 300}, {"name": "凱基-台北", "net": 120}]}
    assert shared_buyers(a, b2)["strong"] is True
    assert shared_buyers(a, None) is None



def test_group_branches_common_buyers_and_majority():
    from openmarket.history.evidence import group_branches

    buy = lambda *names: {"buy": [{"name": n, "net": 100 - i} for i, n in enumerate(names)], "sell": []}  # noqa: E731
    data = {"A": buy("高盛", "野村", "元大"), "B": buy("國泰", "高盛", "凱基"), "C": buy("X1", "X2", "X3", "X4", "X5", "野村")}
    g = group_branches(["A", "B", "C"], data)
    assert [(e["name"], e["ranks"]) for e in g["common"]] == [("高盛", {"A": 1, "B": 2}), ("野村", {"A": 2, "C": 6})]
    assert g["ok"] is False  # only A–B share a top-5 buyer: 1 of 3 pairs
    assert g["have"] == 3
    assert group_branches(["A", "Z"], data) is None  # one member without 分點 data
    assert group_branches(["A", "B"], {**data, "B": {"error": "x"}}) is None



def test_concentration_top15_net_over_volume():
    from openmarket.history.evidence import concentration

    data = {"buy": [{"name": "甲", "net": 300}, {"name": "乙", "net": 200}], "sell": [{"name": "丙", "net": -100}]}
    assert concentration(data, 2_000_000) == 20.0  # (300 + 200 − 100) 張 ÷ 2,000 張
    assert concentration(data, 2_000_000, top=1) == 10.0  # (300 − 100) ÷ 2,000
    assert concentration({"buy": [], "sell": []}, 1e6) is None  # an empty page: no data, not 0%
    assert concentration(None, 1e6) is None and concentration({"error": "x"}, 1e6) is None and concentration(data, 0) is None



def test_buyer_cost_is_the_top_buyers_net_weighted_price():
    from openmarket.history.evidence import buyer_cost

    data = {"buy": [{"name": "甲", "net": 300, "avg": 50.0}, {"name": "乙", "net": 100, "avg": 54.0}, {"name": "丙", "net": 50, "avg": None}], "sell": []}
    assert buyer_cost(data) == 51.0  # (300×50 + 100×54) ÷ 400; 丙 has no price
    assert buyer_cost(data, top=1) == 50.0
    assert buyer_cost({"buy": [], "sell": []}) is None and buyer_cost(None) is None and buyer_cost({"error": "x"}) is None



def test_buy_streaks_count_back_until_a_gap():
    from openmarket.history.evidence import buy_streaks

    day = lambda *names: {"buy": [{"name": n, "net": 10} for n in names], "sell": []}  # noqa: E731
    days = [day("甲", "乙", "丙"), day("甲", "乙"), day("甲"), None, day("甲")]  # newest first; day 4 not stored
    assert buy_streaks(days) == {"甲": 3, "乙": 2, "丙": 1}  # the gap ends 甲's run
    assert buy_streaks([None, day("甲")]) == {} and buy_streaks([]) == {}



def test_foreign_branches_among_the_stored_top_15():
    from openmarket.history.evidence import foreign_branch_net, is_foreign_branch

    assert is_foreign_branch("美商高盛") and is_foreign_branch("摩根大通") and is_foreign_branch("台灣摩根士丹利")
    assert not is_foreign_branch("元大-西屯") and not is_foreign_branch("凱基-台北")
    data = {"buy": [{"name": "美商高盛", "net": 500}, {"name": "元大", "net": 300}], "sell": [{"name": "港商野村", "net": -200}]}
    assert foreign_branch_net(data) == 300
    assert foreign_branch_net({"buy": [], "sell": []}) is None and foreign_branch_net(None) is None



def test_peak_lag_says_who_moves_first():
    from openmarket.history.evidence import minute_evidence

    import math
    moves = [math.sin(i * 0.7) * (1 + (i % 5)) for i in range(200)]
    bar = lambda t, c: (f"{9 + t // 60:02d}:{t % 60:02d}", c, c, c, c, 1000)  # noqa: E731
    path = lambda xs: [bar(t, 100 + sum(xs[: t + 1])) for t in range(len(xs))]  # noqa: E731
    a = path(moves)
    b = path([0, 0] + moves[:-2])  # b repeats a two minutes later
    assert minute_evidence(a, b)["peak_lag"] == 2
    assert minute_evidence(b, a)["peak_lag"] == -2
    assert minute_evidence(a, a)["peak_lag"] == 0
