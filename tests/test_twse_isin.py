from pathlib import Path

import pytest

from openmarket.models import ParseError
from openmarket.sources.twse_isin import parse_isin

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def twse():
    return parse_isin((FIX / "isin_twse.html").read_bytes())


@pytest.fixture(scope="module")
def tpex():
    return parse_isin((FIX / "isin_tpex.html").read_bytes())


def test_listed_common_stocks(twse):
    tsmc = twse["2330"]
    assert (tsmc.name, tsmc.industry, tsmc.market, tsmc.kind) == ("台積電", "半導體業", "上市", "stock")
    assert twse["2317"].industry == "其他電子業"
    assert twse["2603"].industry == "航運業"
    assert twse["1590"].name == "亞德客-KY"


def test_innovation_board_is_stock_on_listed_market(twse):
    s = twse["2254"]
    assert s.kind == "stock" and s.market == "上市" and s.industry == "汽車工業"


def test_etf_etn_and_other_sections(twse):
    assert twse["0050"].kind == "etf"
    assert twse["00631L"].kind == "etf"
    assert twse["020000"].kind == "other"  # ETN is not an ETF
    assert twse["2881A"].kind == "other"  # preferred
    assert twse["910322"].kind == "other"  # TDR
    assert twse["01001T"].kind == "other"  # REIT


def test_warrants_skipped(twse, tpex):
    assert "030001" not in twse
    assert "700019" not in tpex


def test_otc(tpex):
    s = tpex["5274"]
    assert (s.name, s.industry, s.market, s.kind) == ("信驊", "半導體業", "上櫃", "stock")
    assert tpex["006201"].kind == "etf" and tpex["006201"].market == "上櫃"


def test_header_missing_raises():
    with pytest.raises(ParseError):
        parse_isin("<html><table><tr><td>nothing</td></tr></table></html>")


def test_header_changed_raises():
    page = "<table><tr><td>有價證券代號及名稱</td><td>a</td><td>b</td><td>c</td><td>行業</td><td>d</td><td>e</td></tr></table>"
    with pytest.raises(ParseError, match="header changed"):
        parse_isin(page)


def test_cp950_only_characters_and_full_row_count(twse, tpex):
    # big5 would fail on 碁/恒 and lxml would silently truncate the page.
    assert twse["2353"].name == "宏碁"
    assert twse["2432"].name == "倚天酷碁-創"
    assert tpex["6174"].name == "安碁"
    assert tpex["8349"].name == "恒耀"
    stocks_twse = {c for c, i in twse.items() if i.kind == "stock"}
    stocks_tpex = {c for c, i in tpex.items() if i.kind == "stock"}
    assert len(stocks_twse) == 47 + 3  # 股票 + 創新板 rows in the fixture
    assert len(stocks_tpex) == 41


def test_industry_coverage(twse, tpex):
    assert len({i.industry for i in twse.values() if i.kind == "stock"}) == 32
    assert len({i.industry for i in tpex.values() if i.kind == "stock"}) == 28
