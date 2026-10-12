import json
from pathlib import Path

import pytest

from openmarket.models import ParseError
from openmarket.sources.shares import parse_tpex_shares, parse_twse_shares

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_twse_shares():
    shares = parse_twse_shares(load("shares_twse.json"))
    assert shares["2330"] == 25_932_370_067
    assert shares["2881"] == 14_007_364_952  # common only, preferred excluded
    assert "9105" not in shares and "910322" not in shares  # TDRs skipped


def test_tpex_shares():
    shares = parse_tpex_shares(load("shares_tpex.json"))
    assert shares["5274"] == 41_582_953
    assert shares["6488"] == 478_113_725


def test_wrong_shape_raises():
    with pytest.raises(ParseError):
        parse_twse_shares({"not": "a list"})
    with pytest.raises(ParseError):
        parse_tpex_shares([{"code": "1234"}])


def test_empty_list_ok():
    assert parse_tpex_shares([]) == {}


def test_fetch_rejects_partial_payload():
    import asyncio

    import httpx

    from openmarket.sources.shares import fetch_shares

    def handler(request):
        return httpx.Response(200, json=[])

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await fetch_shares(client)

    with pytest.raises(ParseError, match="partial"):
        asyncio.run(go())
