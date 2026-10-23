import asyncio
import json
from datetime import date, datetime
from pathlib import Path

import pytest

from openmarket.config import TAIPEI
from openmarket.history.ingest import HistoryCollector, build_rows
from openmarket.history.metrics import (
    clv,
    flow_baseline,
    flow_day,
    group_flows,
    industry_grouping,
    mapping_grouping,
    rotation,
    zscore,
)
from openmarket.history.store import HistoryStore
from openmarket.models import ParseError, StockInfo
from openmarket.sources.institutional import InstRow, parse_tpex_inst, parse_twse_inst
from openmarket.sources.official import DailyRow

FIX = Path(__file__).parent / "fixtures"


# ---- formulas --------------------------------------------------------------------------------

def test_clv_and_zscore():
    assert clv({"high": 110, "low": 100, "close": 110}) == 1
    assert clv({"high": 110, "low": 100, "close": 100}) == -1
    assert clv({"high": 110, "low": 100, "close": 105}) == 0
    assert clv({"high": 100, "low": 100, "close": 100}) == 0
    assert clv({"high": None, "low": 1, "close": 1}) == 0
    assert zscore(5, [1, 1, 1, 1]) == pytest.approx((5 - 1) / 0.05)  # std floor
    assert zscore(3, [1, 2, 3]) == pytest.approx((3 - 2) / (2 / 3) ** 0.5)
    assert zscore(3, [1, 2]) is None  # too little history


def row(code, close, turnover, high, low, volume=1000.0, cap=1e10, kind="stock", industry="X"):
    return {"code": code, "kind": kind, "industry": industry, "close": close, "high": high, "low": low,
            "turnover_yuan": turnover, "volume_shares": volume, "market_cap": cap}


def test_flow_day_sums_per_group_once_per_code():
    rows = [row("a", 110, 100, 110, 100), row("b", 100, 300, 110, 100, industry="Y"), row("e", 10, 999, 10, 10, kind="etf")]
    grouping = mapping_grouping({"a": ["G", "G"], "b": ["G"]})
    out = flow_day(rows, grouping, {"a": 10})
    assert out["market"] == 400  # ETF excluded
    g = out["groups"]["G"]
    assert g["turnover"] == 400 and g["mf"] == 100 * 1 + 300 * -1 and g["inst"] == 10 * 110
    assert g["shares"] == pytest.approx(1e10 / 110 + 1e10 / 100)


# ---- store-backed metrics ----------------------------------------------------------------------

INFOS = {c: StockInfo(c, c, ind, "上市", "stock") for c, ind in (("1", "熱門"), ("2", "冷門"), ("3", "冷門"))}


@pytest.fixture
def store(tmp_path):
    s = HistoryStore(tmp_path / "h.sqlite")
    now = datetime(2026, 10, 23, 16, tzinfo=TAIPEI)
    days = [date(2026, 9, d) for d in range(1, 26) if date(2026, 9, d).weekday() < 5]
    for i, d in enumerate(days):
        hot_spike = i == len(days) - 1
        rows = [
            DailyRow("1", "1", "上市", 100, 1, 99, 101, 99, 1000, 9e8, 10**7),
            DailyRow("2", "2", "上市", 50, 1, 49, 50, 48, 1000, (5e8 if hot_spike else 1e8) * (1 + (i % 3) * 0.05), 10**7),
            DailyRow("3", "3", "上市", 20, 0, 20, 20, 20, 1000, 1e7, 10**7),
        ]
        s.save_day(d, build_rows(rows, INFOS, {}), now)
    s.days_list = days
    return s


def test_group_flows_flags_a_spike_and_inst_appears_when_stored(store):
    last = store.days_list[-1]
    out = group_flows(store, last, industry_grouping)
    cold = out["冷門"]
    assert cold["z20"] > 2 and cold["share"] > 30  # 5e8 of ~1.4e9
    assert out["熱門"]["z20"] < 0
    assert cold["mf"] is not None and cold["inst_net"] is None  # no institutional data yet
    assert cold["turnover_rate"] == pytest.approx(2000 / (2 * 10**7) * 100)
    store.save_inst_day(last, [InstRow("2", 1000, 0, 0, 1000)], datetime.now(TAIPEI))
    cold = group_flows(store, last, industry_grouping)["冷門"]
    assert cold["inst_net"] == 1000 * 50 and cold["inst_ratio"] > 0
    assert group_flows(store, date(2026, 9, 27), industry_grouping) == {}  # not a stored day


def test_baseline_and_rotation(store):
    base = flow_baseline(store, industry_grouping)
    assert base["as_of"] == store.days_list[-1].isoformat() and set(base["groups"]) == {"熱門", "冷門"}
    assert base["groups"]["冷門"]["m5"] > base["groups"]["冷門"]["m20"]  # the spike day is in the last 5
    before = flow_baseline(store, industry_grouping, before=store.days_list[-1])
    assert before["as_of"] == store.days_list[-2].isoformat()  # the live day is not its own baseline
    r = rotation(store, 5, "share_z", 5)
    assert r["metric"] == "share_z" and len(r["dates"]) == 5 and r["groups"][0]["name"] == "冷門"
    assert r["groups"][0]["values"][-1] > 2


# ---- 三大法人 sources + collector ----------------------------------------------------------------

def test_parse_institutional_fixtures():
    twse = parse_twse_inst(json.loads((FIX / "inst_twse_20261022.json").read_text(encoding="utf-8")))
    first = twse[0]
    assert first.code == "1101" and first.total == 33359013 and first.trust == 4726000
    assert first.foreign == 25549325 and first.dealer == 3083688
    tpex = parse_tpex_inst(json.loads((FIX / "inst_tpex_20261022.json").read_text(encoding="utf-8")))
    assert tpex[0].code == "00411A" and tpex[0].foreign == 751700 and tpex[0].dealer == 3610418 and tpex[0].total == 4362118
    assert parse_twse_inst({"stat": "查詢日期大於可查詢最大日期，請重新查詢!"}) is None
    assert parse_tpex_inst({"tables": [{"data": []}]}) is None
    with pytest.raises(ParseError):
        parse_twse_inst({"stat": "OK", "data": [["1101", "x"]]})


def test_collector_backfills_inst_and_waits_for_today(tmp_path):
    s = HistoryStore(tmp_path / "h.sqlite")
    now = datetime(2026, 10, 22, 17, tzinfo=TAIPEI)
    for d in (date(2026, 10, 21), date(2026, 10, 22)):
        s.save_day(d, build_rows([DailyRow("1", "1", "上市", 100, 1, 99, 101, 99, 1000, 9e8, 10**7)], INFOS, {}), now)
    asked = []

    async def fetch_inst(d):
        asked.append(d)
        return None if d == date(2026, 10, 22) else [InstRow("1", 5, 0, 0, 5)]

    async def no_sleep(_):
        return None

    c = HistoryCollector(store=s, fetch_twse=None, fetch_tpex=None, reference=lambda: ({}, {}), clock=lambda: now,
                         sleep=no_sleep, fetch_inst=fetch_inst)
    asyncio.run(c.collect_inst())
    assert sorted(asked) == [date(2026, 10, 21), date(2026, 10, 22)]
    assert s.inst_dates() == {date(2026, 10, 21)}  # today's empty answer is retried later
    assert s.inst_net([date(2026, 10, 21)])[date(2026, 10, 21)] == {"1": 5}
