import pytest

from openmarket.models import Quote, StockInfo
from openmarket.snapshot import build_stocks


def q(code, change, change_pct, price=100.0, week=None, amp=2.0, turnover=1.0, name=None):
    return Quote(
        code=code, name=name or code, price=price, change=change, change_pct=change_pct,
        week_pct=week, amplitude_pct=amp, open=price, high=price, low=price,
        prev_close=price, volume_lots=10, turnover_100m=turnover,
    )


INFOS = {
    "2330": StockInfo("2330", "台積電", "半導體業", "上市", "stock"),
    "2454": StockInfo("2454", "聯發科", "半導體業", "上市", "stock"),
    "2603": StockInfo("2603", "長榮", "航運業", "上市", "stock"),
    "0050": StockInfo("0050", "元大台灣50", "", "上市", "etf"),
    "6488": StockInfo("6488", "環球晶", "半導體業", "上櫃", "stock"),
}


def test_merge_classification_market_cap_and_dedupe():
    stocks = build_stocks(
        [q("2330", 10, 1.0), q("0050", 1, 0.5), q("2330", 99, 9.9)],
        INFOS,
        {"2330": 1000},
    )
    by = {s.code: s for s in stocks}
    assert list(by) == ["2330", "0050"]  # duplicates dropped, order kept
    assert by["2330"].industry == "半導體業" and by["2330"].market == "上市"
    assert by["2330"].market_cap == 100_000.0
    assert by["0050"].industry == "ETF" and by["0050"].kind == "etf"
    assert by["2330"].change == 10  # first occurrence wins


def test_codes_missing_from_isin_are_dropped_when_isin_present():
    stocks = build_stocks([q("2330", 1, 1.0), q("2456", 0, 0.0)], INFOS, {})
    assert [s.code for s in stocks] == ["2330"]


def test_fallback_classification_without_isin():
    stocks = build_stocks([q("9999", 0, 0.0), q("00999", 0, 0.0), q("2881A", 0, 0.0)], {}, {})
    by = {s.code: s for s in stocks}
    assert by["9999"].industry == "其他" and by["9999"].market == "未知" and by["9999"].kind == "stock"
    assert by["00999"].kind == "etf" and by["00999"].industry == "ETF"
    assert by["2881A"].kind == "other"


def test_market_cap_uses_prev_close_when_no_trade():
    quote = Quote("2603", "長榮", None, None, None, None, None, None, None, None, 200.0, 0, 0)
    (s,) = build_stocks([quote], INFOS, {"2603": 10})
    assert s.market_cap == 2000.0


def test_preferred_is_other_and_never_takes_common_shares():
    infos = {**INFOS, "2881A": StockInfo("2881A", "富邦特", "金融保險業", "上市", "other")}
    stocks = build_stocks([q("2881A", 1, 1.0), q("2330", 1, 1.0)], infos, {"2881": 5})
    by = {s.code: s for s in stocks}
    assert by["2881A"].kind == "other"
    assert by["2881A"].market_cap is None  # exact code match only
