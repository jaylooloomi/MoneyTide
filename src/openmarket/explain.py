"""⑤ Why did the day's top movers move? Headlines (Google News) → short AI summaries, cached.

For a day: the 3 largest gainers and 3 largest losers among common stocks with turnover ≥ 1 億
(thin stocks are noise). Each gets ≤ 8 headlines from around that day; with no headlines the AI is
not asked at all and the answer is NO_NEWS. Results (including NO_NEWS) are cached per (date, code)
in data/history.sqlite, so a stock is asked about once per day; failures are not cached.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from datetime import date

import httpx

from .ai import AIConfig, AIError, complete
from .sources.google_news import Headline

TOP_N = 3
MIN_TURNOVER_100M = 1.0
AI_CONCURRENCY = 3
NO_NEWS = "找不到足夠新聞，無法判斷。"
AI_DOWN = "AI 服務暫時無法使用"

SYSTEM = (
    "你是台股盤後新聞整理助理。只根據使用者提供的新聞標題，說明這檔股票當天大漲或大跌最可能的原因。"
    "規則：用繁體中文寫 2～3 句；只引用提供的標題，不可自行補充或推測標題沒有的事實；"
    "不給任何投資建議；若標題與漲跌無關或資訊不足，reason 必須是 INSUFFICIENT。"
    '只輸出一個 JSON 物件：{"reason": "…", "sources": [引用的標題編號]}，不要其他文字。'
)

HeadlineFetcher = Callable[[str, str, date], Awaitable[list[Headline]]]


def select_movers(stocks: list[dict], n: int = TOP_N, min_turnover_100m: float = MIN_TURNOVER_100M) -> dict[str, list[dict]]:
    """{"gainers": [...], "losers": [...]} from rows with code, name, kind, change_pct, turnover_100m."""
    seen: set[str] = set()
    pool = []
    for s in stocks:
        if s.get("kind") != "stock" or s["code"] in seen or s.get("change_pct") is None:
            continue
        if (s.get("turnover_100m") or 0) < min_turnover_100m:
            continue
        seen.add(s["code"])
        pool.append(s)
    gainers = sorted((s for s in pool if s["change_pct"] > 0), key=lambda s: -s["change_pct"])[:n]
    losers = sorted((s for s in pool if s["change_pct"] < 0), key=lambda s: s["change_pct"])[:n]
    return {"gainers": gainers, "losers": losers}


def build_prompt(stock: dict, day: date, headlines: list[Headline]) -> str:
    direction = "上漲" if stock["change_pct"] > 0 else "下跌"
    lines = [
        f"日期：{day.isoformat()}",
        f"股票：{stock['code']} {stock['name']}（{stock.get('industry') or '—'}）",
        f"當日{direction} {abs(stock['change_pct']):.2f}%，成交值 {stock.get('turnover_100m') or 0:.1f} 億元",
        "新聞標題：",
    ]
    for i, h in enumerate(headlines, 1):
        when = h.published.strftime("%m/%d %H:%M") if h.published else "日期不明"
        lines.append(f"{i}. [{when}｜{h.source or '來源不明'}] {h.title}")
    return "\n".join(lines)


def parse_answer(text: str, headlines: list[Headline]) -> tuple[str, list[dict]]:
    """(reason, cited links). Falls back to the raw text with the first 3 headlines when the model
    did not return JSON; INSUFFICIENT becomes NO_NEWS with no links."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    m = re.search(r"\{.*\}", cleaned, re.S)
    reason, cited = None, []
    if m:
        try:
            obj = json.loads(m.group(0))
            reason = str(obj.get("reason") or "").strip()
            cited = [int(i) for i in obj.get("sources") or [] if str(i).isdigit()]
        except (ValueError, TypeError, AttributeError):
            reason = None
    if reason is None:
        reason = cleaned
        cited = []
    if not reason or "INSUFFICIENT" in reason.upper():
        return NO_NEWS, []
    picked = [headlines[i - 1] for i in cited if 1 <= i <= len(headlines)] or headlines[:3]
    return reason[:400], [h.to_dict() for h in picked]


async def explain_stock(
    http: httpx.AsyncClient,
    cfg: AIConfig,
    fetch_headlines: HeadlineFetcher,
    stock: dict,
    day: date,
    sem: asyncio.Semaphore,
) -> dict:
    """One stock → {reason, links, error}. error is set (and nothing should be cached) on failure."""
    try:
        headlines = await fetch_headlines(stock["name"], stock["code"], day)
    except Exception:  # news search down: report, do not cache
        return {"reason": None, "links": [], "error": "新聞搜尋暫時無法使用"}
    if not headlines:
        return {"reason": NO_NEWS, "links": [], "error": None}
    async with sem:
        try:
            answer = await complete(http, cfg, SYSTEM, build_prompt(stock, day, headlines))
        except AIError as exc:
            return {"reason": None, "links": [h.to_dict() for h in headlines[:3]], "error": f"{AI_DOWN}：{exc}"}
    reason, links = parse_answer(answer, headlines)
    return {"reason": reason, "links": links, "error": None}


async def explain_day(
    store,
    http: httpx.AsyncClient,
    cfg: AIConfig,
    fetch_headlines: HeadlineFetcher,
    day: date,
    stocks: list[dict],
    *,
    run: bool,
) -> dict:
    """Movers for `day` with cached reasons; with run=True, missing ones are asked for (and cached)."""
    movers = select_movers(stocks)
    cached = store.ai_reasons(day)
    sem = asyncio.Semaphore(AI_CONCURRENCY)

    async def one(side: str, s: dict) -> dict:
        row = {
            "code": s["code"], "name": s["name"], "industry": s.get("industry"), "side": side,
            "change_pct": s["change_pct"], "turnover_100m": s.get("turnover_100m"),
        }
        hit = cached.get(s["code"])
        if hit:
            return {**row, "reason": hit["reason"], "links": hit["links"], "model": hit["model"], "cached": True, "error": None}
        if not run:
            return {**row, "reason": None, "links": [], "model": None, "cached": False, "error": None}
        result = await explain_stock(http, cfg, fetch_headlines, s, day, sem)
        if result["error"] is None:
            store.save_ai_reason(day, s["code"], result["reason"], result["links"], cfg.model)
        return {**row, **result, "model": cfg.model, "cached": False}

    tasks = [one("gainers", s) for s in movers["gainers"]] + [one("losers", s) for s in movers["losers"]]
    rows = await asyncio.gather(*tasks)
    return {
        "date": day.isoformat(),
        "gainers": [r for r in rows if r["side"] == "gainers"],
        "losers": [r for r in rows if r["side"] == "losers"],
        "analyzed": all(r["reason"] is not None for r in rows) and bool(rows),
    }
