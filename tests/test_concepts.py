import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest

from openmarket.concepts import ConceptLoader
from openmarket.config import TAIPEI
from openmarket.models import ParseError
from openmarket.sources import yahoo_concepts as yc
from openmarket.storage import JsonCache

FIX = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 23, 10, 0, tzinfo=TAIPEI)


def test_parse_index_only_concepts():
    names = yc.parse_concept_index((FIX / "yahoo_class_index.html").read_text(encoding="utf-8"))
    assert "AI人工智慧" in names and len(names) >= 90
    assert "水泥" not in names  # industry sector link, not a concept
    assert len(names) == len(set(names))


def test_parse_page():
    payload = json.loads((FIX / "yahoo_class_quotes.json").read_text(encoding="utf-8"))
    codes, nxt = yc.parse_concept_page(payload)
    assert nxt is None and len(codes) == 2 and all(c.isdigit() for c in codes)
    codes, nxt = yc.parse_concept_page({"list": [{"symbol": "2330.TW"}, {"symbol": "6488.TWO"}, {"symbol": "^TWII"}],
                                        "pagination": {"nextOffset": "30"}})
    assert codes == ["2330", "6488"] and nxt == 30
    with pytest.raises(ParseError):
        yc.parse_concept_page({"nope": 1})


def test_fetch_concepts_paginates_and_skips_failures(monkeypatch):
    monkeypatch.setattr(yc, "MIN_CONCEPTS", 2)
    index = "".join(f'<a href="/class-quote?category={n}&amp;categoryLabel=概念股">{n}</a>' for n in ("A", "B", "C"))

    def handler(req: httpx.Request):
        url = str(req.url)
        if url.endswith("/class"):
            return httpx.Response(200, text=index)
        from urllib.parse import unquote
        u = unquote(url)
        if "categoryName=C" in u:
            return httpx.Response(500)
        if "categoryName=A" in u and "offset=0" in u:
            return httpx.Response(200, json={"list": [{"symbol": "2330.TW"}], "pagination": {"nextOffset": "30"}})
        if "categoryName=A" in u:
            return httpx.Response(200, json={"list": [{"symbol": "3017.TW"}], "pagination": {"nextOffset": None}})
        return httpx.Response(200, json={"list": [{"symbol": "2330.TW"}], "pagination": {"nextOffset": None}})

    async def no_sleep(_):
        return None

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            monkeypatch.setattr("openmarket.sources.http.HTTP_RETRY_DELAY_SECONDS", 0)
            return await yc.fetch_concepts(client, sleep=no_sleep)

    out = asyncio.run(go())
    assert out == {"A": ["2330", "3017"], "B": ["2330"]}
    assert yc.code_to_concepts(out) == {"2330": ["A", "B"], "3017": ["A"]}


def make_loader(tmp_path, fetch, now=NOW):
    return ConceptLoader(cache=JsonCache(tmp_path / "c.json"), fetch=fetch, clock=lambda: now)


def test_loader_refresh_cache_and_retry(tmp_path):
    calls = []

    async def fetch(progress):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("down")
        progress(1, 1)
        return {"散熱": ["3017", "3324"]}

    loader = make_loader(tmp_path, fetch)
    assert loader.due(NOW)
    asyncio.run(loader.refresh())
    assert loader.status()["ready"] is False and "down" in loader.error
    assert not loader.due(NOW + timedelta(minutes=30))  # retry at most hourly
    assert loader.due(NOW + timedelta(hours=1))
    asyncio.run(loader.refresh())
    assert loader.mapping == {"3017": ["散熱"], "3324": ["散熱"]} and loader.error == ""
    fresh = make_loader(tmp_path, fetch)
    fresh.load_cache()
    assert fresh.status()["count"] == 1 and not fresh.due(NOW + timedelta(days=6))
    assert fresh.due(NOW + timedelta(days=7))


def test_loader_ignores_bad_cache(tmp_path):
    (tmp_path / "c.json").write_text('{"saved_at": "2026-10-23T10:00:00", "data": [1, 2]}', encoding="utf-8")

    async def fetch(progress):
        return {}

    loader = make_loader(tmp_path, fetch)
    loader.load_cache()
    assert loader.concepts == {}
