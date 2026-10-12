import asyncio
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from openmarket.api import create_app
from openmarket.config import TAIPEI, AppConfig
from openmarket.models import Quote, StockInfo
from openmarket.poller import Poller
from openmarket.storage import JsonCache, SettingsStore


class Clock:
    t = datetime(2026, 10, 12, 10, 0, tzinfo=TAIPEI)

    def __call__(self):
        return self.t


@pytest.fixture
def setup(tmp_path):
    clock = Clock()

    async def quotes():
        return [Quote("2330", "台積電", 100.0, 1.0, 1.0, 2.0, 1.0, 99, 101, 98, 99, 10, 1.0)]

    async def infos():
        return {"2330": StockInfo("2330", "台積電", "半導體業", "上市", "stock")}

    async def shares():
        return {"2330": 10}

    poller = Poller(
        fetch_quotes=quotes,
        fetch_infos=infos,
        fetch_shares=shares,
        info_cache=JsonCache(tmp_path / "i.json"),
        shares_cache=JsonCache(tmp_path / "s.json"),
        settings=SettingsStore(tmp_path / "settings.json"),
        clock=clock,
    )
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<h1>hi</h1>", encoding="utf-8")
    app = create_app(AppConfig(data_dir=tmp_path), poller=poller, start_polling=False, static_dir=static)
    with TestClient(app) as client:
        yield client, poller, clock


def test_snapshot_and_etag(setup):
    client, poller, _ = setup
    r = client.get("/api/snapshot")
    assert r.status_code == 200 and r.json()["status"] == "error"
    asyncio.run(poller.refresh_reference())
    asyncio.run(poller.fetch_once())
    r = client.get("/api/snapshot")
    body = r.json()
    assert body["status"] == "ok" and body["stocks"][0]["industry"] == "半導體業"
    etag = r.headers["etag"]
    r2 = client.get("/api/snapshot", headers={"If-None-Match": etag})
    assert r2.status_code == 304
    r3 = client.get("/api/snapshot", headers={"If-None-Match": '"0"'})
    assert r3.status_code == 200


def test_settings(setup):
    client, _, _ = setup
    assert client.get("/api/settings").json() == {"poll_seconds": 60}
    assert client.put("/api/settings", json={"poll_seconds": 45}).json() == {"poll_seconds": 45}
    assert client.put("/api/settings", json={"poll_seconds": 10}).status_code == 422
    assert client.put("/api/settings", json={"poll_seconds": "x"}).status_code == 422
    assert client.get("/api/settings").json() == {"poll_seconds": 45}


def test_refresh_throttle(setup):
    client, poller, clock = setup
    assert client.post("/api/refresh").status_code == 202
    asyncio.run(poller.fetch_once())
    r = client.post("/api/refresh")
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0


def test_watchlist_crud(setup):
    client, _, _ = setup
    assert client.get("/api/watchlist").json() == {"codes": []}
    assert client.put("/api/watchlist/2330").json() == {"codes": ["2330"]}
    assert client.put("/api/watchlist/00878").json() == {"codes": ["2330", "00878"]}
    assert client.put("/api/watchlist/bad!").status_code == 422
    assert client.delete("/api/watchlist/2330").json() == {"codes": ["00878"]}


def test_static_index(setup):
    client, _, _ = setup
    assert "hi" in client.get("/").text
