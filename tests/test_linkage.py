import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from openmarket.config import TAIPEI
from openmarket.history.ingest import build_rows
from openmarket.history.linkage import (
    bucket_closes,
    daily_linkage,
    fmt_minute,
    group_r20,
    pair_matrix,
    peak_minute_from_bars,
    peak_minute_from_ticks,
    peak_stats,
    pearson,
    returns,
    top_members,
    verdict_r,
    verdict_timing,
)
from openmarket.history.metrics import industry_grouping
from openmarket.history.store import HistoryStore
from openmarket.intraday import IntradayRecorder
from openmarket.models import Snapshot, StockInfo
from openmarket.sources.official import DailyRow
from openmarket.sources.yahoo_intraday import parse_chart, symbol_for

FIX = Path(__file__).parent / "fixtures"


def test_pearson_and_matrix():
    assert pearson([1, 2, 3], [2, 4, 6]) == pytest.approx(1)
    assert pearson([1, 2, 3], [3, 2, 1]) == pytest.approx(-1)
    assert pearson([1, 1, 1], [1, 2, 3]) is None
    m, mean = pair_matrix([[1, 2, 3, None], [2, 4, 6, 8], [3, 2, 1, 0]], min_points=3)
    assert m[0][1] == pytest.approx(1) and m[0][2] == pytest.approx(-1) and m[1][1] == 1.0
    assert mean == pytest.approx((1 - 1 - 1) / 3, abs=1e-3)  # rounded to 3 decimals
    assert pair_matrix([[1, 2], [1, 2]], min_points=3)[1] is None


def test_verdicts_and_peaks():
    assert verdict_r(0.8) == "群體圍攻" and verdict_r(0.2) == "單兵作戰" and verdict_r(0.5) == "中度連動" and verdict_r(None) == "資料不足"
    assert verdict_r(0.45, 0.5, 0.2) == "中度連動"
    assert verdict_timing(5) == "高度同步" and verdict_timing(70) == "時間錯落" and verdict_timing(30) == "普通"
    assert peak_minute_from_ticks([("09:01:00", 10), ("09:15:30", 12), ("10:00:00", 12)]) == 15
    assert peak_minute_from_bars([("09:00", 10, 9, 9.5), ("09:05", 11, 10, 10.5), ("09:10", 11, 10, 10)]) == 5
    assert peak_stats([15, 17, 19]) == (pytest.approx(1.6, abs=0.1), 3.0)
    assert peak_stats([15, None]) == (None, None)
    assert fmt_minute(75) == "10:15" and fmt_minute(None) is None


def test_buckets_and_returns_stay_within_a_session():
    closes = bucket_closes([("09:00:30", 100), ("09:04:59", 101), ("09:05:10", 102), ("09:12:00", 103)])
    assert closes == {0: 101, 1: 102, 2: 103}
    r = returns(closes, [0, 1, 2, 3])
    assert r[0] == pytest.approx((102 / 101 - 1) * 100) and r[2] is None


def test_yahoo_parse_and_symbol():
    days = parse_chart(json.loads((FIX / "yahoo_5m_2330_TW.json").read_text()))
    last = days[max(days)]
    assert last[0][0] == "09:00" and len(last) >= 50 and all(len(b) == 4 for b in last)
    assert symbol_for("6488", "上櫃") == "6488.TWO" and symbol_for("2330", "上市") == "2330.TW"


INFOS = {c: StockInfo(c, c, "G", "上市", "stock") for c in ("A", "B", "C")}


@pytest.fixture
def store(tmp_path):
    s = HistoryStore(tmp_path / "h.sqlite")
    now = datetime(2026, 10, 23, 16, tzinfo=TAIPEI)
    start = date(2026, 8, 3)
    days = [start + timedelta(days=i) for i in range(90) if (start + timedelta(days=i)).weekday() < 5][:61]
    for i, d in enumerate(days):
        move = 1 if i % 2 else -1
        rows = [
            DailyRow("A", "A", "上市", 100 + move, move, 100, 101, 99, 1, 1e8, 10**9),  # A and B move together
            DailyRow("B", "B", "上市", 50 + move / 2, move / 2, 50, 51, 49, 1, 1e8, 10**8),
            DailyRow("C", "C", "上市", 20 - move / 5 if i % 3 else 20 + move / 5, (-move if i % 3 else move) / 5, 20, 21, 19, 1, 1e8, 10**7),
        ]
        s.save_day(d, build_rows(rows, INFOS, {}), now)
    s.days_list = days
    return s


def test_daily_linkage_and_group_r20(store):
    d = store.days_list[-1]
    members = top_members(store.day_rows(d), industry_grouping, "G")
    assert [m["code"] for m in members] == ["A", "B", "C"]  # by market cap
    out = daily_linkage(store, d, ["A", "B"])
    assert out["r20"] == pytest.approx(1) and out["r60"] == pytest.approx(1) and len(out["matrix20"]) == 2
    r = group_r20(store, d, industry_grouping)["G"]
    assert -1 <= r < 1  # C breaks the lockstep


def test_recorder_records_session_polls_once(tmp_path):
    s = HistoryStore(tmp_path / "h.sqlite")
    from openmarket.models import Stock

    stock = Stock("A", "A", 10.5, 0.5, 5, 0, 0, 10, 11, 10, 10, 1, 1, "G", "上市", "stock", 1e9)

    class P:
        snapshot = Snapshot(version=3, as_of="2026-10-22T10:15:00+08:00", status="ok", market_open=True, stocks=[stock])

    rec = IntradayRecorder(store=s, get_poller=lambda: P)
    assert rec.record_once() is True and rec.record_once() is False  # same version
    assert s.ticks(date(2026, 10, 22), {"A"}) == {"A": [("10:15:00", 10.5)]}
    P.snapshot = Snapshot(version=4, as_of="2026-10-22T15:00:00+08:00", status="ok", stocks=[stock])
    assert rec.record_once() is False  # after the session


def test_linkage_api_uses_cached_bars(store, tmp_path):
    from fastapi.testclient import TestClient

    from openmarket.api import create_app
    from openmarket.config import AppConfig

    d = store.days_list[-1]
    sessions = store.days_list[-3:]
    now = datetime.now(TAIPEI)
    for code, base in (("A", 100), ("B", 50), ("C", 20)):
        bars = {s: [(f"{9 + k // 12:02d}:{(k % 12) * 5:02d}", base * (1 + 0.01 * ((k % 7) - 3)) + 1, base, base * (1 + 0.01 * ((k % 7) - 3))) for k in range(54)] for s in sessions}
        store.save_yahoo_bars(code, bars, now)  # fresh: the endpoint must not call Yahoo
    app = create_app(AppConfig(data_dir=tmp_path), start_polling=False, start_history=False, start_concepts=False, history_store=store)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        body = client.get("/api/history/linkage", params={"date": d.isoformat(), "group": "G"}).json()
        assert [m["code"] for m in body["members"]] == ["A", "B", "C"]
        assert body["daily"]["r20"] is not None and body["intraday"]["r"] == pytest.approx(1)  # identical shapes
        assert all(s["source"] == "yahoo" for s in body["intraday"]["sessions"])
        assert body["peak_std_min"] == 0 and body["verdict"]["timing"] == "高度同步" and body["notes"] == []
        assert client.get("/api/history/linkage", params={"date": d.isoformat(), "group": "nope"}).status_code == 404
        flows = client.get("/api/history/flows", params={"date": d.isoformat()}).json()["groups"]
        assert "r20" in flows["G"]
