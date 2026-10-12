import asyncio
import json
from datetime import datetime, timedelta

import pytest

from openmarket.config import TAIPEI
from openmarket.models import Quote, StockInfo
from openmarket.poller import Poller, RefreshTooSoon
from openmarket.storage import JsonCache, SettingsStore


def quote(code, change_pct=1.0):
    return Quote(code, code, 100.0, change_pct, change_pct, 0.0, 1.0, 100, 100, 100, 99, 10, 1.0)


class FakeClock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, **kw):
        self.t += timedelta(**kw)


class Source:
    """Async fake that returns queued results or raises queued exceptions."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        r = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        if isinstance(r, Exception):
            raise r
        return r


INFOS = {"2330": StockInfo("2330", "台積電", "半導體業", "上市", "stock")}


def make(tmp_path, quotes, infos=None, shares=None, clock=None):
    clock = clock or FakeClock(datetime(2026, 10, 12, 10, 0, tzinfo=TAIPEI))
    p = Poller(
        fetch_quotes=quotes,
        fetch_infos=infos or Source(INFOS),
        fetch_shares=shares or Source({"2330": 10}),
        info_cache=JsonCache(tmp_path / "isin.json"),
        shares_cache=JsonCache(tmp_path / "shares.json"),
        settings=SettingsStore(tmp_path / "settings.json"),
        clock=clock,
    )
    return p, clock


def run(coro):
    return asyncio.run(coro)


def test_initial_state_is_loading(tmp_path):
    p, _ = make(tmp_path, Source([quote("2330")]))
    assert p.snapshot.status == "loading"
    assert p.snapshot.stocks == []
    assert "載入中" in p.snapshot.message


def test_success_then_failure_keeps_old_data_as_stale_then_recovers(tmp_path):
    quotes = Source([quote("2330", 1.0)], RuntimeError("boom"), [quote("2330", 2.0)])
    p, _ = make(tmp_path, quotes)
    run(p.refresh_reference())

    run(p.fetch_once())
    assert p.snapshot.status == "ok" and p.snapshot.version == 1
    assert p.snapshot.stocks[0].change_pct == 1.0
    assert p.snapshot.stocks[0].industry == "半導體業"
    assert p.snapshot.stocks[0].market_cap == 1000.0
    etag1 = p.etag

    run(p.fetch_once())
    assert p.snapshot.status == "stale" and p.snapshot.version == 1
    assert p.snapshot.stocks[0].change_pct == 1.0
    assert "boom" in p.snapshot.message
    assert p.etag != etag1

    run(p.fetch_once())
    assert p.snapshot.status == "ok" and p.snapshot.version == 2
    assert p.snapshot.stocks[0].change_pct == 2.0
    assert p.snapshot.message == ""


def test_never_succeeded_is_error(tmp_path):
    p, _ = make(tmp_path, Source(RuntimeError("down")))
    run(p.fetch_once())
    assert p.snapshot.status == "error" and "down" in p.snapshot.message


def test_unchanged_snapshot_keeps_etag(tmp_path):
    p, _ = make(tmp_path, Source([quote("2330")]))
    run(p.refresh_reference())
    run(p.fetch_once())
    rev = p.revision
    p._rebuild()
    assert p.revision == rev


def test_snapshot_json_is_serialised_utf8(tmp_path):
    p, _ = make(tmp_path, Source([quote("2330")]))
    run(p.refresh_reference())
    run(p.fetch_once())
    data = json.loads(p.snapshot_json)
    assert data["stocks"][0]["industry"] == "半導體業"
    assert data["market_open"] is True


def test_reference_failure_keeps_cache_and_reports(tmp_path):
    infos = Source(RuntimeError("isin down"))
    p, clock = make(tmp_path, Source([quote("2330")]), infos=infos)
    run(p.refresh_reference())
    run(p.fetch_once())
    assert p.snapshot.status == "ok"
    assert p.snapshot.stocks[0].industry == "其他"
    assert "產業分類更新失敗" in p.snapshot.message
    assert "全部歸類為「其他」" in p.snapshot.message
    # retried at most once per hour
    run(p.refresh_reference())
    assert infos.calls == 1
    clock.advance(hours=1)
    run(p.refresh_reference())
    assert infos.calls == 2


def test_reference_loaded_from_cache_and_not_refetched_when_fresh(tmp_path):
    p, _ = make(tmp_path, Source([quote("2330")]))
    run(p.refresh_reference())
    infos, shares = Source(INFOS), Source({})
    p2, _ = make(tmp_path, Source([quote("2330")]), infos=infos, shares=shares)
    p2.load_reference_from_cache()
    run(p2.refresh_reference())
    assert infos.calls == 0 and shares.calls == 0
    run(p2.fetch_once())
    assert p2.snapshot.stocks[0].industry == "半導體業"


def test_reference_refetched_after_seven_days(tmp_path):
    p, clock = make(tmp_path, Source([quote("2330")]))
    run(p.refresh_reference())
    clock.advance(days=7)
    infos = Source(INFOS)
    p._fetch_infos = infos
    run(p.refresh_reference())
    assert infos.calls == 1


def test_manual_refresh_throttled(tmp_path):
    p, clock = make(tmp_path, Source([quote("2330")]))
    p.request_refresh()  # never fetched → allowed
    run(p.fetch_once())
    clock.advance(seconds=10)
    with pytest.raises(RefreshTooSoon) as err:
        p.request_refresh()
    assert 19 <= err.value.retry_after <= 20
    clock.advance(seconds=20)
    p.request_refresh()


def test_market_open_flag_follows_clock(tmp_path):
    clock = FakeClock(datetime(2026, 10, 12, 14, 0, tzinfo=TAIPEI))
    p, _ = make(tmp_path, Source([quote("2330")]), clock=clock)
    run(p.fetch_once())
    assert p.snapshot.market_open is False


def test_run_loop_fetches_on_start_and_on_manual_refresh(tmp_path):
    quotes = Source([quote("2330")])

    async def scenario():
        p, clock = make(tmp_path, quotes, clock=FakeClock(datetime(2026, 10, 17, 10, 0, tzinfo=TAIPEI)))
        task = asyncio.create_task(p.run())
        for _ in range(50):
            await asyncio.sleep(0.01)
            if quotes.calls:
                break
        assert quotes.calls == 1  # startup fetch even on Saturday
        clock.advance(seconds=31)
        p.request_refresh()
        for _ in range(50):
            await asyncio.sleep(0.01)
            if quotes.calls == 2:
                break
        assert quotes.calls == 2
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    run(scenario())
