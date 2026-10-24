import asyncio
from datetime import datetime, timedelta

from openmarket.config import TAIPEI
from openmarket.history.store import HistoryStore
from openmarket.relations import NameIndex, RelationCollector, norm_name, relation_edges, relation_groups
from openmarket.sources.moneydj import BoardSeat, Investment, parse_board, parse_investments

# made-up pages in MoneyDJ's shape (the real pages are not kept in the repo)
INVEST_HTML = """<table><tr><td class="t10" colspan="7">甲科(1111)轉投資</td></tr>
<tr><TD class="t2">轉投資事業</TD><TD class="t2">投資幣別</TD><TD class="t2">投資成本</TD><TD class="t2">持股股數</TD><TD class="t2">持股比例</TD><TD class="t2">帳面價值(台幣)</TD><TD class="t2">會計原則</TD></TR>
<TR><TD class="t3t1">乙電子                    </TD><TD class="t3t1"></TD><TD class="t3n1">N/A</TD><TD class="t3n1">9,882</TD><TD class="t3n1">19.07%</TD><TD class="t3n1">438,267</TD><TD class="t3t1">綜合公允   </TD></TR>
<TR><TD class="t3t1">丙科技</TD><TD class="t3t1">台幣</TD><TD class="t3n1">737,506</TD><TD class="t3n1">33,408</TD><TD class="t3n1">29.69%</TD><TD class="t3n1">776,721</TD><TD class="t3t1">權益法</TD></TR>
<TR><TD class="t3t1">Foo Holdings (BVI)</TD><TD class="t3t1">台幣</TD><TD class="t3n1">945</TD><TD class="t3n1">30</TD><TD class="t3n1">100.00%</TD><TD class="t3n1">956</TD><TD class="t3t1">權益法</TD></TR>
</table>"""

BOARD_HTML = """<table><tr><td colspan="6">甲科(1111)董監事經理人持股明細</td></tr>
<tr><td>職稱▲</td><td>姓名/法人名稱</td><td>持股張數▲</td><td>持股比例</td><td>質押張數</td><td>質押比率</td></tr>
<tr><td>董事長</td><td>丙科技(股)-王小明</td><td>26,016</td><td>18.88%</td><td>0</td><td>0.00%</td></tr>
<tr><td>獨立董事</td><td>李大華</td><td>0</td><td>0.00%</td><td>0</td><td>0.00%</td></tr>
<tr><td>監察人</td><td>丁投資股份有限公司代表人：陳一</td><td>500</td><td>0.36%</td><td>0</td><td>0.00%</td></tr>
<tr><td>＊持股張數，按持有股數四捨五入至"張"數。</td></tr>
<tr><td>甲科(1111)申報轉讓</td></tr>
<tr><td>日期</td><td>申報人</td><td>身份</td><td>申報張數</td><td>轉讓方式</td></tr>
<tr><td>115/06/11</td><td>乙電子(股)</td><td>董事</td><td>600</td><td>一般交易</td></tr>
</table>"""


def test_parse_moneydj_pages():
    inv = parse_investments(INVEST_HTML)
    assert [(x.name, x.pct, x.method) for x in inv] == [("乙電子", 19.07, "綜合公允"), ("丙科技", 29.69, "權益法"), ("Foo Holdings (BVI)", 100.0, "權益法")]
    assert inv[0].cost is None and inv[1].shares == 33408
    board = parse_board(BOARD_HTML)
    assert [(x.title, x.corp, x.pct) for x in board] == [("董事長", "丙科技", 18.88), ("獨立董事", None, 0.0), ("監察人", "丁投資", 0.36)]
    assert len(board) == 3  # the 申報轉讓 table after the footnote is not part of it


def test_names_edges_and_groups():
    assert norm_name("東元電機股份有限公司") == norm_name("東元電機") == "東元電機"
    assert norm_name("臺灣水泥 (股)") == "台灣水泥"
    idx = NameIndex.build({"1111": "甲科股份有限公司", "2222": "乙電子股份有限公司", "3333": "丙科技股份有限公司"}, {"1111": "甲科", "2222": "乙電", "3333": "丙科"})
    assert idx.code("乙電子") == "2222" and idx.code("丙科技(股)") == "3333" and idx.code("Foo Holdings (BVI)") is None
    invest = {"1111": [{"name": "乙電子", "pct": 19.07, "method": "綜合公允"}, {"name": "丙科技", "pct": 29.69, "method": "權益法"}, {"name": "Foo", "pct": 100, "method": "權益法"}]}
    board = {"1111": [{"corp": "丙科技", "pct": 18.88, "title": "董事長"}, {"corp": "丁投資", "pct": 0.36, "title": "監察人"}]}
    edges = relation_edges(invest, board, idx, ["1111", "2222", "3333"])
    assert [(e["src"], e["dst"], e["kind"]) for e in edges] == [("1111", "2222", "invest"), ("1111", "3333", "invest"), ("3333", "1111", "board")]
    groups = relation_groups(edges, {"1111": 100, "2222": 50, "3333": 300})
    # each holds the other (a 29.69% 權益法 stake / a board seat): a tie, so the larger market cap leads
    assert groups["1111"]["leader"] == "3333" and groups["1111"]["members"] == ["3333", "1111"]
    more = relation_groups(edges + [{"src": "1111", "dst": "2222", "kind": "board", "pct": 5, "title": "董事"}], {"1111": 100, "2222": 50, "3333": 300})
    assert more["1111"]["leader"] == "1111"  # now 1111 holds two members: it leads despite the smaller cap
    from openmarket.relations import merge_edges

    merged = merge_edges(edges + [{"src": "3333", "dst": "1111", "kind": "board", "pct": 18.88, "title": "董事"}])
    assert [(m["src"], m["dst"], m["pct"], m["method"], m["seats"]) for m in merged] == [
        ("1111", "2222", 19.07, "綜合公允", []), ("1111", "3333", 29.69, "權益法", []), ("3333", "1111", 18.88, "", ["董事長", "董事"])]
    assert "2222" not in groups  # a 19% fair-value stake is a relation, not a group membership


def test_store_and_collector_pause_after_failures(tmp_path):
    s = HistoryStore(tmp_path / "h.sqlite")
    now = datetime(2026, 10, 24, 12, tzinfo=TAIPEI)
    calls, slept = [], []

    async def fetch(code):
        calls.append(code)
        if code.startswith("X"):
            raise OSError("blocked")
        return [Investment("乙電子", "", None, 1.0, 19.07, 2.0, "綜合公允")], [BoardSeat("董事長", "丙科技(股)-王", "丙科技", 1.0, 18.88)]

    async def names():
        return {"1111": "甲科股份有限公司"}

    async def sleep(s_):
        slept.append(s_)

    c = RelationCollector(store=s, fetch=fetch, fetch_names=names, codes=lambda: ["1111", "X1", "X2", "X3", "2222"], clock=lambda: now, sleep=sleep, start_delay=0)
    asyncio.run(c.run_once())
    assert calls == ["1111", "X1", "X2", "X3", "2222"]
    assert 900 in slept  # three failures in a row → a 15-minute pause
    assert all(x >= 4 for x in slept if x != 900)  # every stock is paced
    invest, board = s.relation_rows()
    assert invest["1111"][0]["name"] == "乙電子" and board["1111"][0]["corp"] == "丙科技"
    assert s.relation_fetched()["X1"]["error"] and s.company_names() == {"1111": "甲科股份有限公司"}
    # fresh ones are skipped; failed ones are retried only after RETRY_HOURS
    assert c.due() == []
    later = RelationCollector(store=s, fetch=fetch, fetch_names=names, codes=lambda: ["1111", "X1"], clock=lambda: now + timedelta(hours=25), sleep=sleep)
    assert later.due() == ["X1"]
    # an error keeps the rows fetched before
    s.save_relations("1111", None, None, now, error="boom")
    assert s.relation_rows()[0]["1111"][0]["name"] == "乙電子"
