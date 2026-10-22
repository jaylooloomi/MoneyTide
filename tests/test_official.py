import json
from pathlib import Path

import pytest

from openmarket.models import ParseError
from openmarket.sources.official import parse_tpex_day, parse_twse_day

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_twse_day():
    rows = parse_twse_day(load("twse_day.json"))
    assert len(rows) > 1000
    by = {r.code: r for r in rows}
    etf = by["0050"]
    assert etf.close == 62.70 and etf.change == -0.50 and etf.market == "上市"
    assert etf.volume_shares == 124_303_290 and etf.turnover_yuan == 7_767_140_110
    assert any(r.change is None and r.close is not None for r in rows)  # 'X' ex-rights
    assert any(r.close is None for r in rows)  # no trade
    assert any(r.change == 0.0 for r in rows)  # flat


def test_tpex_day():
    rows = parse_tpex_day(load("tpex_day.json"))
    assert len(rows) > 900
    by = {r.code: r for r in rows}
    b = by["00679B"]
    assert b.close == 27.90 and b.change == 0.19 and b.shares == 8_987_692_000 and b.market == "上櫃"
    assert by["00981B"].change is None  # 除息
    assert by["2235"].close is None and by["2235"].change is None  # no trade


def test_holidays_are_none():
    assert parse_twse_day(load("twse_holiday.json")) is None
    assert parse_tpex_day(load("tpex_holiday.json")) is None


def test_errors():
    with pytest.raises(ParseError):
        parse_twse_day({"stat": "查詢日期大於今日"})
    with pytest.raises(ParseError):
        parse_tpex_day({"tables": []})
    with pytest.raises(ParseError, match="收盤價"):
        parse_twse_day({"stat": "OK", "tables": [{"title": "每日收盤行情", "fields": ["證券代號"], "data": []}]})
