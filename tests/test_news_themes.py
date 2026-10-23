import asyncio
import json
from datetime import date, datetime

import httpx
import pytest

from openmarket.ai import AIConfig
from openmarket.config import TAIPEI
from openmarket.history.store import HistoryStore
from openmarket.news_themes import (
    NewsThemeCollector,
    ai_prompt,
    group_members_for,
    hot_themes,
    parse_ai_themes,
    themes_for_day,
    themes_mapping,
)
from openmarket.sources.google_news import Headline
from openmarket.sources.news_themes import NameIndex, clean_theme, day_url, extract_day, themes_in

NAMES = {"2330": "台積電", "2317": "鴻海", "6285": "啟碁", "3491": "昇達科", "2313": "華通", "1101": "台泥",
         "2204": "中華", "2412": "中華電", "5521": "工信", "2882": "國泰金"}


# ---- extraction ---------------------------------------------------------------------------------

@pytest.mark.parametrize(("title", "themes"), [
    ("台股開高強彈近800點！台積電領軍五大權值股走揚 低軌衛星族群升空 - 經濟日報", ["低軌衛星"]),
    ("台積股漲台股開盤續揚重返47K PCB、玻纖布族群強勢", ["玻纖布", "PCB"]),
    ("AI伺服器供應鏈營收上修，矽光子與折疊機題材強勢輪動", ["AI伺服器", "折疊機"]),
    ("【12:48 即時新聞】工信(5521)盤中小幅走高，營建族群人氣為多方焦點", ["營建"]),
    ("三大法人爆砍千億　「這族群」淪重災區", []),
    ("【最新消息】公股投信整併拍板，「7檔概念股」同步轉強！", []),
    ("A股CPO概念股集體下跌，新易盛大跌超9%", []),
    ("美股早盤 SpaceX與美超微業績提振AI類股", []),
])
def test_themes_in(title, themes):
    assert themes_in(title) == themes


def test_clean_theme_strips_lead_words_and_rejects_noise():
    assert clean_theme("台股熱門重電") == "重電"
    assert clean_theme("3檔") is None
    assert clean_theme("高風險") is None
    assert clean_theme("x") is None


def test_name_index_prefers_longer_names_and_codes():
    idx = NameIndex.build(NAMES)
    assert idx.find("中華電與台積電齊揚") == ["2412", "2330"]  # 中華電, not 中華
    assert idx.find("中華(2204)反彈") == ["2204"]  # the common 2-char name only with its code
    assert idx.find("沒有股票") == []


def H(title, url="https://x/1"):
    return Headline(title, "來源", url, datetime(2026, 10, 22, 10, tzinfo=TAIPEI))


def test_extract_day_counts_mentions_and_co_mentions():
    idx = NameIndex.build(NAMES)
    out = extract_day([
        H("低軌衛星族群升空 啟碁、昇達科大漲"),
        H("低軌衛星供應鏈迎巨頭，華通與昇達科籌碼現分歧", "https://x/2"),
        H("台股收紅"),
    ], idx)
    assert set(out) == {"低軌衛星"}
    t = out["低軌衛星"]
    assert t["mentions"] == 2 and t["codes"] == {"6285": 1, "3491": 2, "2313": 1} and len(t["titles"]) == 2


def test_day_url():
    url = day_url("概念股", date(2026, 10, 22))
    assert "after%3A2026-10-22" in url and "before%3A2026-10-23" in url


# ---- rolling list -----------------------------------------------------------------------------

def day(**themes):
    return {n: {"mentions": m, "codes": codes, "titles": [{"title": n, "source": "s", "url": "https://x"}]} for n, (m, codes) in themes.items()}


def test_hot_themes_window_trend_and_thresholds():
    days = [
        day(低軌衛星=(3, {"6285": 2, "3491": 1, "2313": 1}), 重電=(1, {"1101": 1})),
        day(低軌衛星=(1, {"3491": 1})),
        day(),
        day(低軌衛星=(1, {"3491": 1})),  # the previous window
    ]
    out = hot_themes(days, None, {}, {})
    assert [t["name"] for t in out] == ["低軌衛星"]  # 重電: 1 mention and 1 member → dropped
    t = out[0]
    assert t["score"] == 4 and t["prev_score"] == 1 and t["codes"] == ["6285", "3491", "2313"]
    # a same-named concept group lends its members
    borrowed = hot_themes([day(重電=(2, {"1101": 1}))], None, {"重電": ["1503", "1513", "1519"]}, {})
    assert borrowed[0]["codes"] == ["1101", "1503", "1513", "1519"]
    assert group_members_for("光罩", {"半導體／光罩": ["2338"]}) == ["2338"]


def test_hot_themes_with_ai_merges_aliases_and_members():
    days = [day(CPO=(2, {"3363": 1}), 矽光子=(2, {"3450": 1}))]
    ai = [{"name": "矽光子", "aliases": ["CPO"], "members": ["聯亞"]}]
    out = hot_themes(days, ai, {}, {"聯亞": "3081"})
    assert out[0]["name"] == "矽光子" and out[0]["score"] == 4
    assert set(out[0]["codes"]) == {"3363", "3450", "3081"} and out[0]["aliases"] == ["CPO"]
    assert themes_mapping(out) == {"3450": ["矽光子"], "3363": ["矽光子"], "3081": ["矽光子"]}


def test_ai_prompt_and_parse():
    prompt = ai_prompt([day(低軌衛星=(3, {"6285": 2}))], NAMES)
    assert "低軌衛星（3 則）" in prompt and "啟碁" in prompt
    themes = parse_ai_themes('```json\n[{"name": "低軌/衛星", "aliases": ["衛星"], "members": ["啟碁", "不存在"]}]\n```', {"啟碁": "6285"})
    assert themes == [{"name": "低軌／衛星", "aliases": ["衛星"], "members": ["啟碁"]}]
    with pytest.raises(ValueError):
        parse_ai_themes("沒有", {})


# ---- collector + store + API ------------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    from openmarket.history.ingest import build_rows
    from openmarket.models import StockInfo
    from openmarket.sources.official import DailyRow

    s = HistoryStore(tmp_path / "h.sqlite")
    infos = {c: StockInfo(c, n, "X", "上市", "stock") for c, n in NAMES.items()}
    for d in (date(2026, 10, 21), date(2026, 10, 22)):
        rows = [DailyRow(c, n, "上市", 110, 10 if c in ("6285", "3491") else 1, 100, 110, 100, 1, 5e8, None) for c, n in NAMES.items()]
        s.save_day(d, build_rows(rows, infos, {}), datetime(2026, 10, 22, 16, tzinfo=TAIPEI))
    return s


def test_collector_backfills_then_cleans_latest_with_ai(store):
    fetched = []

    async def fetch_day(d):
        fetched.append(d)
        return [H("低軌衛星族群升空 啟碁、昇達科大漲"), H("低軌衛星供應鏈 華通與昇達科", "https://x/2")]

    ai_calls = []

    def handler(request):
        ai_calls.append(1)
        body = '[{"name": "低軌衛星", "aliases": [], "members": ["啟碁", "華通", "昇達科", "鴻海"]}]'
        return httpx.Response(200, json={"choices": [{"message": {"content": body}}]})

    async def no_sleep(_):
        return None

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            c = NewsThemeCollector(store=store, fetch_day=fetch_day, reference=lambda: NAMES,
                                   ai_config=AIConfig.from_env({"OPENMARKET_AI_KEY": "k"}), http=http,
                                   clock=lambda: datetime(2026, 10, 23, 9, tzinfo=TAIPEI), sleep=no_sleep)
            await c.run_once()
            first = (c.state.done, c.state.total)
            await c.run_once()  # nothing pending, AI already done
            return first

    done, total = asyncio.run(go())
    assert sorted(fetched) == [date(2026, 10, 21), date(2026, 10, 22)] and (done, total) == (2, 2)
    assert len(ai_calls) == 1 and store.news_ai(date(2026, 10, 22))[0]["name"] == "低軌衛星"
    used, themes, method = themes_for_day(store, date(2026, 10, 22), {}, NAMES)
    assert used == date(2026, 10, 22) and method == "ai" and themes[0]["score"] == 4
    assert "2317" in themes[0]["codes"]  # the AI-added member, validated against the listing
    used, themes, method = themes_for_day(store, date(2026, 10, 21), {}, NAMES)
    assert method == "keyword" and themes[0]["name"] == "低軌衛星"


def test_api_news_endpoints_and_grouping(store, tmp_path):
    from fastapi.testclient import TestClient

    from openmarket.api import create_app
    from openmarket.config import AppConfig
    from openmarket.history.ingest import build_rows  # noqa: F401
    from openmarket.sources.news_themes import NameIndex as NI

    store.save_news_day(date(2026, 10, 22), extract_day([H("低軌衛星族群升空 啟碁、昇達科、華通大漲"), H("低軌衛星供應鏈 昇達科", "https://x/2")], NI.build(NAMES)), 2)

    class P:  # a poller stand-in: only the ISIN names are needed
        infos = {c: type("I", (), {"name": n, "kind": "stock"})() for c, n in NAMES.items()}

    app = create_app(AppConfig(data_dir=tmp_path), poller=P(), start_polling=False, start_history=False, start_concepts=False,
                     history_store=store)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/api/news-themes/status").json()["ready"] is True
        body = client.get("/api/news-themes?date=2026-10-22").json()
        t = body["themes"][0]
        assert body["news_date"] == "2026-10-22" and body["method"] == "keyword"
        assert t["name"] == "低軌衛星" and t["score"] == 2 and t["avg_pct"] is not None
        assert {m["name"] for m in t["members"]} == {"啟碁", "昇達科", "華通"}
        groups = client.get("/api/history/groups?date=2026-10-22&grouping=news").json()["groups"]
        assert [g["name"] for g in groups] == ["低軌衛星"] and groups[0]["count"] == 3
        assert client.get("/api/groupings/news").json()["mapping"]["3491"] == ["低軌衛星"]
        assert client.get("/api/news-themes?date=bad").status_code == 422
