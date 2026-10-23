"""Market-wide headlines for one day and the keyword extraction of "hot groups" from them.

Google News RSS with `<query> after:<day> before:<day+1>` for a few theme words; titles such as
"低軌衛星族群升空", "CPO概念股集體下跌", "PCB、玻纖布族群強勢". A theme is the phrase right
before 概念股／族群／類股／供應鏈／題材; its members are the listed stocks named in the same
titles. Pure functions here; collection, storage and AI clean-up live in openmarket.news_themes.
"""

from __future__ import annotations

import re
import urllib.parse
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta

import httpx

from .google_news import RSS_URL, Headline, parse_rss
from .http import get_with_retry

QUERIES = ["概念股", "族群", "類股", "題材股", "供應鏈 台股"]
MAX_PER_QUERY = 100

_SUFFIX = re.compile(r"(概念股|族群|類股|供應鏈|題材股|題材)")
# split points before a theme phrase: punctuation, spaces and joining words
_SPLIT = re.compile(r"[\s，,。．.、；;：:！!？?「」『』《》〈〉()（）\[\]【】|｜/／\-—–~～+＋→⭢]|的|與|和|及|帶動|領軍|點火|助攻|接棒|拉抬|推升|撐盤|走強|走弱|齊揚|大漲|重挫|下跌|上漲")
_LEADING = ("台股", "臺股", "熱門", "強勢", "弱勢", "相關", "台廠", "臺廠", "傳產", "今日", "今天", "盤中", "盤後", "早盤", "尾盤",
            "多頭", "空頭", "資金", "主流", "新興", "整體", "全體", "其他", "多檔", "個股", "龍頭", "產業")
_STOP = {"這", "那", "此", "該", "某", "各", "其", "這個", "那個", "這些", "相關", "多檔", "個股", "權值", "上市", "上櫃", "高風險",
         "弱勢", "強勢", "熱門", "防禦", "價值股", "成長股", "傳產", "非電", "中小型", "大型", "小型", "中型",
         "年輕", "銀髮", "上班", "族", "高齡", "低收入", "弱勢族群", "台廠", "臺廠", "台灣", "臺灣", "美國", "海外", "全球",
         "供應", "概念", "題材", "族群", "類股", "內需", "外資", "投信", "法人", "主力"}
_FOREIGN = ("美股", "港股", "A股", "陸股", "日股", "韓股", "陸港股", "中概", "美國股市", "智通財經")
_COMMON_SHORT = {"中華", "大同", "統一", "台灣", "臺灣", "國泰", "中信", "全國", "東元", "大成", "新光", "力麗", "長榮",
                 "無敵", "全家", "寶島", "大樹", "合作", "美食", "天然", "國際", "如興", "大將"}
_CODE = re.compile(r"[（(](\d{4,6}[A-Z]?)[)）]")


def clean_theme(prefix: str) -> str | None:
    """The theme name from the text before a suffix, or None when it is not a usable theme."""
    parts = [p for p in _SPLIT.split(prefix) if p]
    if not parts:
        return None
    name = parts[-1].strip()
    changed = True
    while changed and name:
        changed = False
        for lead in _LEADING:
            if name.startswith(lead) and len(name) > len(lead):
                name, changed = name[len(lead):], True
    name = re.sub(r"^\d+檔", "", name)
    if not (2 <= len(name) <= 10) or name.isdigit() or name in _STOP or name[0] in "這那該此某":
        return None
    if re.fullmatch(r"[\d.%]+", name) or name.endswith("檔"):
        return None
    return name


def themes_in(title: str) -> list[str]:
    if any(f in title for f in _FOREIGN):
        return []
    found = []
    for m in _SUFFIX.finditer(title):
        before = title[: m.start()][-24:]
        names = [clean_theme(before)]
        # "PCB、玻纖布族群": the phrase joined by 、 right before belongs to the same suffix
        head, sep, _ = before.rpartition("、")
        if sep and len(before) - len(head) <= 12:
            names.append(clean_theme(head[-14:]))
        for name in names:
            if name and name not in found:
                found.append(name)
    return found


@dataclass
class NameIndex:
    """Longest-first matcher of listed common-stock names (and "(code)" mentions) in titles."""

    names: dict[str, str]  # name -> code
    codes: set[str]
    _pattern: re.Pattern | None = field(default=None, init=False, repr=False)

    @classmethod
    def build(cls, code_to_name: dict[str, str]) -> NameIndex:
        names = {}
        for code, name in code_to_name.items():
            name = name.strip()
            if len(name) >= 2 and name not in _COMMON_SHORT:
                names.setdefault(name, code)
        return cls(names=names, codes=set(code_to_name))

    def find(self, title: str) -> list[str]:
        if self._pattern is None:
            alts = sorted(self.names, key=len, reverse=True)
            self._pattern = re.compile("|".join(re.escape(n) for n in alts)) if alts else re.compile(r"(?!)")
        out: list[str] = []
        for m in self._pattern.finditer(title):
            code = self.names[m.group(0)]
            if code not in out:
                out.append(code)
        for m in _CODE.finditer(title):
            if m.group(1) in self.codes and m.group(1) not in out:
                out.append(m.group(1))
        return out


def extract_day(headlines: list[Headline], index: NameIndex) -> dict[str, dict]:
    """{theme: {"mentions": n, "codes": {code: co-mentions}, "titles": [≤5 headline dicts]}}."""
    out: dict[str, dict] = {}
    for h in headlines:
        names = themes_in(h.title)
        if not names:
            continue
        codes = index.find(h.title)
        for name in names:
            t = out.setdefault(name, {"mentions": 0, "codes": Counter(), "titles": []})
            t["mentions"] += 1
            t["codes"].update(codes)
            if len(t["titles"]) < 5:
                t["titles"].append({"title": h.title, "source": h.source, "url": h.url})
    for t in out.values():
        t["codes"] = dict(t["codes"])
    return out


def day_url(query: str, day: date) -> str:
    q = f"{query} after:{day:%Y-%m-%d} before:{day + timedelta(days=1):%Y-%m-%d}"
    return f"{RSS_URL}?{urllib.parse.urlencode({'q': q, 'hl': 'zh-TW', 'gl': 'TW', 'ceid': 'TW:zh-Hant'})}"


async def fetch_day_headlines(client: httpx.AsyncClient, day: date, sleep, delay: float) -> list[Headline]:
    """All theme-query headlines published on `day` (Taipei), deduplicated by title."""
    seen: dict[str, Headline] = {}
    for i, q in enumerate(QUERIES):
        if i:
            await sleep(delay)
        resp = await get_with_retry(client, day_url(q, day))
        for h in parse_rss(resp.text, day, limit=MAX_PER_QUERY, window=0):
            seen.setdefault(h.title, h)
    return list(seen.values())
