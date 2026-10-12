from pathlib import Path

import pytest

from openmarket.models import ParseError
from openmarket.sources.histock import parse_number, parse_rank

FIX = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("▲210.00", 210.0),
        ("▼-35.00", -35.0),
        ("+1.20%", 1.2),
        ("-3.11%", -3.11),
        ("1,691", 1691.0),
        ("37.513", 37.513),
        ("--", None),
        ("", None),
        ("abc", None),
    ],
)
def test_parse_number(text, expected):
    assert parse_number(text) == expected


def test_parse_fixture():
    quotes = parse_rank((FIX / "histock_rank_all.html").read_bytes())
    assert len(quotes) > 100
    by = {q.code: q for q in quotes}
    q = by["5274"]
    assert q.name == "信驊"
    assert q.price == 17695 and q.change == 210.0 and q.change_pct == 1.2
    assert q.week_pct == -9.35 and q.amplitude_pct == 6.55
    assert (q.open, q.high, q.low, q.prev_close) == (17445, 18080, 16935, 17485)
    assert q.volume_lots == 212 and q.turnover_100m == 37.513
    # odd codes survive as strings
    assert "00878" in by and "2881A" in by and "910322" in by


def test_flat_rows_derive_zero_change():
    by = {q.code: q for q in parse_rank((FIX / "histock_rank_all.html").read_bytes())}
    flat = by["3563"]  # 牧德: "--" with price == 昨收
    assert flat.change == 0.0 and flat.change_pct == 0.0
    assert flat.week_pct == -4.82


def test_missing_header_raises():
    with pytest.raises(ParseError, match="漲跌幅"):
        parse_rank((FIX / "histock_rank_broken.html").read_bytes())


def test_no_table_raises():
    with pytest.raises(ParseError):
        parse_rank(b"<html><body><p>maintenance</p></body></html>")
