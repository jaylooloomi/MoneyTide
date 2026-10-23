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
from .sources.news_themes import NameIndex, extract_day

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
        http: httpx.AsyncClient | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(TAIPEI),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        delay: float = 3.0,
    ) -> None:
        self.store = store
        self._fetch_day = fetch_day
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
        await self.clean_latest_with_ai(dict(names))

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
