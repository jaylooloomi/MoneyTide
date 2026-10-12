import pytest

from openmarket.models import Quote, StockInfo
from openmarket.snapshot import aggregate_industries, build_stocks


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


def test_industry_cap_weighted_when_all_have_cap():
    stocks = build_stocks(
        [q("2330", 1, 2.0, price=100, week=4.0), q("2454", -1, -1.0, price=100, week=0.0)],
        INFOS,
        {"2330": 3, "2454": 1},
    )
    (semi,) = aggregate_industries(stocks)
    assert semi.change_pct == pytest.approx((2.0 * 300 - 1.0 * 100) / 400)
    assert semi.week_pct == pytest.approx(3.0)
    assert (semi.up_count, semi.down_count, semi.flat_count, semi.stock_count) == (1, 1, 0, 2)


def test_industry_equal_weight_when_any_cap_missing():
    stocks = build_stocks(
        [q("2330", 1, 2.0), q("2454", -1, -1.0), q("6488", 0, 0.0)],
        INFOS,
        {"2330": 3, "2454": 1},  # 6488 missing shares
    )
    (semi,) = aggregate_industries(stocks)
    assert semi.change_pct == pytest.approx(1.0 / 3)
    assert semi.flat_count == 1


def test_etf_excluded_by_default_and_sorted_desc():
    stocks = build_stocks(
        [q("2330", 1, 1.0), q("2603", -5, -5.0), q("0050", 1, 3.0)], INFOS, {}
    )
    names = [s.name for s in aggregate_industries(stocks)]
    assert names == ["半導體業", "航運業"]
    assert "ETF" in [s.name for s in aggregate_industries(stocks, include_etf=True)]


def test_none_values_ignored_in_averages():
    stocks = build_stocks([q("2330", None, None), q("2454", 1, 1.0)], INFOS, {})
    (semi,) = aggregate_industries(stocks)
    assert semi.change_pct == 1.0
    assert semi.flat_count == 1


def test_fallback_kind_and_other_never_aggregated():
    infos = {**INFOS, "2881A": StockInfo("2881A", "富邦特", "金融保險業", "上市", "other")}
    stocks = build_stocks([q("2881A", 1, 1.0), q("2330", 1, 1.0)], infos, {})
    by = {s.code: s for s in stocks}
    assert by["2881A"].kind == "other"
    assert [st.name for st in aggregate_industries(stocks, include_etf=True)] == ["半導體業"]
