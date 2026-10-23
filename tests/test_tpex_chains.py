import asyncio
from pathlib import Path

import httpx
import pytest

from openmarket.models import ParseError
from openmarket.sources.tpex_chains import clean_name, fetch_chains, merge_chains, parse_chain_index, parse_chain_page

FIX = Path(__file__).parent / "fixtures"
INDEX = (FIX / "tpex_chain_index.html").read_text(encoding="utf-8")
SEMI = (FIX / "tpex_chain_D000.html").read_text(encoding="utf-8")


def test_clean_name():
    assert clean_name("IP設計<br/>/IC設計 代工") == "IP設計／IC設計 代工"
    assert clean_name("<span>&#9658;</span>&nbsp;LED驅動IC&nbsp;(12家)") == "LED驅動IC"
    assert clean_name("A,B") == "A、B"


def test_index_lists_all_chains():
    chains = parse_chain_index(INDEX)
    assert len(chains) == 40
    assert chains[0] == ("D000", "半導體")
    assert ("J000", "被動元件") in chains


def test_chain_page_uses_finest_level_and_skips_repeats():
    groups = parse_chain_page(SEMI, "半導體")
    # plain list → "<chain>／<sub>"
    assert groups["半導體／光罩"] == ["2338", "2438"]
    # split list → "<sub>／<finer>"
    assert "IC設計／電源管理IC" in groups and "2454" in groups["IC設計／電源管理IC"]
    assert "半導體／IC設計" not in groups
    # the fixture repeats the first list: members are not duplicated
    first = groups["半導體／IP設計／IC設計代工服務"]
    assert len(first) == len(set(first)) and "3443" in first
    # foreign companies without a Taiwan code are not members
    assert all(c.isalnum() for codes in groups.values() for c in codes)


def test_merge_prefixes_names_taken_by_another_chain():
    merged = merge_chains([("A鏈", {"其他／X": ["1"]}), ("B鏈", {"其他／X": ["2"], "B鏈／Y": ["3"]})])
    assert merged == {"其他／X": ["1"], "B鏈／其他／X": ["2"], "B鏈／Y": ["3"]}


def test_fetch_chains_walks_every_chain():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.path == "/":
            return httpx.Response(200, text=INDEX)
        return httpx.Response(200, text=SEMI)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            async def no_sleep(_):
                return None
            return await fetch_chains(client, sleep=no_sleep)

    groups = asyncio.run(run())
    assert len(seen) == 41
    assert "IC設計／電源管理IC" in groups and "被動元件／光罩" in groups  # same page under another chain → prefixed


def test_fetch_chains_rejects_a_changed_index():
    async def run():
        transport = httpx.MockTransport(lambda r: httpx.Response(200, text="<html></html>"))
        async with httpx.AsyncClient(transport=transport) as client:
            async def no_sleep(_):
                return None
            await fetch_chains(client, sleep=no_sleep)

    with pytest.raises(ParseError):
        asyncio.run(run())
