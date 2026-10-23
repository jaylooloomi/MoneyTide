"""News-driven hot groups (新聞熱門族群): daily keyword extraction, optional AI clean-up, and the
3-day rolling list that feeds panel J and the `news` grouping. See
docs/superpowers/specs/2026-10-23-news-themes-design.md.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import httpx

from .ai import AIConfig, AIError, complete
from .config import TAIPEI
from .history.store import HistoryStore
from .sources.google_news import Headline
from .sources.news_themes import NameIndex, extract_day, themes_in

log = logging.getLogger(__name__)

BACKFILL_DAYS = 60
WINDOW = 3  # trading days summed into a day's heat
MIN_SCORE = 2
MIN_MEMBERS = 3
TOP_THEMES = 30
AI_CANDIDATES = 40
DAILY_READY = time(15, 30)

AI_SYSTEM = (
    "你是台股題材整理助理。輸入是近 3 天新聞標題中抽出的候選族群詞、則數、例句與候選成員股名。"
    "請合併同義或同一題材的詞（例如 CPO 與矽光子），用最常見的名稱命名，剔除不是投資族群的詞（例如泛稱、人口族群、外國市場）。"
    "成員只能從提供的候選股名中挑選，可以補上你確定屬於該題材且在候選名單中的股名。"
    '只輸出 JSON 陣列：[{"name": "…", "aliases": ["…"], "members": ["股名", …]}]，不要其他文字。'
)


# ---- rolling hot list ---------------------------------------------------------------------------


def group_members_for(theme: str, groups: Mapping[str, list[str]]) -> list[str]:
    """Members of an existing concept / 細產業 group with the same name (or the same last part)."""
    for name, codes in groups.items():
        if name == theme or name.split("／")[-1] == theme:
            return list(codes)
    return []


def hot_themes(
    days: list[dict],
    ai: list[dict] | None,
    groups: Mapping[str, list[str]],
    name_to_code: Mapping[str, str],
) -> list[dict]:
    """`days`: keyword results of the latest stored news days, newest first (≥ the day asked for).
    Returns [{name, score, prev_score, codes, titles, aliases}] sorted by heat."""
    recent, previous = days[:WINDOW], days[WINDOW:WINDOW * 2]

    def gather(names: list[str], span: list[dict]) -> tuple[int, Counter, list[dict]]:
        mentions, codes, titles = 0, Counter(), []
        for day in span:
            for n in names:
                t = day.get(n)
                if not t:
                    continue
                mentions += t["mentions"]
                codes.update(t["codes"])
                for x in t["titles"]:
                    if x not in titles and len(titles) < 5:
                        titles.append(x)
        return mentions, codes, titles

    if ai:
        candidates = [(t["name"], [t["name"], *t.get("aliases", [])], t.get("members", [])) for t in ai]
    else:
        names = {n for day in recent for n in day}
        candidates = [(n, [n], []) for n in names]
    out = []
    for name, names, ai_members in candidates:
        score, codes, titles = gather(names, recent)
        prev, _, _ = gather(names, previous)
        ordered = [c for c, _ in codes.most_common()]
        for m in ai_members:
            code = name_to_code.get(m)
            if code and code not in ordered:
                ordered.append(code)
        for n in names:
            for code in group_members_for(n, groups):
                if code not in ordered:
                    ordered.append(code)
        if score >= (1 if ai else MIN_SCORE) and len(ordered) >= MIN_MEMBERS:
            out.append({"name": name, "score": score, "prev_score": prev, "codes": ordered, "titles": titles,
                        "aliases": [n for n in names if n != name]})
    out.sort(key=lambda t: (-t["score"], -(t["score"] - t["prev_score"]), t["name"]))
    return out[:TOP_THEMES]


def themes_mapping(themes: list[dict]) -> dict[str, list[str]]:
    """code → [theme names] (the `news` grouping)."""
    mapping: dict[str, list[str]] = {}
    for t in themes:
        for code in t["codes"]:
            mapping.setdefault(code, []).append(t["name"])
    return mapping


# ---- AI clean-up --------------------------------------------------------------------------------


def ai_prompt(days: list[dict], code_to_name: Mapping[str, str]) -> str:
    recent = days[:WINDOW]
    totals: Counter = Counter()
    for day in recent:
        for n, t in day.items():
            totals[n] += t["mentions"]
    lines = []
    for n, count in totals.most_common(AI_CANDIDATES):
        if count < MIN_SCORE:
            break
        codes: Counter = Counter()
        sample = ""
        for day in recent:
            t = day.get(n)
            if t:
                codes.update(t["codes"])
                sample = sample or t["titles"][0]["title"]
        members = "、".join(code_to_name.get(c, c) for c, _ in codes.most_common(12)) or "（無）"
        lines.append(f"- {n}（{count} 則）例：{sample}｜候選成員：{members}")
    return "候選族群：\n" + "\n".join(lines)


def parse_ai_themes(text: str, name_to_code: Mapping[str, str]) -> list[dict]:
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    m = re.search(r"\[.*\]", cleaned, re.S)
    if not m:
        raise ValueError("AI 回答不是 JSON 陣列")
    out = []
    for t in json.loads(m.group(0)):
        if not isinstance(t, dict) or not str(t.get("name", "")).strip():
            continue
        out.append({
            "name": str(t["name"]).strip()[:20].replace("/", "／").replace(",", "、"),
            "aliases": [str(a).strip() for a in t.get("aliases") or [] if str(a).strip()],
            "members": [str(x).strip() for x in t.get("members") or [] if str(x).strip() in name_to_code],
        })
    return out


# ---- collector ----------------------------------------------------------------------------------


@dataclass
class NewsState:
    running: bool = False
    done: int = 0
    total: int = 0
    error: str = ""


class NewsThemeCollector:
    def __init__(
        self,
        *,
        store: HistoryStore,
        fetch_day: Callable[[date], Awaitable[list[Headline]]],
        reference: Callable[[], Mapping[str, str]],  # common-stock code → name
        ai_config: AIConfig,
        fetch_ptt: Callable[[date], Awaitable[dict[date, list[str]]]] | None = None,
        http: httpx.AsyncClient | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(TAIPEI),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        delay: float = 3.0,
    ) -> None:
        self.store = store
        self._fetch_day = fetch_day
        self._fetch_ptt = fetch_ptt
        self._reference = reference
        self._ai = ai_config
        self._http = http
        self._clock = clock
        self._sleep = sleep
        self._delay = delay
        self.state = NewsState()

    def pending_days(self) -> list[date]:
        now = self._clock().astimezone(TAIPEI)
        dates = list(self.store.trading_dates(limit=BACKFILL_DAYS))
        if now.weekday() < 5 and now.time() >= DAILY_READY and now.date() not in dates:
            dates.insert(0, now.date())
        known = self.store.news_dates()
        return [d for d in dates if d not in known]

    async def run_once(self) -> None:
        names = self._reference()
        if not names:
            return  # wait for the ISIN listing
        index = NameIndex.build(dict(names))
        todo = self.pending_days()
        self.state = NewsState(running=bool(todo), total=len(todo))
        for d in todo:
            try:
                headlines = await self._fetch_day(d)
                self.store.save_news_day(d, extract_day(headlines, index), len(headlines))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("news themes for %s failed: %s", d, exc)
                self.state.error = f"{d}: {exc}"
            self.state.done += 1
            await self._sleep(self._delay)
        self.state.running = False
        await self.collect_ptt()
        await self.clean_latest_with_ai(dict(names))

    async def collect_ptt(self) -> None:
        """PTT titles from the newest page back to the day before the latest stored one (first run:
        PTT_DAYS back); days that were covered are replaced, so a partly fetched day fills up."""
        if self._fetch_ptt is None:
            return
        today = self._clock().astimezone(TAIPEI).date()
        stored = self.store.ptt_dates_sorted(limit=1)
        since = max(stored[0] - timedelta(days=1), today - timedelta(days=PTT_DAYS)) if stored else today - timedelta(days=PTT_DAYS)
        try:
            by_day = await self._fetch_ptt(since)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("PTT fetch failed: %s", exc)
            self.state.error = f"PTT：{exc}"
            return
        if by_day:
            self.store.save_ptt_days(by_day)

    async def clean_latest_with_ai(self, code_to_name: dict[str, str]) -> None:
        if not self._ai.configured or self._http is None:
            return
        dates = self.store.news_dates_sorted(limit=WINDOW)
        if not dates or self.store.news_ai(dates[0]) is not None:
            return
        days = [self.store.news_day(d) for d in dates]
        name_to_code = {n: c for c, n in code_to_name.items()}
        try:
            answer = await complete(self._http, self._ai, AI_SYSTEM, ai_prompt(days, code_to_name), max_tokens=4096)
            themes = parse_ai_themes(answer, name_to_code)
        except (AIError, ValueError) as exc:
            log.warning("news theme AI clean-up failed: %s", exc)
            self.state.error = f"AI：{exc}"
            return
        if themes:
            self.store.save_news_ai(dates[0], themes, self._ai.model)

    async def run(self) -> None:
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("news theme collector error")
            await self._sleep(1800)


# ---- queries used by the API ---------------------------------------------------------------------


def themes_for_day(store: HistoryStore, day: date | None, groups: Mapping[str, list[str]], code_to_name: Mapping[str, str]) -> tuple[date | None, list[dict], str]:
    """(news date used, hot themes, method) for the latest stored news day ≤ `day`."""
    dates = store.news_dates_sorted(up_to=day, limit=WINDOW * 2)
    if not dates:
        return None, [], "none"
    key = ("news_themes", dates[0], tuple(dates), store.news_version())
    cached = store.derived_cache.get(key)
    if cached is not None:
        return cached
    days = [store.news_day(d) for d in dates]
    ai = store.news_ai(dates[0])
    name_to_code = {n: c for c, n in code_to_name.items()}
    result = (dates[0], hot_themes(days, ai, groups, name_to_code), "ai" if ai else "keyword")
    store.derived_cache[key] = result
    return result



# ---- heat bursts: terms whose recent mentions jump above their own baseline ---------------------

PTT_DAYS = 30
BURST_RECENT = 3
BURST_BASE = 20
BURST_Z = 2.0
BURST_MIN = 3
TOP_BURSTS = 15

_TECH = re.compile(r"(?<![A-Za-z0-9])([A-Za-z][A-Za-z0-9+\-]{1,7})(?![A-Za-z0-9])")
_TECH_STOP = {"RE", "FW", "ETF", "EPS", "KY", "YOY", "QOQ", "MOM", "ROE", "PE", "PB", "ADR", "IPO", "CEO", "CFO",
              "GDP", "CPI", "PMI", "FED", "FOMC", "PTT", "US", "TW", "OK", "QQ", "LOL", "XD", "NT", "USD", "TWD",
              "Q1", "Q2", "Q3", "Q4", "H1", "H2", "AM", "PM", "TSMC", "VS", "NO", "YES"}


def ptt_terms(titles: list[str], group_names: list[str]) -> Counter:
    """Theme phrases, English/alphanumeric tech words and known group names in one day's PTT titles."""
    counts: Counter = Counter()
    pattern = re.compile("|".join(re.escape(n) for n in sorted(group_names, key=len, reverse=True))) if group_names else None
    for t in titles:
        found = set(themes_in(t))
        for m in _TECH.finditer(t):
            w = m.group(1)
            if w.upper() not in _TECH_STOP and not w.isdigit():
                found.add(w.upper() if w.isupper() or len(w) <= 4 else w)
        if pattern:
            found.update(m.group(0) for m in pattern.finditer(t))
        counts.update(found)  # a term counts once per title
    return counts


def short_group_names(groups: Mapping[str, list[str]]) -> list[str]:
    """Group names usable as search terms: the last part of 細產業 names, 2–10 characters."""
    names = {n.split("／")[-1] for n in groups}
    return [n for n in names if 2 <= len(n) <= 10 and not n.startswith("其他")]


def heat_bursts(store: HistoryStore, day: date | None, groups: Mapping[str, list[str]]) -> list[dict]:
    """Terms mentioned ≥ BURST_MIN times in the last BURST_RECENT days and ≥ BURST_Z above what their
    BURST_BASE-day rate predicts: z = (recent − expected) / √(expected + 1), expected = base mean × days."""
    dates = sorted(set(store.news_dates_sorted(up_to=day, limit=BURST_RECENT + BURST_BASE))
                   | set(store.ptt_dates_sorted(up_to=day, limit=BURST_RECENT + BURST_BASE)), reverse=True)
    dates = dates[: BURST_RECENT + BURST_BASE]
    if len(dates) < BURST_RECENT + 5:
        return []
    key = ("heat_bursts", tuple(dates), store.news_version())
    cached = store.derived_cache.get(key)
    if cached is not None:
        return cached
    names = short_group_names(groups)
    per_day = []
    for d in dates:
        c: Counter = Counter()
        for theme, t in store.news_day(d).items():
            c[theme] += t["mentions"]
        c.update(ptt_terms(store.ptt_titles(d), names))
        per_day.append(c)
    recent, base = per_day[:BURST_RECENT], per_day[BURST_RECENT:]
    terms = set().union(*recent)
    out = []
    for term in terms:
        r = [c.get(term, 0) for c in recent]
        b = [c.get(term, 0) for c in base]
        if sum(r) < BURST_MIN:
            continue
        bm = sum(b) / len(b)
        expected = bm * len(r)
        z = (sum(r) - expected) / (expected + 1) ** 0.5  # Poisson-style: counts are small and bursty
        if z >= BURST_Z:
            out.append({"term": term, "recent": sum(r), "base_mean": round(bm, 2), "z": round(z, 2)})
    out.sort(key=lambda t: (-t["z"], -t["recent"]))
    store.derived_cache[key] = out[:TOP_BURSTS]
    return out[:TOP_BURSTS]
