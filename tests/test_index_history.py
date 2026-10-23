import json
from datetime import date, datetime
from pathlib import Path

import pytest

from openmarket.config import TAIPEI
from openmarket.history.api import index_timeline
from openmarket.history.ingest import build_rows, index_months_to_fetch, index_window
from openmarket.history.store import HistoryStore
from openmarket.models import ParseError, StockInfo
from openmarket.sources.official import DailyRow
from openmarket.sources.official_index import (
    IndexRow,
    merge_tpex,
    merge_twse,
    parse_date,
    parse_tpex_ohlc,
    parse_tpex_turnover,
    parse_twse_ohlc,
    parse_twse_turnover,
)

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_parse_date_roc_and_ad():
    assert parse_date("115/09/01") == date(2026, 9, 1)
    assert parse_date("2026/09/30") == date(2026, 9, 30)
    with pytest.raises(ParseError):
        parse_date("2026-09-01")


def test_twse_month_parses_and_merges():
    ohlc = parse_twse_ohlc(load("index_twse_ohlc_202609.json"))
    turnover = parse_twse_turnover(load("index_twse_turnover_202609.json"))
    assert len(ohlc) == 20 and len(turnover) == 20
    assert ohlc[date(2026, 9, 1)] == (46177.11, 46948.72, 46081.11, 46948.72)
    assert turnover[date(2026, 9, 1)] == (1187571567117.0, 820.25)
    rows = merge_twse(ohlc, turnover)
    assert rows[0] == IndexRow(date(2026, 9, 1), "上市", 46177.11, 46948.72, 46081.11, 46948.72, 820.25, 1187571567117.0)
    assert rows[-1].date == date(2026, 9, 30)


def test_tpex_month_parses_thousands_of_yuan():
    ohlc = parse_tpex_ohlc(load("index_tpex_ohlc_202609.json"))
    turnover = parse_tpex_turnover(load("index_tpex_turnover_202609.json"))
    assert ohlc[date(2026, 9, 1)] == (402.12, 412.90, 402.12, 410.77, 9.07)
    assert turnover[date(2026, 9, 1)] == (252387965 * 1000, 9.07)
    rows = merge_tpex(ohlc, turnover)
    assert len(rows) == 20 and rows[0].market == "上櫃" and rows[0].turnover_yuan == 252387965000


def test_empty_months_and_bad_rows():
    assert parse_twse_ohlc({"stat": "很抱歉，沒有符合條件的資料!"}) == {}
    assert parse_tpex_ohlc({"stat": "ok", "tables": [{"data": []}]}) == {}
    assert parse_tpex_turnover({"tables": []}) == {}
    with pytest.raises(ParseError):
        parse_twse_turnover({"stat": "OK", "data": [["115/09/01", "1"]]})
    # one side missing → the other side's values with NULLs
    rows = merge_twse({}, {date(2026, 9, 1): (5.0, 1.0)})
    assert rows[0].close is None and rows[0].turnover_yuan == 5.0


def test_index_window_and_due_months():
    now = datetime(2026, 10, 23, 16, 0, tzinfo=TAIPEI)
    window = index_window(now)
    assert window[0] == "2026-10" and window[-1] == "2025-10" and len(window) == 13
    due = index_months_to_fetch({}, now)
    assert len(due) == 26 and due[0] == ("上市", "2026-10")

    fetched_old = datetime(2026, 10, 5, 12, 0, tzinfo=TAIPEI)
    fetched = {(m, mo): fetched_old for mo in window for m in ("上市", "上櫃")}
    # September was fetched after its last close; October before today's close → only October
    assert index_months_to_fetch(fetched, now) == [("上市", "2026-10"), ("上櫃", "2026-10")]
    # fetched after today's 15:30 → nothing due
    after = {k: datetime(2026, 10, 23, 15, 45, tzinfo=TAIPEI) for k in fetched}
    assert index_months_to_fetch(after, now) == []
    # before today's close the latest needed close is yesterday's
    morning = datetime(2026, 10, 23, 10, 0, tzinfo=TAIPEI)
    yesterday_evening = {k: datetime(2026, 10, 22, 16, 0, tzinfo=TAIPEI) for k in fetched}
    assert index_months_to_fetch(yesterday_evening, morning) == []
    # September fetched on Sept 30 morning (before its final close) → due once more
    stale_sep = dict(after)
    stale_sep[("上櫃", "2026-09")] = datetime(2026, 9, 30, 9, 0, tzinfo=TAIPEI)
    assert index_months_to_fetch(stale_sep, now) == [("上櫃", "2026-09")]


INFOS = {
    "1101": StockInfo("1101", "台泥", "水泥工業", "上市", "stock"),
    "2330": StockInfo("2330", "台積電", "半導體業", "上市", "stock"),
    "0050": StockInfo("0050", "元大台灣50", "", "上市", "etf"),
}


def drow(code, close, change):
    return DailyRow(code, code, "上市", close, change, close, close, close, 1000, 1e8, None)


@pytest.fixture
def store(tmp_path):
    s = HistoryStore(tmp_path / "h.sqlite")
    now = datetime(2026, 10, 23, 16, 0, tzinfo=TAIPEI)
    # 1101 +10%, 2330 +1%, 0050 (ETF, excluded) +10%
    s.save_day(date(2026, 9, 1), build_rows([drow("1101", 110, 10), drow("2330", 101, 1), drow("0050", 110, 10)], INFOS, {}), now)
    s.save_day(date(2026, 9, 2), build_rows([drow("1101", 110, 0), drow("2330", 101, 0)], INFOS, {}), now)
    return s


def test_store_index_month_replace_and_read(store):
    now = datetime(2026, 10, 23, 16, 0, tzinfo=TAIPEI)
    rows = merge_twse(parse_twse_ohlc(load("index_twse_ohlc_202609.json")), parse_twse_turnover(load("index_twse_turnover_202609.json")))
    store.save_index_month("上市", "2026-09", rows, now)
    store.save_index_month("上市", "2026-09", rows[:3], now)  # re-fetch replaces the month
    data = store.index_rows()
    assert len(data) == 3 and data["2026-09-01"]["上市"]["close"] == 46948.72
    assert store.index_months() == {("上市", "2026-09"): now}


def test_daily_strength_counts_common_stocks_only(store):
    s = store.daily_strength(5, 9.5)
    assert s["2026-09-01"] == {"strong_ratio": 50.0, "limit_up": 1}
    assert s["2026-09-02"] == {"strong_ratio": 0.0, "limit_up": 0}
    assert store.daily_strength(5, 9.5) is s  # cached


def test_index_timeline_unions_days_and_marks_missing(store):
    now = datetime(2026, 10, 23, 16, 0, tzinfo=TAIPEI)
    store.save_index_month("上櫃", "2026-09", [IndexRow(date(2026, 9, 1), "上櫃", 1, 2, 0.5, 1.5, 0.5, 9e9),
                                              IndexRow(date(2026, 9, 3), "上櫃", 1, 2, 0.5, 1.6, 0.1, 8e9)], now)
    out = index_timeline(store, 250)["days"]
    assert [d["date"] for d in out] == ["2026-09-01", "2026-09-02", "2026-09-03"]
    assert out[0]["twse"] is None and out[0]["tpex"]["close"] == 1.5 and out[0]["strong_ratio"] == 50.0
    assert out[1]["tpex"] is None and out[1]["has_stocks"] is True
    assert out[2]["has_stocks"] is False and out[2]["limit_up"] is None
    assert [d["date"] for d in index_timeline(store, 2)["days"]] == ["2026-09-02", "2026-09-03"]


def test_market_index_route_is_not_shadowed(store):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openmarket.history.api import create_history_router

    app = FastAPI()
    app.include_router(create_history_router(lambda: store, lambda: None))
    body = TestClient(app).get("/api/history/market-index?days=10").json()
    assert [d["date"] for d in body["days"]] == ["2026-09-01", "2026-09-02"]
    assert body["backfill"]["months_total"] == 26 and body["backfill"]["running"] is False
