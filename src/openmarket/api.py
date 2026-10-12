from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import STATIC_DIR, AppConfig
from .poller import Poller, RefreshTooSoon
from .sources.histock import fetch_quotes
from .sources.http import make_client
from .sources.shares import fetch_shares
from .sources.twse_isin import fetch_isin
from .storage import JsonCache, SettingsStore, Watchlist


class SettingsBody(BaseModel):
    poll_seconds: int


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
    static_dir: Path = STATIC_DIR,
) -> FastAPI:
    config = config or AppConfig.from_env()
    settings = SettingsStore(config.data_dir / "settings.json")
    watchlist = Watchlist(config.data_dir / "watchlist.json")

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client = None
        if app.state.poller is None:
            client = make_client()
            app.state.poller = build_poller(client, config.data_dir, settings)
        task = asyncio.create_task(app.state.poller.run()) if start_polling else None
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            if client is not None:
                await client.aclose()

    app = FastAPI(title="Open Market", lifespan=lifespan)
    app.state.poller = poller

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

    @app.put("/api/settings")
    def put_settings(body: SettingsBody) -> dict:
        try:
            result = settings.set_poll_seconds(body.poll_seconds)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if app.state.poller is not None:
            app.state.poller.settings_changed()
        return result

    @app.post("/api/refresh", status_code=202)
    def refresh() -> dict:
        try:
            get_poller().request_refresh()
        except RefreshTooSoon as exc:
            raise HTTPException(
                429, str(exc), headers={"Retry-After": str(int(exc.retry_after) + 1)}
            ) from exc
        return {"accepted": True}

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

    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    return app
