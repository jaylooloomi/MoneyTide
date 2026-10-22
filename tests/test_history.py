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
