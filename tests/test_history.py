import asyncio
from datetime import date, datetime

import pytest

from openmarket.config import TAIPEI
from openmarket.history.ingest import HistoryCollector, build_rows
from openmarket.history.metrics import day_stocks, group_stats, movers, rotation
from openmarket.history.store import HistoryStore
from openmarket.models import StockInfo
from openmarket.sources.official import DailyRow

INFOS = {
    "2330": StockInfo("2330", "台積電", "半導體業", "上市", "stock"),
    "2454": StockInfo("2454", "聯發科", "半導體業", "上市", "stock"),
    "2603": StockInfo("2603", "長榮", "航運業", "上市", "stock"),
    "2609": StockInfo("2609", "陽明", "航運業", "上市", "stock"),
    "0050": StockInfo("0050", "元大台灣50", "", "上市", "etf"),
}
NOW = datetime(2026, 10, 23, 16, 0, tzinfo=TAIPEI)  # Friday after close


def row(code, close, change, market="上市", shares=None, high=None, low=None):
    return DailyRow(code, code, market, close, change, close, high or close, low or close, 1000, 1e8, shares)


def test_build_rows_derives_prev_pct_cap_and_skips_unknown():
    rows = build_rows(
        [row("2330", 110, 10), row("9999", 10, 1), row("0050", 50, 1), row("2603", None, None, shares=5)],
        INFOS, {"2330": 1000, "0050": 99},
    )
    by = {r["code"]: r for r in rows}
    assert "9999" not in by
    assert by["2330"]["prev_close"] == 100 and by["2330"]["change_pct"] == 10
    assert by["2330"]["market_cap"] == 110_000 and by["2330"]["industry"] == "半導體業"
    assert by["0050"]["market_cap"] is None and by["0050"]["kind"] == "etf"
    assert by["2603"]["change_pct"] is None and by["2603"]["market_cap"] is None


@pytest.fixture
def store(tmp_path):
    s = HistoryStore(tmp_path / "h.sqlite")
    days = [date(2026, 10, d) for d in (14, 15, 16, 19, 20, 21)]
    # 2603 rises 10 every day, 2330 flat, 2454 falls, 2609 jumps 10% on the last day
    for i, d in enumerate(days):
        s.save_day(d, build_rows([
            row("2330", 100, 0),
            row("2454", 100 - i, -1),
            row("2603", 100 + 10 * i, 10),
            row("2609", 110 if i == len(days) - 1 else 100, 10 if i == len(days) - 1 else 0, high=110, low=100),
            row("0050", 50, 5),
        ], INFOS, {c: 10 for c in INFOS}), NOW)
    s.mark_no_data(date(2026, 10, 13), NOW)
    return s


def test_store_days_and_trading_dates(store):
    assert store.days()[date(2026, 10, 13)] == "no_data"
    assert store.trading_dates(limit=2) == [date(2026, 10, 21), date(2026, 10, 20)]
    assert len(store.day_rows(date(2026, 10, 21))) == 5


def test_save_day_replaces(store):
    store.save_day(date(2026, 10, 21), build_rows([row("2330", 100, 0)], INFOS, {}), NOW)
    assert [r["code"] for r in store.day_rows(date(2026, 10, 21))] == ["2330"]


def test_group_stats(store):
    stats = {g["name"]: g for g in group_stats(store.day_rows(date(2026, 10, 21)), threshold=5)}
    ship = stats["航運業"]
    assert ship["count"] == 2 and ship["strong_count"] == 2 and ship["strong_ratio"] == 100
    assert ship["limit_up"] == 1 and ship["up"] == 2 and ship["breadth"] == 100
    semi = stats["半導體業"]
    assert semi["strong_ratio"] == 0 and semi["up"] == 0 and semi["down"] == 1 and semi["breadth"] == 0
    assert "ETF" not in stats and "" not in stats
    assert list(stats)[0] == "航運業"  # sorted by strong_ratio


def test_rotation(store):
    rot = rotation(store, days=3, metric="strong_ratio", threshold=5)
    assert rot["dates"] == ["2026-10-19", "2026-10-20", "2026-10-21"]
    ship = next(g for g in rot["groups"] if g["name"] == "航運業")
    assert ship["values"] == [50, 50, 100]
    assert rot["groups"][0]["name"] == "航運業"
    with pytest.raises(ValueError):
        rotation(store, days=3, metric="nope", threshold=5)


def test_day_stocks_shape_and_week_pct(store):
    stocks = {s["code"]: s for s in day_stocks(store, date(2026, 10, 21))}
    s = stocks["2603"]
    assert s["price"] == 150 and s["week_pct"] == pytest.approx(50)
    assert stocks["2609"]["amplitude_pct"] == pytest.approx(10)
    assert s["turnover_100m"] == 1 and s["volume_lots"] == 1
    assert day_stocks(store, date(2026, 10, 18)) == []  # weekend


def test_movers_modes(store):
    day = movers(store, date(2026, 10, 21), "day", 5)
    assert {g["name"] for g in day["groups"]} == {"航運業"}
    assert [s["code"] for s in day["groups"][0]["stocks"]] == ["2609", "2603"]

    # base = close before 10/16 (10/15: 110) → 150 = +36%; 2609 only +10%
    rng = movers(store, date(2026, 10, 21), "range", 30, start=date(2026, 10, 16))
    assert [s["code"] for g in rng["groups"] for s in g["stocks"]] == ["2603"]
    streak = movers(store, date(2026, 10, 21), "streak", 5)
    assert [s["code"] for g in streak["groups"] for s in g["stocks"]] == ["2603"]
    with pytest.raises(ValueError):
        movers(store, date(2026, 10, 21), "bogus", 1)


class FakeFetch:
    def __init__(self, data):
        self.data = data
        self.calls = []

    async def __call__(self, d):
        self.calls.append(d)
        v = self.data.get(d, None)
        if isinstance(v, Exception):
            raise v
        return v


def collector(tmp_path, twse, tpex, now=NOW, infos=INFOS):
    async def no_sleep(_):
        return None

    return HistoryCollector(
        store=HistoryStore(tmp_path / "c.sqlite"), fetch_twse=twse, fetch_tpex=tpex,
        reference=lambda: (infos, {}), clock=lambda: now, sleep=no_sleep, request_delay=0,
    )


def test_pending_days_skip_weekends_known_and_today_before_ready(tmp_path):
    c = collector(tmp_path, FakeFetch({}), FakeFetch({}), now=datetime(2026, 10, 23, 10, 0, tzinfo=TAIPEI))
    pending = c.pending_days(c._clock())
    assert pending[0] == date(2026, 10, 22)  # today not ready before 15:30
    assert all(d.weekday() < 5 for d in pending)
    assert 255 <= len(pending) <= 262


def test_collect_holiday_today_not_ready_and_errors(tmp_path):
    d_ok, d_holiday, d_err = date(2026, 10, 22), date(2026, 10, 21), date(2026, 10, 20)
    twse = FakeFetch({d_ok: [row("2330", 100, 1)], d_err: RuntimeError("blocked"), date(2026, 10, 23): [row("2330", 1, 0)]})
    tpex = FakeFetch({d_ok: [row("2603", 50, 1, market="上櫃", shares=10)]})
    c = collector(tmp_path, twse, tpex)
    assert asyncio.run(c.collect_day(d_ok)) == "ok"
    assert asyncio.run(c.collect_day(d_holiday)) == "no_data"
    assert asyncio.run(c.collect_day(date(2026, 10, 23))) == "not_ready"  # TPEx not out yet at 16:00
    with pytest.raises(RuntimeError):
        asyncio.run(c.collect_day(d_err))
    days = c.store.days()
    assert days[d_ok] == "ok" and days[d_holiday] == "no_data" and d_err not in days
    assert {r["code"]: r["market_cap"] for r in c.store.day_rows(d_ok)}["2603"] == 500


def test_run_once_resumes_and_waits_for_reference(tmp_path):
    twse, tpex = FakeFetch({}), FakeFetch({})
    c = collector(tmp_path, twse, tpex, infos={})
    asyncio.run(c.run_once())
    assert twse.calls == []  # no ISIN classification yet
    c._reference = lambda: (INFOS, {})
    asyncio.run(c.run_once())
    first = len(twse.calls)
    assert first > 200 and c.state.done == c.state.total and not c.state.running
    asyncio.run(c.run_once())
    assert len(twse.calls) == first + 1  # only today (not_ready) is retried


def test_custom_grouping_multi_membership_and_any_kind(store):
    from openmarket.history.metrics import mapping_grouping

    grouping = mapping_grouping({"2603": ["貨櫃", "我的觀察"], "2609": ["貨櫃"], "0050": ["我的觀察"]})
    stats = {g["name"]: g for g in group_stats(store.day_rows(date(2026, 10, 21)), 5, grouping)}
    assert stats["貨櫃"]["count"] == 2 and stats["我的觀察"]["count"] == 2  # ETF allowed in custom groups
    assert "半導體業" not in stats
    rot = rotation(store, days=2, metric="avg_pct", threshold=5, grouping=grouping)
    assert {g["name"] for g in rot["groups"]} == {"貨櫃", "我的觀察"}
    stocks = day_stocks(store, date(2026, 10, 21), grouping)
    assert sorted((s["code"], s["industry"]) for s in stocks) == [
        ("0050", "我的觀察"), ("2603", "我的觀察"), ("2603", "貨櫃"), ("2609", "貨櫃")]
    mv = movers(store, date(2026, 10, 21), "day", 5, grouping=grouping)
    assert {g["name"] for g in mv["groups"]} == {"貨櫃", "我的觀察"}


def test_stock_history(store):
    from openmarket.history.metrics import stock_history

    h = stock_history(store, "2603", date(2026, 10, 21), days=3)
    assert [p["date"] for p in h["series"]] == ["2026-10-19", "2026-10-20", "2026-10-21"]
    assert h["close"] == 150 and h["period_pct"] == pytest.approx((150 / 130 - 1) * 100)
    assert h["industry"] == "航運業" and h["turnover_100m"] == 1
    assert stock_history(store, "2603", date(2026, 10, 18)) is None  # not a stored day for that date
    assert stock_history(store, "9999", date(2026, 10, 21)) is None


def test_group_index(store):
    from openmarket.history.metrics import group_index

    idx = group_index(store, days=3, up_to=date(2026, 10, 21))
    assert idx["dates"] == ["2026-10-19", "2026-10-20", "2026-10-21"]
    ship = next(s for s in idx["series"] if s["name"] == "航運業")
    # 2603 prev closes 120/130/140 (+10 each day), 2609 flat then +10% → daily equal-weight averages
    exp, level = [], 1.0
    for v in ((10 / 120 * 100) / 2, (10 / 130 * 100) / 2, (10 / 140 * 100 + 10) / 2):
        level *= 1 + v / 100
        exp.append((level - 1) * 100)
    assert ship["values"] == pytest.approx(exp, rel=1e-4)
    assert idx["series"][0]["name"] == "航運業"  # top by period return
    assert len(idx["market"]) == 3
    picked = group_index(store, days=3, up_to=date(2026, 10, 21), names=["半導體業"])
    assert [s["name"] for s in picked["series"]] == ["半導體業"]


def test_group_leader(store):
    stats = {g["name"]: g for g in group_stats(store.day_rows(date(2026, 10, 21)), threshold=5)}
    assert stats["航運業"]["leader"] == {"code": "2609", "name": "2609", "change_pct": 10.0}
    assert stats["半導體業"]["leader"]["code"] == "2330"  # 0% beats -1%


def test_group_periods(store):
    from openmarket.history.metrics import group_periods

    p = group_periods(store, date(2026, 10, 21), periods=(3, 6, 10))
    ship = p["航運業"]
    exp, level = [], 1.0
    for v in ((10 / 120 * 100) / 2, (10 / 130 * 100) / 2, (10 / 140 * 100 + 10) / 2):
        level *= 1 + v / 100
    assert ship["perf_3"] == pytest.approx((level - 1) * 100, rel=1e-4)
    assert ship["perf_6"] is not None and ship["perf_10"] is None  # only 6 stored days
    assert "ETF" not in p and "" not in p


def test_day_stocks_period_20(tmp_path):
    from datetime import timedelta

    s = HistoryStore(tmp_path / "p.sqlite")
    d0 = date(2026, 9, 1)
    days = []
    d = d0
    while len(days) < 22:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    for i, day in enumerate(days):
        s.save_day(day, build_rows([row("2330", 100 + i, 1)], INFOS, {}), NOW)
    out = {x["code"]: x for x in day_stocks(s, days[-1])}
    # 21 stored days before the last one; 20 trading days back = days[-21] (close 101)
    assert out["2330"]["period_20"] == pytest.approx((121 / 101 - 1) * 100)
    assert out["2330"]["week_pct"] == pytest.approx((121 / 116 - 1) * 100)
    early = {x["code"]: x for x in day_stocks(s, days[10])}
    assert early["2330"]["period_20"] is None


def test_daily_breadth(store):
    cal = {d["date"]: d for d in store.daily_breadth()}
    assert "2026-10-13" not in cal  # no_data day
    last = cal["2026-10-21"]
    # stocks only (0050 ETF excluded): 2330 flat, 2454 down, 2603 up, 2609 up
    assert (last["up"], last["down"], last["count"]) == (2, 1, 4)
    assert last["avg_pct"] == pytest.approx((0 + (-1 / 96 * 100) + (10 / 140 * 100) + 10) / 4, rel=1e-4)


def test_daily_group_avgs_cache_and_invalidation(store):
    from openmarket.history.metrics import daily_group_avgs, group_periods, industry_grouping

    days = sorted(store.trading_dates())
    first = daily_group_avgs(store, days, industry_grouping)
    assert ("industry", days[-1]) in store.derived_cache
    again = daily_group_avgs(store, days, industry_grouping)
    assert again == first
    before = group_periods(store, days[-1], periods=(3,))["航運業"]["perf_3"]
    # rewriting a day clears derived results, so new numbers are picked up
    store.save_day(days[-1], build_rows([row("2603", 200, 50), row("2609", 100, 0)], INFOS, {}), NOW)
    assert store.derived_cache == {}
    after = group_periods(store, days[-1], periods=(3,))["航運業"]["perf_3"]
    assert after != before

    uncached = lambda r: ["X"] if r.get("kind") == "stock" else []  # no cache_key → not cached
    daily_group_avgs(store, days, uncached)
    assert not any(k[0] is None for k in store.derived_cache)


def test_group_turnover_avg(store):
    avg = store.group_turnover_avg(days=3)
    assert avg["as_of"] == "2026-10-21" and avg["days"] == 3
    # every stock row has turnover 1e8 per day; 航運業 has 2 listed stocks
    assert avg["avg"]["航運業"]["上市"] == pytest.approx(2e8)
    assert "ETF" not in avg["avg"] and "" not in avg["avg"]
    assert store.group_turnover_avg(days=3) is avg  # cached


def test_daily_group_avgs_survives_concurrent_clear(store, monkeypatch):
    from openmarket.history.metrics import daily_group_avgs, industry_grouping

    days = sorted(store.trading_dates())
    daily_group_avgs(store, days[:-1], industry_grouping)  # cache all but the last day
    real = store.change_rows

    def clearing(ds):
        store.derived_cache.clear()  # a save_day on another thread lands mid-request
        return real(ds)

    monkeypatch.setattr(store, "change_rows", clearing)
    out = daily_group_avgs(store, days, industry_grouping)
    assert len(out) == len(days)


def test_group_rank_change(store):
    from openmarket.history.metrics import group_rank_change

    rc = group_rank_change(store, date(2026, 10, 21))
    # 10/20: 航運 avg (10/130*100+0)/2≈3.85 > 半導體 avg (0 + -1/97*100)/2≈-0.52 → same order on 10/21
    assert rc["航運業"] == {"rank": 1, "rank_change": 0}
    assert rc["半導體業"] == {"rank": 2, "rank_change": 0}
    first = group_rank_change(store, date(2026, 10, 14))
    assert first["航運業"]["rank_change"] is None  # no previous day
    assert group_rank_change(store, date(2026, 10, 18)) == {}  # not a trading day
