from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import mimetypes
from dataclasses import asdict
from datetime import date, datetime, time
from itertools import takewhile
from collections.abc import AsyncIterator, Mapping
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel

from .ai import AIConfig
from .config import STATIC_DIR, TAIPEI, USER_AGENT, AppConfig
from .explain import explain_day
from .history.linkage import (
    INTRADAY_HIGH_R, INTRADAY_LOW_R, bucket_closes, daily_linkage, fmt_minute, pair_matrix, peak_minute_from_bars, peak_minute_from_ticks,
    align_bars, amplitude_pct, limit_down_pct, limit_up_pct, minute_bars, turnover_rate, peak_stats, tick_bars, with_close_bar, race_points, returns, locked_level, top_members, verdict_r, verdict_timing,
)
from .history.finder import INST_STREAK_DAYS, FinderParams, inst_streak, inst_summary, margin_changes, margin_summary, pair_extras, persistence, run_search
from .history.finder import news_themes as finder_news_themes  # api.py has its own news_themes route
from .intraday import IntradayRecorder
from .sources.yahoo_intraday import INDEX_SYMBOLS, ONE_MINUTE_DAYS, fetch_bars, fetch_day_1m, fetch_span_1m
from .news_themes import NewsThemeCollector, heat_bursts, themes_for_day, themes_mapping
from .concepts import ConceptLoader
from .groups import GroupStore
from .history.api import create_history_router, live_quote_day
from .history.metrics import industry_grouping, mapping_grouping
from .history.ingest import REQUEST_DELAY_SECONDS, HistoryCollector
from .history.store import HistoryStore
from .poller import Poller, RefreshTooSoon
from .sources.histock import fetch_quotes
from .sources.http import make_client
from .sources.official import fetch_tpex_day, fetch_twse_day
from .sources.official_index import fetch_index_month
from .sources.institutional import fetch_inst_day
from .sources.margin import fetch_margin_day
from .sources.sector_index import fetch_sector_day
from .sources.company_address import fetch_county_groups
from .sources.google_news import fetch_headlines
from .sources.news_themes import fetch_day_headlines
from .sources.ptt import fetch_titles_since, make_ptt_client
from .sources.tpex_chains import fetch_chains
from .sources.yahoo_concepts import fetch_concepts
from .sources.shares import fetch_shares
from .sources.twse_isin import fetch_isin
from .storage import JsonCache, SettingsStore, Watchlist


class SettingsBody(BaseModel):
    poll_seconds: int


class RenameBody(BaseModel):
    name: str


def build_poller(client: httpx.AsyncClient, data_dir: Path, settings: SettingsStore) -> Poller:
    return Poller(
        fetch_quotes=lambda: fetch_quotes(client),
        fetch_infos=lambda: fetch_isin(client),
        fetch_shares=lambda: fetch_shares(client),
        info_cache=JsonCache(data_dir / "isin_cache.json"),
        shares_cache=JsonCache(data_dir / "shares_cache.json"),
        settings=settings,
    )


def create_app(
    config: AppConfig | None = None,
    *,
    poller: Poller | None = None,
    start_polling: bool = True,
    history_store: HistoryStore | None = None,
    start_history: bool = True,
    concepts: ConceptLoader | None = None,
    start_concepts: bool = True,  # also starts the 細產業 (TPEx chain) loader
    chains: ConceptLoader | None = None,
    counties: ConceptLoader | None = None,
    ai_config: AIConfig | None = None,
    headline_fetcher=None,  # tests: (client, name, code, day) -> [Headline]
    ai_transport: httpx.AsyncBaseTransport | None = None,  # tests: mock HTTP for news + AI
    static_dir: Path = STATIC_DIR,
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost"),
) -> FastAPI:
    config = config or AppConfig.from_env()
    settings = SettingsStore(config.data_dir / "settings.json")
    watchlist = Watchlist(config.data_dir / "watchlist.json")
    groups = GroupStore(config.data_dir / "groups.json")

    def stock_names() -> dict[str, str]:
        """Common-stock code → name from the ISIN listing (empty until it has loaded)."""
        p = app.state.poller
        return {c: i.name for c, i in (p.infos if p else {}).items() if i.kind == "stock"}

    def named_groups() -> dict[str, list[str]]:
        """Concept + 細產業 groups by name: a news theme with the same name borrows their members."""
        out: dict[str, list[str]] = {}
        for loader in (app.state.concepts, app.state.chains):
            if loader is not None:
                out.update(loader.concepts)
        return out

    def get_grouping(name: str):
        if name == "industry":
            return industry_grouping
        if name == "custom":
            mapping = groups.mapping()
            g = mapping_grouping(mapping)
            g.cache_key = "custom:" + json.dumps(mapping, sort_keys=True, ensure_ascii=False)
            return g
        if name == "concept":
            loader = app.state.concepts
            if loader is None or not loader.mapping:
                return None
            g = mapping_grouping(loader.mapping)
            g.cache_key = f"concept:{loader.saved_at.isoformat() if loader.saved_at else ''}"
            return g
        if name == "news" or name.startswith("news@"):  # 新聞族群: that day's hot themes (latest without a date)
            day = date.fromisoformat(name[5:]) if "@" in name else None
            used, themes, _ = themes_for_day(app.state.history, day, named_groups(), stock_names())
            if not themes:
                return None
            g = mapping_grouping(themes_mapping(themes))
            g.cache_key = f"news:{used.isoformat()}:{app.state.history.news_version()}"
            return g
        if name == "chain":  # 細產業 (TPEx 產業價值鏈)
            loader = app.state.chains
            if loader is None or not loader.mapping:
                return None
            g = mapping_grouping(loader.mapping)
            g.cache_key = f"chain:{loader.saved_at.isoformat() if loader.saved_at else ''}"
            return g
        return None

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client = None
        if app.state.poller is None:
            client = make_client()
            app.state.poller = build_poller(client, config.data_dir, settings)
        tasks = []
        if start_polling:
            tasks.append(asyncio.create_task(app.state.poller.run()))
        if start_history:
            if client is None:
                client = make_client()
            p = app.state.poller
            app.state.collector = HistoryCollector(
                store=app.state.history,
                fetch_twse=lambda d: fetch_twse_day(client, d),
                fetch_tpex=lambda d: fetch_tpex_day(client, d),
                reference=lambda: (p.infos, p.shares),
                fetch_index=lambda market, month: fetch_index_month(client, market, month, asyncio.sleep, REQUEST_DELAY_SECONDS),
                fetch_inst=lambda d: fetch_inst_day(client, d, asyncio.sleep, REQUEST_DELAY_SECONDS),
                fetch_margin=lambda d: fetch_margin_day(client, d, asyncio.sleep, REQUEST_DELAY_SECONDS),
                fetch_sectors=lambda d: fetch_sector_day(client, d),
            )
            tasks.append(asyncio.create_task(app.state.collector.run()))
            ptt_client = app.state.ptt_client = make_ptt_client()
            app.state.news = NewsThemeCollector(
                store=app.state.history,
                fetch_day=lambda d: fetch_day_headlines(client, d, asyncio.sleep, REQUEST_DELAY_SECONDS),
                reference=stock_names,
                ai_config=app.state.ai,
                http=client,
                fetch_ptt=lambda since: fetch_titles_since(ptt_client, since, asyncio.sleep),
            )
            tasks.append(asyncio.create_task(app.state.news.run()))
            app.state.recorder = IntradayRecorder(store=app.state.history, get_poller=lambda: app.state.poller)
            tasks.append(asyncio.create_task(app.state.recorder.run()))
            tasks.append(asyncio.create_task(finder_precompute()))  # N: the latest day, after the close
        if start_concepts and app.state.concepts is None:
            if client is None:
                client = make_client()
            app.state.concepts = ConceptLoader(
                cache=JsonCache(config.data_dir / "concepts_cache.json"),
                fetch=lambda progress: fetch_concepts(client, progress=progress),
            )
        if start_concepts and app.state.concepts is not None:
            tasks.append(asyncio.create_task(app.state.concepts.run()))
        if start_concepts and app.state.chains is None:
            if client is None:
                client = make_client()
            app.state.chains = ConceptLoader(
                cache=JsonCache(config.data_dir / "chains_cache.json"),
                fetch=lambda progress: fetch_chains(client, progress=progress),
            )
        if start_concepts and app.state.chains is not None:
            tasks.append(asyncio.create_task(app.state.chains.run()))
        if start_concepts and app.state.counties is None:
            if client is None:
                client = make_client()
            app.state.counties = ConceptLoader(  # head-office county per company (map view)
                cache=JsonCache(config.data_dir / "counties_cache.json"),
                fetch=lambda progress: fetch_county_groups(client, progress=progress),
            )
        if start_concepts and app.state.counties is not None:
            tasks.append(asyncio.create_task(app.state.counties.run()))
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
            if client is not None:
                await client.aclose()
            if app.state.ptt_client is not None:
                await app.state.ptt_client.aclose()

    app = FastAPI(title="MoneyTide", lifespan=lifespan)
    app.state.poller = poller
    app.state.history = history_store or HistoryStore(config.data_dir / "history.sqlite")
    app.state.collector = None
    app.state.news = None
    app.state.ptt_client = None
    app.state.concepts = concepts
    app.state.chains = chains
    app.state.counties = counties
    app.state.ai = ai_config or AIConfig.from_env()
    app.include_router(create_history_router(lambda: app.state.history, lambda: app.state.collector, get_grouping))
    # Local-only app: reject other Host headers (DNS rebinding could otherwise reach the PUT routes).
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(allowed_hosts))

    @app.middleware("http")
    async def revalidate_static(request: Request, call_next):
        # Without Cache-Control browsers cache JS/CSS heuristically and keep running an old
        # front end after an update; no-cache makes them revalidate (ETag → 304) on every load.
        response = await call_next(request)
        if not request.url.path.startswith("/api/") and "cache-control" not in response.headers:
            response.headers["Cache-Control"] = "no-cache"
        return response

    def get_poller() -> Poller:
        p = app.state.poller
        if p is None:
            raise HTTPException(503, "poller not ready")
        return p

    @app.get("/api/snapshot")
    def snapshot(request: Request) -> Response:
        p = get_poller()
        etag = p.etag
        headers = {"ETag": etag, "Cache-Control": "no-cache"}
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        return Response(content=p.snapshot_json, media_type="application/json", headers=headers)

    @app.get("/api/settings")
    def get_settings() -> dict:
        return settings.get()

    # async: runs on the event-loop thread, next to the poller it wakes up
    @app.put("/api/settings")
    async def put_settings(body: SettingsBody) -> dict:
        try:
            result = settings.set_poll_seconds(body.poll_seconds)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if app.state.poller is not None:
            app.state.poller.settings_changed()
        return result

    @app.post("/api/refresh", status_code=202)
    async def refresh() -> Response:
        try:
            get_poller().request_refresh()
        except RefreshTooSoon as exc:
            retry_after = int(exc.retry_after) + 1
            return JSONResponse(
                {"retry_after": retry_after}, status_code=429, headers={"Retry-After": str(retry_after)}
            )
        return JSONResponse({"accepted": True}, status_code=202)

    @app.get("/api/watchlist")
    def get_watchlist() -> dict:
        return {"codes": watchlist.codes()}

    @app.put("/api/watchlist/{code}")
    def add_watch(code: str) -> dict:
        try:
            return {"codes": watchlist.add(code)}
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.delete("/api/watchlist/{code}")
    def remove_watch(code: str) -> dict:
        return {"codes": watchlist.remove(code)}

    # ---- custom groups (自訂族群) ----

    def _groups_call(fn, *args) -> dict:
        try:
            return {"groups": fn(*args)}
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(404, f"group not found: {exc.args[0]}") from exc

    @app.get("/api/concepts/status")
    def concepts_status() -> dict:
        loader = app.state.concepts
        return loader.status() if loader is not None else {"ready": False, "count": 0, "running": False, "done": 0, "total": 0, "error": "", "saved_at": None}

    # ---- ⑤ AI news explanations for the day's top movers ----------------------------------

    @app.get("/api/ai/status")
    def ai_status() -> dict:
        return app.state.ai.public()

    def explain_input(source: str, day: str | None) -> tuple[date, list[dict]]:
        if source == "live":
            p = get_poller()
            snap = p.snapshot
            if snap.market_open:
                raise HTTPException(409, "盤中不分析，收盤後再試")
            if not snap.stocks:
                raise HTTPException(404, "目前沒有即時資料")
            d = live_quote_day(app.state.history, datetime.now(TAIPEI))
            return d, [asdict(s) for s in snap.stocks]
        if source != "history" or not day:
            raise HTTPException(422, "source must be history (with date) or live")
        try:
            d = date.fromisoformat(day)
        except ValueError as exc:
            raise HTTPException(422, f"invalid date {day!r}") from exc
        rows = app.state.history.day_rows(d)
        if not rows:
            raise HTTPException(404, f"no data for {day}")
        stocks = [
            {"code": r["code"], "name": r["name"], "kind": r["kind"], "industry": r["industry"], "change_pct": r["change_pct"],
             "turnover_100m": (r["turnover_yuan"] or 0) / 1e8}
            for r in rows
        ]
        return d, stocks

    async def run_explain(source: str, day: str | None, run: bool) -> dict:
        d, stocks = explain_input(source, day)
        cfg = app.state.ai
        if run and not cfg.configured:
            raise HTTPException(400, "AI 未設定：請設定環境變數 OPENMARKET_AI_KEY（以及 OPENMARKET_AI_FORMAT／BASE_URL／MODEL）後重新啟動")
        async with httpx.AsyncClient(
            timeout=30, headers={"User-Agent": USER_AGENT}, follow_redirects=True, transport=ai_transport
        ) as http:
            fetcher = headline_fetcher or fetch_headlines

            async def headlines(name: str, code: str, when: date):
                return await fetcher(http, name, code, when)

            out = await explain_day(app.state.history, http, cfg, headlines, d, stocks, run=run)
        out["ai"] = cfg.public()
        return out

    @app.get("/api/ai/reasons")
    async def ai_reasons(source: str = "history", day: str | None = Query(None, alias="date")) -> dict:
        """Movers with cached explanations only — never calls the AI."""
        return await run_explain(source, day, run=False)

    @app.post("/api/ai/reasons")
    async def ai_explain(request: Request, source: str = "history", day: str | None = Query(None, alias="date")) -> dict:
        """Ask the AI for the movers that have no cached explanation yet (costs API calls)."""
        # a custom header forces a CORS preflight, so other web pages cannot trigger paid calls
        if request.headers.get("x-openmarket-action") != "explain":
            raise HTTPException(403, "missing X-OpenMarket-Action header")
        return await run_explain(source, day, run=True)

    # ---- 新聞熱門族群 (panel J and the `news` grouping) -------------------------------------------

    @app.get("/api/news-themes/status")
    def news_status() -> dict:
        store = app.state.history
        dates = store.news_dates_sorted(limit=1)
        st = app.state.news.state if app.state.news else None
        return {
            "ready": bool(dates),
            "count": len(store.news_dates()),
            "saved_at": dates[0].isoformat() if dates else None,
            "running": bool(st and st.running),
            "done": st.done if st else 0,
            "total": st.total if st else 0,
            "error": st.error if st else "",
        }

    @app.get("/api/news-themes")
    def news_themes(day: str | None = Query(None, alias="date")) -> dict:
        d = None
        if day:
            try:
                d = date.fromisoformat(day)
            except ValueError as exc:
                raise HTTPException(422, f"invalid date {day!r}") from exc
        names = stock_names()
        used, themes, method = themes_for_day(app.state.history, d, named_groups(), names)
        rows = {r["code"]: r for r in app.state.history.day_rows(d)} if d else {}
        out = []
        for t in themes:
            pcts = [rows[c]["change_pct"] for c in t["codes"] if c in rows and rows[c]["change_pct"] is not None]
            out.append({
                "name": t["name"],
                "aliases": t["aliases"],
                "score": t["score"],
                "prev_score": t["prev_score"],
                "titles": t["titles"][:3],
                "members": [{"code": c, "name": names.get(c, c), "change_pct": rows[c]["change_pct"] if c in rows else None} for c in t["codes"]],
                "avg_pct": sum(pcts) / len(pcts) if pcts else None,
                "strong_ratio": sum(p >= 5 for p in pcts) / len(pcts) * 100 if pcts else None,
            })
        bursts = heat_bursts(app.state.history, d, named_groups())
        hot = {b["term"] for b in bursts}
        for t in out:
            t["burst"] = t["name"] in hot or any(a in hot for a in t["aliases"])
        return {"date": day, "news_date": used.isoformat() if used else None, "method": method, "themes": out, "bursts": bursts}

    # ---- linkage: does the group move together? (spec 2026-10-23-linkage-design.md) ---------------

    YAHOO_REFRESH_HOURS = 6

    async def bars_for(http: httpx.AsyncClient, code: str, market: str, sessions: list[date]) -> tuple[dict, str]:
        store = app.state.history
        have = store.yahoo_bars(code, sessions)
        missing = [s for s in sessions if s not in have]
        fetched = store.yahoo_fetched_at(code)
        fresh = fetched and (datetime.now(fetched.tzinfo) - fetched).total_seconds() < YAHOO_REFRESH_HOURS * 3600
        # bars cached before open/volume were kept (4 fields) are fetched again, fresh or not
        old_format = any(bars and len(bars[0]) < 6 for bars in have.values())
        if (missing and not fresh) or old_format:
            try:
                by_day = await fetch_bars(http, code, market)
                store.save_yahoo_bars(code, by_day, datetime.now(TAIPEI))
                have = store.yahoo_bars(code, sessions)
            except Exception as exc:  # Yahoo is unofficial: degrade, never fail the panel
                return have, f"Yahoo 失敗：{type(exc).__name__}"
        return have, ""

    async def minute_bars_for(http: httpx.AsyncClient, code: str, market: str, day: date) -> tuple[list | None, str]:
        """1-minute bars for the peak time, cached once the session is over; None when unavailable."""
        store = app.state.history
        cached = store.yahoo_1m(code, day)
        # bars cached before open/volume were kept (4 fields) are fetched again
        if cached is not None and (not cached or len(cached[0]) >= 6):
            return cached or None, ""
        now = datetime.now(TAIPEI)
        if (now.date() - day).days > ONE_MINUTE_DAYS:
            return None, ""
        try:
            bars = await fetch_day_1m(http, code, market, day)
        except Exception as exc:  # unofficial source: fall back to the 5-minute bars
            return None, f"Yahoo 1 分 K 失敗：{type(exc).__name__}"
        if day < now.date() or now.time() >= time(13, 35):
            store.save_yahoo_1m(code, day, bars)
        return bars or None, ""

    YAHOO_CONCURRENCY = 6  # members whose bars are fetched at the same time
    SESSION_MIN_POINTS = 15  # 5-minute returns one session needs for its own R (locked stretches leave fewer)

    async def linkage_payload(d: date, members: list[dict]) -> dict:
        """K body for `members` (day rows, the largest market cap first) on day d."""
        store = app.state.history
        codes = [m["code"] for m in members]
        daily = await asyncio.to_thread(daily_linkage, store, d, codes)
        recorded = store.tick_dates()
        sessions = sorted(store.trading_dates(up_to=d, limit=3))
        notes: list[str] = []
        per_code_sessions: dict[str, dict[date, dict]] = {c: {} for c in codes}
        peaks: dict[str, int | None] = {c: None for c in codes}
        sources = {}
        coarse: set[str] = set()  # members whose peak time is only known to 5 minutes
        prev = {m["code"]: m.get("prev_close") for m in members}
        race: dict[str, list] = {c: [] for c in codes}  # the shown day minute by minute

        def note(err: str) -> None:
            if err and err not in notes:
                notes.append(err)

        async with httpx.AsyncClient(timeout=20, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as http:
            for s in sessions:
                if s in recorded:
                    ticks = await asyncio.to_thread(store.ticks, s, set(codes))
                    sources[s] = "recorded"
                    for c in codes:
                        per_code_sessions[c][s] = bucket_closes(ticks[c])
                        if s == d:
                            peaks[c] = peak_minute_from_ticks(ticks[c])
                            race[c] = race_points([(ts, p, p, p) for ts, p in ticks[c]], prev[c])
            yahoo_sessions = [s for s in sessions if s not in recorded]
            gate = asyncio.Semaphore(YAHOO_CONCURRENCY)

            async def one(m: dict) -> None:
                c = m["code"]
                async with gate:
                    bars, err = await bars_for(http, c, m["market"], yahoo_sessions)
                    note(err)
                    for s in yahoo_sessions:
                        b = bars.get(s, [])
                        if b:
                            sources.setdefault(s, "yahoo")
                        per_code_sessions[c][s] = {int(x[0][:2]) * 12 + int(x[0][3:5]) // 5 - 108: x[3] for x in b}
                        if s == d:
                            b = align_bars(b, m)  # Yahoo back-adjusts: back to the official prices
                            peaks[c] = peak_minute_from_bars(b)
                            race[c] = race_points([(x[0], x[1], x[2], x[3]) for x in b], prev[c])
                    if d in yahoo_sessions:
                        # the peak time to the minute: 1-minute bars where Yahoo still has them
                        mb, err = await minute_bars_for(http, c, m["market"], d)
                        note(err)
                        mb = align_bars(mb, m) if mb else mb
                        if mb:
                            peaks[c] = peak_minute_from_bars(mb)
                            race[c] = race_points([(x[0], x[1], x[2], x[3]) for x in mb], prev[c])
                        else:
                            coarse.add(c)

            if yahoo_sessions:
                await asyncio.gather(*(one(m) for m in members))
            benchmarks = await index_race(http, d)
        axis = list(range(0, 55))
        rows_by_session = {s: {r["code"]: r for r in rs} for s, rs in (await asyncio.to_thread(store.rows, sessions)).items()}
        series = []
        for c in codes:
            r: list = []
            for s in sessions:
                closes = per_code_sessions[c].get(s, {})
                # locked limit-up stretches left out, as in N (a flat locked line says nothing)
                r.extend(returns(closes, axis, locked_level(closes, rows_by_session.get(s, {}).get(c))))
            series.append(r)
        matrix, r_intraday = pair_matrix(series, min_points=20)
        # the same R per session (今日／昨日／前日), for the 🔗 交集: one session has 54 returns at most
        step = len(axis) - 1
        by_session = [
            {"date": s.isoformat(), "matrix": pair_matrix([r[k * step:(k + 1) * step] for r in series], min_points=SESSION_MIN_POINTS)[0]}
            for k, s in enumerate(sessions)
        ]
        for m in members:  # 13:30 = the official close (no Yahoo bar covers the closing auction)
            if race[m["code"]] and m.get("change_pct") is not None:
                close = round(m["change_pct"], 2)
                race[m["code"]] = [p for p in race[m["code"]] if p[0] < 270] + [[270, close, close, close]]
        peak_list = [peaks[c] for c in codes]
        std, lag = peak_stats(peak_list)
        inst = (await asyncio.to_thread(store.inst_net, [d])).get(d, {})  # 三大法人 net shares (posted after the close)
        return {
            "date": d.isoformat(),
            "members": [
                {
                    "code": m["code"], "name": m["name"], "market_cap": m["market_cap"], "change_pct": m["change_pct"],
                    "limit_up_pct": limit_up_pct(m.get("prev_close")),
                    "turnover_rate": turnover_rate(m), "amplitude_pct": amplitude_pct(m),
                    "inst_net": inst.get(m["code"]),
                }
                for m in members
            ],
            "daily": daily,
            "intraday": {"sessions": [{"date": s.isoformat(), "source": sources.get(s, "none")} for s in sessions], "r": r_intraday, "matrix": matrix, "by_session": by_session},
            "peaks": [{"code": c, "time": fmt_minute(p)} for c, p in zip(codes, peak_list)],
            "peak_resolution_min": 5 if any(peaks[c] is not None for c in coarse) else 1,
            "peak_std_min": std,
            "race": {"step_min": 5 if coarse else 1, "points": race},
            "leader_lag_min": lag,
            "benchmarks": benchmarks,
            "verdict": {"daily": verdict_r(daily.get("r20")), "intraday": verdict_r(r_intraday, INTRADAY_HIGH_R, INTRADAY_LOW_R), "timing": verdict_timing(std)},
            "notes": notes,
        }

    async def index_race(http: httpx.AsyncClient, d: date) -> list[dict]:
        """大盤 / 櫃買 for the top of K's timeline: 1m (else 5m) index bars aligned to the official index,
        ending on its close. A market without a stored index row that day is left out."""
        index = app.state.history.index_rows().get(d.isoformat(), {})

        async def one(code: str, name: str, market: str) -> dict | None:
            row = index.get(market)
            if not row or row.get("close") is None or row.get("change") is None:
                return None
            prev = row["close"] - row["change"]
            bars, _ = await minute_bars_for(http, code, market, d)
            if not bars:
                got, _ = await bars_for(http, code, market, [d])
                bars = got.get(d, [])
            pts = race_points([(x[0], x[1], x[2], x[3]) for x in align_bars(bars, row)], prev) if bars else []
            if pts:
                close = round(row["change"] / prev * 100, 2)
                pts = [p for p in pts if p[0] < 270] + [[270, close, close, close]]
            return {"code": code, "name": name, "change_pct": round(row["change"] / prev * 100, 2), "points": pts}

        # both indexes at once: a slow Yahoo must not add its timeouts twice to every K load
        got = await asyncio.gather(*(one(code, name, market) for code, (name, market) in INDEX_SYMBOLS.items()))
        return [x for x in got if x is not None]

    def _day(day: str) -> date:
        try:
            return date.fromisoformat(day)
        except ValueError as exc:
            raise HTTPException(422, f"invalid date {day!r}") from exc

    @app.get("/api/history/linkage")
    async def linkage(group: str, day: str = Query(..., alias="date"), grouping: str = "industry") -> dict:
        d = _day(day)
        store = app.state.history
        g = get_grouping(f"news@{d.isoformat()}" if grouping == "news" else grouping)
        if g is None:
            raise HTTPException(422, f"grouping {grouping!r} is not available")
        rows = store.day_rows(d)
        if not rows:
            raise HTTPException(404, f"no data for {day}")
        members = top_members(rows, g, group)
        if len(members) < 2:
            raise HTTPException(404, "這個族群少於 2 檔普通股，無法計算連動性")
        return {**await linkage_payload(d, members), "group": group}

    # ---- N · 資金連動搜尋 (history/finder.py) -----------------------------------------------------

    FINDER_CONCURRENCY = 12  # Yahoo served 92 stocks in ~2 s at 6–24 at once (2026-10-24 test)
    NEWS_THEME_DAYS = 7  # 📰 only news days this close to the shown day (a gap in collection must not show old news)
    finder_running: dict[tuple, asyncio.Task] = {}
    finder_progress: dict[tuple, dict] = {}  # (date, method, key) → {stage, done, total} while running

    async def finder_fetch(rows: list[dict], sessions: list[date], done=lambda: None) -> dict[str, tuple[dict, int]]:
        """Bars for the finder: cached 1m first, else one 1m request per stock for all sessions (last ~30
        days), else the 5m bars; new 1m bars are saved in one transaction."""
        store = app.state.history
        codes = [r["code"] for r in rows]
        cached = await asyncio.to_thread(store.yahoo_1m_many, codes, sessions)
        now = datetime.now(TAIPEI)
        minute_ok = (now.date() - sessions[0]).days <= ONE_MINUTE_DAYS
        finished = lambda s: s < now.date() or now.time() >= time(13, 35)  # noqa: E731
        out: dict[str, tuple[dict, int]] = {}
        new: list[tuple[str, date, list]] = []
        gate = asyncio.Semaphore(FINDER_CONCURRENCY)
        async with httpx.AsyncClient(timeout=20, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as http:

            async def one(r: dict) -> None:
                try:
                    await one_stock(r)
                finally:
                    done()

            async def one_stock(r: dict) -> None:
                c = r["code"]
                have = {s: cached[(c, s)] for s in sessions if (c, s) in cached and (not cached[(c, s)] or len(cached[(c, s)][0]) >= 6)}
                if minute_ok and len(have) < len(sessions):
                    try:
                        async with gate:
                            by_day = await fetch_span_1m(http, c, r["market"], sessions[0], sessions[-1])
                        for s in sessions:
                            if s not in have:
                                have[s] = by_day.get(s, [])
                                if finished(s):
                                    new.append((c, s, have[s]))
                    except Exception:  # unofficial source: this stock falls back to the 5m bars
                        pass
                if minute_ok and have.get(sessions[-1]):
                    out[c] = ({s: have.get(s, []) for s in sessions}, 1)
                    return
                async with gate:
                    bars, _ = await bars_for(http, c, r["market"], sessions)
                if bars.get(sessions[-1]):
                    out[c] = ({s: bars.get(s, []) for s in sessions}, 5)

            await asyncio.gather(*(one(r) for r in rows))
        await asyncio.to_thread(store.save_yahoo_1m_many, new)
        return out

    def finder_groupings(names: tuple[str, ...], day: date) -> tuple[dict, list[str]]:
        found, missing = {}, []
        for n in names:
            g = get_grouping(f"news@{day.isoformat()}" if n == "news" else n)
            if g is None:
                missing.append(n)
            else:
                found[n] = g
        return found, missing

    def finder_titles(day: date) -> list[str]:
        store = app.state.history
        titles: list[str] = []
        for d in store.news_dates_sorted(up_to=day, limit=3):
            for term in store.news_day(d).values():
                titles.extend(t["title"] for t in term.get("titles", []) if t.get("title"))
        return titles + store.ptt_titles(day)

    def finder_params(query: Mapping[str, str]) -> FinderParams:
        """Any FinderParams field can come from the query string (lists comma-separated, '' = None)."""
        import dataclasses

        base = FinderParams()
        values = {}
        for f in dataclasses.fields(FinderParams):
            if f.name not in query:
                continue
            raw, default = query[f.name], getattr(base, f.name)
            try:
                if isinstance(default, bool):
                    values[f.name] = raw.lower() in ("1", "true", "yes", "on")
                elif isinstance(default, tuple):
                    values[f.name] = tuple(x for x in raw.split(",") if x)
                elif raw == "" and f.name == "start_gap":
                    values[f.name] = None
                elif isinstance(default, int) or f.name == "start_gap":
                    values[f.name] = int(raw)
                else:
                    values[f.name] = float(raw)
            except ValueError as exc:
                raise HTTPException(422, f"{f.name}: {raw!r}") from exc
        return dataclasses.replace(base, **values)

    async def finder_result(d: date, method: str, p: FinderParams, refresh: bool = False, stored_only: bool = False) -> dict:
        store = app.state.history
        groupings, missing = finder_groupings(p.groupings, d)
        key = p.key() + "|" + ",".join(sorted(groupings))
        def with_history(res: dict) -> dict:
            # 🔁 the same combination on the earlier days of the window (stored results only, never computed)
            earlier_days = store.trading_dates(up_to=d, limit=FINDER_PRECOMPUTE_DAYS)[1:]
            earlier = {e.isoformat(): r for e in earlier_days if (r := store.finder(e, method, key)) is not None}
            groups = persistence(res.get("groups", []), earlier)
            # 📰 the news keywords naming each member (the latest 3 news days within a week up to d), attached, not stored
            news_dates = [x for x in store.news_dates_sorted(up_to=d, limit=3) if (d - x).days <= NEWS_THEME_DAYS]
            news = [store.news_day(x) for x in news_dates]
            # 🏦 法人 read now, not from the stored result: it is published after the close
            by_code = {r["code"]: r for r in store.day_rows(d)}
            groups = inst_summary(groups, store.inst_net([d]).get(d, {}), by_code)
            # 法人連買／連賣 over the latest 法人 days up to d
            # on trading days, stopping at the first one without 法人: a gap must not join two runs
            have = store.inst_dates()
            inst_days = list(takewhile(lambda x: x in have, store.trading_dates(up_to=d, limit=INST_STREAK_DAYS)))
            member_codes = {m["code"] for g in groups for m in g["members"]}  # 20 days × the cards' stocks only
            groups = inst_streak(groups, store.inst_net(inst_days, member_codes), inst_days)
            # 外資／投信／自營 summed over the members, in 張 (their motives differ: 投信 themes, 外資 weights)
            split = store.inst_split(d)

            def by_kind(g: dict) -> dict | None:
                rows = [split[m["code"]] for m in g["members"] if m["code"] in split]
                return {k: round(sum(r[i] for r in rows) / 1000) for i, k in enumerate(("foreign", "trust", "dealer"))} if rows else None

            groups = [{**g, "inst_split": by_kind(g)} for g in groups]
            # 投信連買／連賣: the same streak on 投信 alone (theme / window-dressing positioning)
            trust = inst_streak(groups, store.inst_trust(inst_days, member_codes), inst_days)
            groups = [{**g, "trust_streak": t["inst_streak"]} for g, t in zip(groups, trust)]
            # 💳 融資融券 (leveraged / retail money) on d, and 融資連增／連減 over the latest margin days
            margin_have = store.margin_dates()
            margin_days = list(takewhile(lambda x: x in margin_have, store.trading_dates(up_to=d, limit=INST_STREAK_DAYS)))
            margin_rows = store.margin(margin_days, member_codes)
            groups = margin_summary(groups, margin_rows.get(d, {}))
            streak = inst_streak(groups, margin_changes(margin_rows), margin_days)
            groups = [{**g, "margin_streak": t["inst_streak"]} for g, t in zip(groups, streak)]
            return {**res, "groups": finder_news_themes(groups, news, [x.isoformat() for x in news_dates])}

        if not refresh:
            hit = await asyncio.to_thread(store.finder, d, method, key)
            if hit is not None:
                return {**await asyncio.to_thread(with_history, hit), "cached": True, "missing_groupings": missing}
        if stored_only:  # another panel peeking (B's 🔗): never start a search for it
            return {"date": d.isoformat(), "method": method, "groups": [], "stored": False, "cached": False, "missing_groupings": missing}
        k = (d, method, key)
        task = finder_running.get(k)
        if task is None:
            async def go() -> dict:
                t0 = datetime.now()

                def report(stage: str, done: int, total: int) -> None:
                    finder_progress[k] = {"stage": stage, "done": done, "total": total, "seconds": round((datetime.now() - t0).total_seconds(), 1)}

                res = await run_search(store, d, method, p, groupings, finder_fetch, finder_titles(d), report)
                res["stats"]["seconds"]["total"] = round((datetime.now() - t0).total_seconds(), 2)
                await asyncio.to_thread(store.save_finder, d, method, key, res)
                return res
            task = finder_running[k] = asyncio.create_task(go())
            task.add_done_callback(lambda _: (finder_running.pop(k, None), finder_progress.pop(k, None)))
        res = await task
        return {**await asyncio.to_thread(with_history, res), "cached": False, "missing_groupings": missing}

    FINDER_PRECOMPUTE_DAYS = 5  # the latest stored days kept ready, newest first
    FINDER_PRECOMPUTE_PAUSE = 5  # seconds between two real runs, so the app stays responsive

    async def finder_precompute() -> None:
        """After the close, keep both searches with the default thresholds ready for the latest
        FINDER_PRECOMPUTE_DAYS days (a stored day returns at once; only missing ones are computed)."""
        await asyncio.sleep(180)  # let the start-up collectors settle first
        while True:
            try:
                for day in app.state.history.trading_dates(limit=FINDER_PRECOMPUTE_DAYS):
                    _, missing = finder_groupings(FinderParams().groupings, day)
                    if missing:  # concept / chain groups not loaded yet: try again next round
                        break
                    for method in ("known", "new"):
                        res = await finder_result(day, method, FinderParams())
                        if not res.get("cached"):
                            await asyncio.sleep(FINDER_PRECOMPUTE_PAUSE)
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.getLogger(__name__).exception("finder precompute failed")
            await asyncio.sleep(600)

    @app.get("/api/history/finder")
    async def finder_api(
        request: Request, day: str = Query(..., alias="date"), method: str = Query("known", pattern="^(known|new)$"),
        refresh: bool = False, stored_only: bool = False,
    ) -> dict:
        d = _day(day)
        if not app.state.history.day_rows(d):
            raise HTTPException(404, f"no data for {day}")
        return await finder_result(d, method, finder_params(request.query_params), refresh, stored_only)

    @app.get("/api/history/finder/progress")
    def finder_progress_api(request: Request, day: str = Query(..., alias="date"), method: str = Query("known", pattern="^(known|new)$")) -> dict:
        """Where a running N search is: {running, stage, done, total, seconds}."""
        d = _day(day)
        p = finder_params(request.query_params)
        groupings, _ = finder_groupings(p.groupings, d)
        k = (d, method, p.key() + "|" + ",".join(sorted(groupings)))
        now = finder_progress.get(k)
        return {"running": now is not None, **(now or {})}

    @app.get("/api/history/linkage-codes")
    async def linkage_codes(codes: str, day: str = Query(..., alias="date")) -> dict:
        """K's view for any set of stocks (a group found by N)."""
        d = _day(day)
        wanted = [c for c in codes.split(",") if c][:40]
        rows = [r for r in app.state.history.day_rows(d) if r["code"] in wanted and r.get("kind") == "stock"]
        if len(rows) < 2:
            raise HTTPException(404, "至少要 2 檔有資料的股票")
        rows.sort(key=lambda r: -(r.get("market_cap") or 0))
        return await linkage_payload(d, rows)

    PAIR_DAYS = 20  # 同漲同跌 over this many trading days
    PAIR_FINDER_DAYS = 5  # N results of the latest this many days

    @app.get("/api/history/pairs")
    async def history_pairs(codes: str, day: str = Query(..., alias="date")) -> dict:
        """K's 🔗 交集 of the picked stocks, pair by pair: 同漲同跌, shared groups, N sightings, shared news themes."""
        d = _day(day)
        store = app.state.history
        wanted = list(dict.fromkeys(c for c in codes.split(",") if c))[:10]
        if len(wanted) < 2:
            raise HTTPException(422, "至少要 2 檔")

        def build() -> list[dict]:
            rows = {r["code"]: r for r in store.day_rows(d)}
            groupings, _ = finder_groupings(("industry", "custom", "concept", "chain"), d)
            dates = sorted(store.trading_dates(up_to=d, limit=PAIR_DAYS))
            pct = {x: {r["code"]: r["change_pct"] for r in rs if r["code"] in wanted} for x, rs in store.change_rows(dates).items()}
            found = store.finder_any(store.trading_dates(up_to=d, limit=PAIR_FINDER_DAYS))
            news_dates = [x for x in store.news_dates_sorted(up_to=d, limit=3) if (d - x).days <= NEWS_THEME_DAYS]
            return pair_extras(wanted, rows, groupings, pct, found, [store.news_day(x) for x in news_dates])

        return {"date": d.isoformat(), "days": PAIR_DAYS, "pairs": await asyncio.to_thread(build)}

    @app.get("/api/history/intraday")
    async def stock_intraday(code: str, day: str = Query(..., alias="date")) -> dict:
        """One stock's session minute by minute for K's chart beside the animation: Yahoo 1-minute bars
        (last ~30 days), else the 5-minute bars, else the app's own polls (no volume)."""
        try:
            d = date.fromisoformat(day)
        except ValueError as exc:
            raise HTTPException(422, f"invalid date {day!r}") from exc
        store = app.state.history
        rows = [r for r in store.stock_rows(code, d, 1) if r["date"] == d.isoformat()]
        if not rows:
            raise HTTPException(404, f"no data for {code} on {day}")
        r = rows[0]
        bars, step, source, note = [], 1, "none", ""
        async with httpx.AsyncClient(timeout=20, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as http:
            mb, err = await minute_bars_for(http, code, r["market"], d)
            if mb:
                bars, source = minute_bars(align_bars(mb, r)), "yahoo"
            else:
                got, err5 = await bars_for(http, code, r["market"], [d])
                if got.get(d):
                    bars, step, source = minute_bars(align_bars(got[d], r)), 5, "yahoo"
                elif d in store.tick_dates():
                    ticks = await asyncio.to_thread(store.ticks, d, {code})
                    bars, source = tick_bars(ticks.get(code, [])), "recorded"
                note = err or err5
        return {
            "code": code,
            "name": r["name"],
            "date": d.isoformat(),
            "prev_close": r["prev_close"],
            "limit_up_pct": limit_up_pct(r["prev_close"]),
            "limit_down_pct": limit_down_pct(r["prev_close"]),
            "day": {k: r[k] for k in ("open", "high", "low", "close", "change", "change_pct", "volume_shares", "turnover_yuan")},
            "step_min": step,
            "source": source,
            "bars": with_close_bar(bars, r),
            "note": note,
        }

    @app.get("/api/counties/status")
    def counties_status() -> dict:
        loader = app.state.counties
        return loader.status() if loader is not None else {"ready": False, "count": 0, "running": False, "done": 0, "total": 0, "error": "", "saved_at": None}

    @app.get("/api/chains/status")
    def chains_status() -> dict:
        loader = app.state.chains
        return loader.status() if loader is not None else {"ready": False, "count": 0, "running": False, "done": 0, "total": 0, "error": "", "saved_at": None}

    # bonus-03: which concept / custom / 細產業 groups a stock belongs to (for the info cards)
    @app.get("/api/membership/{code}")
    def membership(code: str) -> dict:
        loader = app.state.concepts
        concepts = loader.mapping.get(code, []) if loader is not None else []
        chain_loader = app.state.chains
        chains = chain_loader.mapping.get(code, []) if chain_loader is not None else []
        return {"code": code, "concepts": concepts, "chains": chains, "custom": groups.mapping().get(code, [])}

    # bonus-17: code → group names, for regrouping the live heatmap in the browser
    @app.get("/api/groupings/{name}")
    def grouping_map(name: str) -> dict:
        if name == "custom":
            return {"name": name, "mapping": groups.mapping()}
        if name == "concept":
            loader = app.state.concepts
            if loader is None or not loader.mapping:
                raise HTTPException(404, "concept groups not loaded yet")
            return {"name": name, "mapping": loader.mapping}
        if name == "chain":
            loader = app.state.chains
            if loader is None or not loader.mapping:
                raise HTTPException(404, "細產業分類尚未載入完成")
            return {"name": name, "mapping": loader.mapping}
        if name == "news":
            _, themes, _ = themes_for_day(app.state.history, None, named_groups(), stock_names())
            if not themes:
                raise HTTPException(404, "新聞族群尚未整理完成")
            return {"name": name, "mapping": themes_mapping(themes)}
        if name == "county":  # code → [head-office county] for the map view
            loader = app.state.counties
            if loader is None or not loader.mapping:
                raise HTTPException(404, "公司地址資料尚未載入完成")
            return {"name": name, "mapping": loader.mapping}
        raise HTTPException(422, "grouping must be custom, concept, chain, news or county")

    @app.get("/api/groups")
    def list_groups() -> dict:
        return {"groups": groups.all()}

    @app.put("/api/groups/{name}")
    def create_group(name: str) -> dict:
        return _groups_call(groups.create, name)

    @app.post("/api/groups/{name}/rename")
    def rename_group(name: str, body: RenameBody) -> dict:
        return _groups_call(groups.rename, name, body.name)

    @app.delete("/api/groups/{name}")
    def delete_group(name: str) -> dict:
        return _groups_call(groups.delete, name)

    @app.put("/api/groups/{name}/{code}")
    def add_to_group(name: str, code: str) -> dict:
        return _groups_call(groups.add, name, code)

    @app.delete("/api/groups/{name}/{code}")
    def remove_from_group(name: str, code: str) -> dict:
        return _groups_call(groups.remove, name, code)

    if static_dir.is_dir():
        # Windows takes MIME types from the registry, where .js may not be text/javascript;
        # browsers refuse ES modules served with the wrong type.
        mimetypes.add_type("text/javascript", ".js")
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    return app

