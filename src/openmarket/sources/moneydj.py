"""Company relations from MoneyDJ's per-stock pages (Big5 HTML, one table each), fetched slowly.

- 轉投資 /z/zc/zcg/zcg_{code}.djhtm: one row per investee — 轉投資事業, 投資幣別, 投資成本 (仟元),
  持股股數 (仟股), 持股比例, 帳面價值 (仟元), 會計原則 (權益法 / 綜合公允 / FV 變動…).
- 董監持股 /z/zc/zck/zck_{code}.djhtm: the first table lists 職稱, 姓名/法人名稱, 持股張數, 持股比例, …;
  a corporate director reads "東友科技(股)-黃育仁" (the company, then its representative).
Both pages credit 公開資訊觀測站 as their source. Kept for local analysis only; never republished.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx

from .http import get_with_retry

BASE = "https://concords.moneydj.com/z/zc"
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True, slots=True)
class Investment:
    name: str  # the investee as written (MoneyDJ cuts long names)
    currency: str
    cost: float | None  # 仟元
    shares: float | None  # 仟股
    pct: float | None  # 持股比例 %
    book: float | None  # 帳面價值 仟元
    method: str  # 會計原則


@dataclass(frozen=True, slots=True)
class BoardSeat:
    title: str  # 職稱 (董事長, 董事, 監察人, 獨立董事, 總經理…)
    name: str  # 姓名/法人名稱 as written
    corp: str | None  # the company behind a corporate seat ("東友科技"), None for a person
    lots: float | None  # 持股張數
    pct: float | None  # 持股比例 %


def _cells(row_html: str) -> list[str]:
    return [_TAG.sub("", c).replace("&nbsp;", " ").replace("&amp;", "&").strip() for c in _CELL.findall(row_html)]


def _num(s: str) -> float | None:
    s = s.replace(",", "").replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse_investments(html: str) -> list[Investment]:
    out = []
    for row in _ROW.findall(html):
        c = _cells(row)
        if len(c) != 7 or c[0] in ("", "轉投資事業") or c[2] == "投資成本":
            continue
        out.append(Investment(c[0], c[1], _num(c[2]), _num(c[3]), _num(c[4]), _num(c[5]), c[6]))
    return out


CORP_SEAT = re.compile(r"^(.+?)(?:\(股\)|（股）|股份有限公司|有限公司)\s*(?:-|－|代表人)?\s*(.*)$")


def parse_board(html: str) -> list[BoardSeat]:
    """The 董監事經理人持股明細 table (stops at its footnote; the 申報轉讓 table after it is ignored)."""
    out: list[BoardSeat] = []
    started = False
    for row in _ROW.findall(html):
        c = _cells(row)
        if not c:
            continue
        if c[0].startswith("職稱"):
            started = True
            continue
        if not started:
            continue
        if len(c) < 4 or c[0].startswith("＊") or "申報轉讓" in c[0]:
            if out:
                break
            continue
        m = CORP_SEAT.match(c[1])
        corp = m.group(1).strip() if m else None
        out.append(BoardSeat(c[0], c[1], corp, _num(c[2]), _num(c[3])))
    return out


async def fetch_relations(
    client: httpx.AsyncClient, code: str, sleep: Callable[[float], Awaitable[None]], delay: float
) -> tuple[list[Investment], list[BoardSeat]]:
    """Both pages for one stock, `delay` apart (the caller paces the stocks)."""
    a = await get_with_retry(client, f"{BASE}/zcg/zcg_{code}.djhtm")
    await sleep(delay)
    b = await get_with_retry(client, f"{BASE}/zck/zck_{code}.djhtm")
    return parse_investments(a.content.decode("big5", errors="replace")), parse_board(b.content.decode("big5", errors="replace"))
