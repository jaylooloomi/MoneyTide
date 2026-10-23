from __future__ import annotations

import asyncio
import contextlib
import json
import mimetypes
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel

from .config import STATIC_DIR, AppConfig
from .concepts import ConceptLoader
from .groups import GroupStore
from .history.api import create_history_router
from .history.metrics import industry_grouping, mapping_grouping
from .history.ingest import REQUEST_DELAY_SECONDS, HistoryCollector
from .history.store import HistoryStore
from .poller import Poller, RefreshTooSoon
from .sources.histock import fetch_quotes
from .sources.http import make_client
from .sources.official import fetch_tpex_day, fetch_twse_day
from .sources.official_index import fetch_index_month
from .sources.company_address import fetch_county_groups
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
    static_dir: Path = STATIC_DIR,
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost"),
) -> FastAPI:
    config = config or AppConfig.from_env()
    settings = SettingsStore(config.data_dir / "settings.json")
    watchlist = Watchlist(config.data_dir / "watchlist.json")
    groups = GroupStore(config.data_dir / "groups.json")

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
            )
            tasks.append(asyncio.create_task(app.state.collector.run()))
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

    app = FastAPI(title="Open Market", lifespan=lifespan)
    app.state.poller = poller
    app.state.history = history_store or HistoryStore(config.data_dir / "history.sqlite")
    app.state.collector = None
    app.state.concepts = concepts
    app.state.chains = chains
    app.state.counties = counties
    app.include_router(create_history_router(lambda: app.state.history, lambda: app.state.collector, get_grouping))
    # Local-only app: reject other Host headers (DNS rebinding could otherwise reach the PUT routes).
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(allowed_hosts))

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
        if name == "county":  # code → [head-office county] for the map view
            loader = app.state.counties
            if loader is None or not loader.mapping:
                raise HTTPException(404, "公司地址資料尚未載入完成")
            return {"name": name, "mapping": loader.mapping}
        raise HTTPException(422, "grouping must be custom, concept, chain or county")

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
