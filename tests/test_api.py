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
    app = create_app(AppConfig(data_dir=tmp_path), poller=poller, start_polling=False, start_history=False, start_concepts=False, static_dir=static)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client, poller, clock


def test_snapshot_and_etag(setup):
    client, poller, _ = setup
    r = client.get("/api/snapshot")
    assert r.status_code == 200 and r.json()["status"] == "loading"
    asyncio.run(poller.refresh_reference())
    asyncio.run(poller.fetch_once())
    r = client.get("/api/snapshot")
    body = r.json()
    assert body["status"] == "ok" and body["stocks"][0]["industry"] == "半導體業"
    etag = r.headers["etag"]
    r2 = client.get("/api/snapshot", headers={"If-None-Match": etag})
    assert r2.status_code == 304
    assert r2.headers["etag"] == etag
    r3 = client.get("/api/snapshot", headers={"If-None-Match": '"x-0"'})
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
    assert r.json()["retry_after"] == int(r.headers["retry-after"])


def test_foreign_host_rejected(setup):
    client, _, _ = setup
    assert client.get("/api/settings", headers={"Host": "evil.example"}).status_code == 400
    assert client.get("/api/settings", headers={"Host": "testserver"}).status_code == 400
    assert client.get("/api/settings", headers={"Host": "localhost:8765"}).status_code == 200


def test_js_served_as_javascript(setup, tmp_path):
    client, _, _ = setup
    (tmp_path / "static" / "app.js").write_text("export {}", encoding="utf-8")
    r = client.get("/app.js")
    assert r.headers["content-type"].startswith("text/javascript")


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


def test_history_endpoints(setup, tmp_path):
    from datetime import date, datetime

    from openmarket.config import TAIPEI
    from openmarket.history.ingest import build_rows
    from openmarket.sources.official import DailyRow

    client, _, _ = setup
    store = client.app.state.history
    infos = {"2330": StockInfo("2330", "台積電", "半導體業", "上市", "stock")}
    for d, close in ((date(2026, 10, 20), 100), (date(2026, 10, 21), 110)):
        store.save_day(d, build_rows([DailyRow("2330", "台積電", "上市", close, 10, close, close, close, 1000, 1e8)], infos, {"2330": 1}),
                       datetime(2026, 10, 21, 16, tzinfo=TAIPEI))
    days = client.get("/api/history/days").json()
    assert days["days"][0] == {"date": "2026-10-21", "status": "ok"} and days["backfill"]["running"] is False
    assert client.get("/api/history/day/2026-10-21").json()["stocks"][0]["price"] == 110
    assert client.get("/api/history/day/2026-10-18").status_code == 404
    assert client.get("/api/history/day/bad").status_code == 422
    g = client.get("/api/history/groups", params={"date": "2026-10-21", "threshold": 5}).json()
    assert g["groups"][0]["name"] == "半導體業" and g["groups"][0]["strong_ratio"] == 100
    rot = client.get("/api/history/rotation", params={"days": 5, "metric": "avg_pct"}).json()
    assert rot["dates"] == ["2026-10-20", "2026-10-21"]
    assert client.get("/api/history/rotation", params={"metric": "x"}).status_code == 422
    mv = client.get("/api/history/movers", params={"to": "2026-10-21", "mode": "day", "value": 5}).json()
    assert mv["groups"][0]["stocks"][0]["code"] == "2330"
    assert client.get("/api/history/movers", params={"to": "2026-10-21", "mode": "nope"}).status_code == 422


def test_groups_api_and_custom_history(setup):
    from datetime import date, datetime

    from openmarket.config import TAIPEI
    from openmarket.history.ingest import build_rows
    from openmarket.sources.official import DailyRow

    client, _, _ = setup
    assert client.get("/api/groups").json() == {"groups": []}
    assert client.put("/api/groups/散熱").json() == {"groups": [{"name": "散熱", "codes": []}]}
    assert client.put("/api/groups/散熱/2330").json()["groups"][0]["codes"] == ["2330"]
    assert client.put("/api/groups/散熱/bad!").status_code == 422
    assert client.put("/api/groups/none/2330").status_code == 404
    assert client.post("/api/groups/散熱/rename", json={"name": "散熱模組"}).json()["groups"][0]["name"] == "散熱模組"

    store = client.app.state.history
    infos = {"2330": StockInfo("2330", "台積電", "半導體業", "上市", "stock")}
    store.save_day(date(2026, 10, 21), build_rows([DailyRow("2330", "台積電", "上市", 110, 10, 110, 110, 110, 1000, 1e8)], infos, {}),
                   datetime(2026, 10, 21, 16, tzinfo=TAIPEI))
    g = client.get("/api/history/groups", params={"date": "2026-10-21", "grouping": "custom"}).json()
    assert [x["name"] for x in g["groups"]] == ["散熱模組"]
    day = client.get("/api/history/day/2026-10-21", params={"grouping": "custom"}).json()
    assert day["stocks"][0]["industry"] == "散熱模組"
    assert client.get("/api/history/groups", params={"date": "2026-10-21", "grouping": "concept"}).status_code == 422
    assert client.get("/api/history/rotation", params={"grouping": "custom"}).status_code == 200
    assert client.delete("/api/groups/散熱模組/2330").json()["groups"][0]["codes"] == []
    assert client.delete("/api/groups/散熱模組").json() == {"groups": []}


def test_concept_grouping(tmp_path):
    from datetime import date, datetime

    from openmarket.concepts import ConceptLoader
    from openmarket.history.ingest import build_rows
    from openmarket.sources.official import DailyRow

    async def fetch(progress):
        return {}

    loader = ConceptLoader(cache=JsonCache(tmp_path / "c.json"), fetch=fetch)
    app = create_app(AppConfig(data_dir=tmp_path), start_polling=False, start_history=False, concepts=loader,
                     start_concepts=False, static_dir=tmp_path / "nostatic")
    with TestClient(app, base_url="http://127.0.0.1") as client:
        infos = {"2330": StockInfo("2330", "台積電", "半導體業", "上市", "stock")}
        client.app.state.history.save_day(date(2026, 10, 21), build_rows(
            [DailyRow("2330", "台積電", "上市", 110, 10, 110, 110, 110, 1000, 1e8)], infos, {}), datetime(2026, 10, 21, 16, tzinfo=TAIPEI))
        assert client.get("/api/concepts/status").json()["ready"] is False
        assert client.get("/api/history/groups", params={"date": "2026-10-21", "grouping": "concept"}).status_code == 422
        loader._set({"CoWoS": ["2330"], "AI": ["2330"]}, datetime(2026, 10, 21, tzinfo=TAIPEI))
        g = client.get("/api/history/groups", params={"date": "2026-10-21", "grouping": "concept"}).json()
        assert sorted(x["name"] for x in g["groups"]) == ["AI", "CoWoS"]
        assert client.get("/api/concepts/status").json()["count"] == 2
