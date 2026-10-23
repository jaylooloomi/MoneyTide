import asyncio
import json
from datetime import date, datetime
from pathlib import Path

import httpx
import pytest

from openmarket.ai import ANTHROPIC_VERSION, AIConfig, AIError, complete, strip_reasoning
from openmarket.config import TAIPEI
from openmarket.explain import NO_NEWS, build_prompt, explain_day, parse_answer, select_movers
from openmarket.history.store import HistoryStore
from openmarket.sources.google_news import Headline, news_url, parse_rss

FIX = Path(__file__).parent / "fixtures"
KEY = "sk-test-secret-123"
DAY = date(2026, 10, 22)


def run(coro):
    return asyncio.run(coro)


async def no_sleep(_):
    return None


# ---- configuration ------------------------------------------------------------------------------

def test_config_defaults_and_public_view_hide_the_key():
    cfg = AIConfig.from_env({"OPENMARKET_AI_KEY": KEY})
    assert (cfg.format, cfg.base_url, cfg.model) == ("openai", "https://api.groq.com/openai/v1", "qwen/qwen3-32b")
    assert cfg.configured and KEY not in json.dumps(cfg.public())
    claude = AIConfig.from_env({"OPENMARKET_AI_FORMAT": "anthropic", "OPENMARKET_AI_KEY": KEY})
    assert claude.base_url == "https://api.anthropic.com" and claude.model == "claude-opus-5-5"
    assert not AIConfig.from_env({}).configured
    assert AIConfig.from_env({"OPENMARKET_AI_FORMAT": "weird"}).format == "openai"
    proxy = AIConfig.from_env({"OPENMARKET_AI_FORMAT": "anthropic", "OPENMARKET_AI_BASE_URL": "http://127.0.0.1:8082/", "OPENMARKET_AI_KEY": "x"})
    assert proxy.base_url == "http://127.0.0.1:8082"


def test_strip_reasoning():
    assert strip_reasoning("<think>hmm\nlong</think>\n答案") == "答案"
    assert strip_reasoning("<think>never closed") == ""


# ---- provider calls -----------------------------------------------------------------------------

def call(cfg, handler, **kw):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await complete(client, cfg, "SYS", "USER", sleep=no_sleep, **kw)
    return run(go())


def test_openai_format_request_and_answer():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "<think>x</think>好的"}}]})

    cfg = AIConfig.from_env({"OPENMARKET_AI_KEY": KEY})
    assert call(cfg, handler) == "好的"
    assert seen["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert seen["auth"] == f"Bearer {KEY}"
    assert seen["body"]["messages"][0] == {"role": "system", "content": "SYS"}


def test_anthropic_format_request_answer_and_refusal():
    seen = {}

    def handler(request):
        seen["headers"] = request.headers
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"stop_reason": "end_turn", "content": [
            {"type": "thinking", "thinking": ""}, {"type": "text", "text": "原因"}]})

    cfg = AIConfig.from_env({"OPENMARKET_AI_FORMAT": "anthropic", "OPENMARKET_AI_KEY": KEY})
    assert call(cfg, handler) == "原因"
    assert seen["headers"]["x-api-key"] == KEY and seen["headers"]["anthropic-version"] == ANTHROPIC_VERSION
    body = seen["body"]
    assert body["system"] == "SYS" and body["model"] == "claude-opus-5-5" and "temperature" not in body
    assert body["fallbacks"] == "default" and seen["headers"]["anthropic-beta"] == "server-side-fallback-2026-07-01"

    proxy = AIConfig.from_env({"OPENMARKET_AI_FORMAT": "anthropic", "OPENMARKET_AI_BASE_URL": "http://127.0.0.1:8082", "OPENMARKET_AI_KEY": "x"})
    call(proxy, handler)
    assert "fallbacks" not in seen["body"] and "anthropic-beta" not in seen["headers"]

    with pytest.raises(AIError, match="拒絕"):
        call(cfg, lambda r: httpx.Response(200, json={"stop_reason": "refusal", "content": []}))


def test_retries_transient_errors_but_not_bad_requests():
    cfg = AIConfig.from_env({"OPENMARKET_AI_KEY": KEY})
    codes = iter([429, 503, 200])
    attempts = []

    def flaky(request):
        attempts.append(1)
        code = next(codes)
        return httpx.Response(code, json={"choices": [{"message": {"content": "ok"}}]} if code == 200 else {})

    assert call(cfg, flaky) == "ok" and len(attempts) == 3

    attempts.clear()

    def down(request):
        attempts.append(1)
        return httpx.Response(500, text=f"echo {KEY}")

    with pytest.raises(AIError) as err:
        call(cfg, down)
    assert len(attempts) == 3 and KEY not in str(err.value)

    attempts.clear()

    def unauthorized(request):
        attempts.append(1)
        return httpx.Response(401)

    with pytest.raises(AIError, match="401"):
        call(cfg, unauthorized)
    assert len(attempts) == 1

    with pytest.raises(AIError, match="未設定"):
        call(AIConfig.from_env({}), unauthorized)


# ---- news -------------------------------------------------------------------------------------

def test_news_url_and_rss_parsing():
    url = news_url("台積電", "2330", DAY)
    assert "after%3A2026-10-20" in url and "before%3A2026-10-25" in url and "ceid=TW%3Azh-Hant" in url
    items = parse_rss((FIX / "google_news_2330.xml").read_text(encoding="utf-8"), DAY)
    assert 1 <= len(items) <= 8
    assert all(h.url.startswith("https://") and h.published for h in items)
    assert all(abs((h.published.date() - DAY).days) <= 2 for h in items)
    assert not any(h.source and h.title.endswith(" - " + h.source) for h in items)
    assert items == sorted(items, key=lambda h: h.published, reverse=True)
    assert parse_rss("not xml", DAY) == []
    # outside the window → dropped
    assert parse_rss((FIX / "google_news_2330.xml").read_text(encoding="utf-8"), date(2025, 1, 1)) == []


# ---- selection, prompt, answer parsing --------------------------------------------------------

def stock(code, pct, turnover=5.0, kind="stock"):
    return {"code": code, "name": f"n{code}", "kind": kind, "industry": "X", "change_pct": pct, "turnover_100m": turnover}


def test_select_movers_filters_and_orders():
    rows = [stock("a", 10), stock("b", 9), stock("c", 8), stock("d", 7), stock("thin", 10, 0.5), stock("etf", 10, kind="etf"),
            stock("a", 10), stock("x", -9.9), stock("y", -3), stock("z", None), stock("flat", 0)]
    m = select_movers(rows)
    assert [s["code"] for s in m["gainers"]] == ["a", "b", "c"]
    assert [s["code"] for s in m["losers"]] == ["x", "y"]


def headlines(n=3):
    return [Headline(f"標題{i}", "來源", f"https://example.com/{i}", datetime(2026, 10, 22, 9, i, tzinfo=TAIPEI)) for i in range(1, n + 1)]


def test_prompt_and_answer_parsing():
    prompt = build_prompt(stock("2330", -2.5), DAY, headlines(2))
    assert "下跌 2.50%" in prompt and "1. [10/22 09:01｜來源] 標題1" in prompt
    reason, links = parse_answer('```json\n{"reason": "因為標題2", "sources": [2]}\n```', headlines())
    assert reason == "因為標題2" and [l["url"] for l in links] == ["https://example.com/2"]
    assert parse_answer('{"reason": "INSUFFICIENT", "sources": []}', headlines()) == (NO_NEWS, [])
    reason, links = parse_answer("純文字回答", headlines())
    assert reason == "純文字回答" and len(links) == 3
    reason, links = parse_answer('{"reason": "x", "sources": [9]}', headlines())  # bad index → first headlines
    assert len(links) == 3


# ---- orchestration + cache --------------------------------------------------------------------

def test_explain_day_caches_and_skips_the_ai_without_news(tmp_path):
    store = HistoryStore(tmp_path / "h.sqlite")
    cfg = AIConfig.from_env({"OPENMARKET_AI_KEY": KEY})
    ai_calls = []

    def handler(request):
        ai_calls.append(json.loads(request.content)["messages"][1]["content"])
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"reason": "利多", "sources": [1]}'}}]})

    async def fetch(name, code, day):
        if code == "fail":
            raise httpx.ConnectError("down")
        return [] if code == "quiet" else headlines(2)

    rows = [stock("a", 9), stock("quiet", 8), stock("fail", 7), stock("b", -9)]

    async def go(run_ai):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await explain_day(store, http, cfg, fetch, DAY, rows, run=run_ai)

    peek = run(go(False))
    assert not ai_calls and all(r["reason"] is None for r in peek["gainers"] + peek["losers"]) and not peek["analyzed"]

    out = run(go(True))
    by = {r["code"]: r for r in out["gainers"] + out["losers"]}
    assert by["a"]["reason"] == "利多" and by["a"]["links"][0]["url"] == "https://example.com/1"
    assert by["quiet"]["reason"] == NO_NEWS and by["fail"]["error"] and by["fail"]["reason"] is None
    assert len(ai_calls) == 2  # a and b; the quiet stock never reaches the AI
    assert set(store.ai_reasons(DAY)) == {"a", "quiet", "b"}  # the failure is not cached

    again = run(go(True))
    assert len(ai_calls) == 2 + 0  # cached ones are not asked again; "fail" retries the news only
    assert {r["code"] for r in again["gainers"] + again["losers"] if r["cached"]} == {"a", "quiet", "b"}


# ---- HTTP API ----------------------------------------------------------------------------------

def make_app(tmp_path, ai_env, transport=None, fetcher=None):
    from fastapi.testclient import TestClient

    from openmarket.api import create_app
    from openmarket.config import AppConfig
    from openmarket.history.ingest import build_rows
    from openmarket.models import StockInfo
    from openmarket.sources.official import DailyRow

    store = HistoryStore(tmp_path / "h.sqlite")
    infos = {c: StockInfo(c, f"n{c}", "半導體業", "上市", "stock") for c in ("2330", "2303", "1101")}
    rows = [DailyRow("2330", "n2330", "上市", 110, 10, 100, 110, 100, 1, 5e8, None),
            DailyRow("2303", "n2303", "上市", 90, -10, 100, 100, 90, 1, 5e8, None),
            DailyRow("1101", "n1101", "上市", 100, 0, 100, 100, 100, 1, 5e8, None)]
    store.save_day(DAY, build_rows(rows, infos, {}), datetime(2026, 10, 22, 16, 0, tzinfo=TAIPEI))
    app = create_app(AppConfig(data_dir=tmp_path), start_polling=False, start_history=False, start_concepts=False,
                     history_store=store, ai_config=AIConfig.from_env(ai_env), ai_transport=transport, headline_fetcher=fetcher)
    return TestClient(app, base_url="http://127.0.0.1"), store


def test_api_guards_and_history_flow(tmp_path):
    async def fetcher(client, name, code, day):
        return headlines(1)

    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"choices": [{"message": {"content": '{"reason": "測試", "sources": [1]}'}}]}))
    client, store = make_app(tmp_path, {"OPENMARKET_AI_KEY": KEY}, transport, fetcher)
    with client:
        assert client.get("/api/ai/status").json()["configured"] is True
        assert KEY not in client.get("/api/ai/status").text
        assert client.post("/api/ai/reasons?date=2026-10-22").status_code == 403  # no header → no paid call
        peek = client.get("/api/ai/reasons?date=2026-10-22").json()
        assert [r["code"] for r in peek["gainers"]] == ["2330"] and peek["gainers"][0]["reason"] is None
        out = client.post("/api/ai/reasons?date=2026-10-22", headers={"X-OpenMarket-Action": "explain"}).json()
        assert out["gainers"][0]["reason"] == "測試" and out["losers"][0]["code"] == "2303" and out["analyzed"]
        assert client.get("/api/ai/reasons?date=2026-10-22").json()["gainers"][0]["cached"] is True
        assert client.get("/api/ai/reasons?date=2026-10-23").status_code == 404
        assert client.get("/api/ai/reasons?date=bad").status_code == 422


def test_api_without_key_explains_nothing(tmp_path):
    client, _ = make_app(tmp_path, {})
    with client:
        assert client.get("/api/ai/status").json()["configured"] is False
        r = client.post("/api/ai/reasons?date=2026-10-22", headers={"X-OpenMarket-Action": "explain"})
        assert r.status_code == 400 and "OPENMARKET_AI_KEY" in r.json()["detail"]
        assert client.get("/api/ai/reasons?date=2026-10-22").status_code == 200  # cached view still works
