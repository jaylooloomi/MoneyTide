import asyncio
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx

from openmarket.config import TAIPEI
from openmarket.history.store import HistoryStore
from openmarket.news_themes import heat_bursts, ptt_terms, short_group_names
from openmarket.sources.ptt import clean_title, fetch_titles_since, parse_index

FIX = Path(__file__).parent / "fixtures"


def test_parse_index_skips_pinned_and_deleted_posts():
    posts, prev = parse_index((FIX / "ptt_stock_index.html").read_text(encoding="utf-8"))
    assert prev == "/bbs/Stock/index10470.html"
    assert len(posts) == 4 and all(d == date(2026, 10, 23) for d, _ in posts)  # 公告 below the separator are not posts
    assert not any("公告" in t or "刪除" in t for _, t in posts)
    assert clean_title("Re: [新聞] 台積電&amp;聯電") == "台積電&聯電"


def test_fetch_titles_walks_back_to_since():
    def page(n, day):
        epoch = int(datetime(day.year, day.month, day.day, 12, tzinfo=TAIPEI).timestamp())
        prev = f'<a class="btn wide" href="/bbs/Stock/index{n - 1}.html">&lsaquo; 上頁</a>' if n > 1 else ""
        return f'{prev}<div class="title"><a href="/bbs/Stock/M.{epoch}.A.ABC.html">[標的] 第{n}頁</a></div>'

    pages = {"/bbs/Stock/index.html": page(3, date(2026, 10, 23)),
             "/bbs/Stock/index2.html": page(2, date(2026, 10, 22)),
             "/bbs/Stock/index1.html": page(1, date(2026, 10, 20))}
    seen = []

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, text=pages[request.url.path])

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            async def no_sleep(_):
                return None
            return await fetch_titles_since(client, date(2026, 10, 22), no_sleep)

    out = asyncio.run(run())
    assert out == {date(2026, 10, 23): ["第3頁"], date(2026, 10, 22): ["第2頁"]}
    assert seen == ["/bbs/Stock/index.html", "/bbs/Stock/index2.html", "/bbs/Stock/index1.html"]  # stops after an older page


def test_ptt_terms_counts_once_per_title():
    c = ptt_terms(["CPO族群噴發 CPO 大漲", "HBM 與 ETF 熱度", "重電族群", "矽光子供應鏈"], ["矽光子"])
    assert c["CPO"] == 1 and c["HBM"] == 1 and "ETF" not in c and c["重電"] == 1 and c["矽光子"] == 1
    assert set(short_group_names({"半導體／光罩": [], "電子／其他電子": [], "其他／x": [], "AI": []})) == {"光罩", "AI"}


def test_heat_bursts_needs_history_and_flags_a_jump(tmp_path):
    s = HistoryStore(tmp_path / "h.sqlite")
    end = date(2026, 10, 23)
    days = [end - timedelta(days=i) for i in range(25)]
    assert heat_bursts(s, end, {}) == []
    by_day = {d: (["CPO族群大漲"] * 5 if i < 3 else ["台股盤整"]) + ["重電族群"] for i, d in enumerate(days)}
    s.save_ptt_days(by_day)
    out = heat_bursts(s, end, {})
    assert [b["term"] for b in out] == ["CPO"]  # 重電 is steady, so it does not burst
    assert out[0]["recent"] == 15 and out[0]["z"] >= 2
