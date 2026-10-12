from datetime import datetime, timedelta

import pytest

from openmarket.config import TAIPEI
from openmarket.storage import JsonCache, SettingsStore, Watchlist

NOW = datetime(2026, 10, 12, 10, 0, tzinfo=TAIPEI)


def test_cache_roundtrip_and_freshness(tmp_path):
    cache = JsonCache(tmp_path / "c.json")
    assert cache.load() is None
    assert not cache.is_fresh(NOW, 7)
    cache.save({"2330": "半導體業"}, NOW)
    data, saved_at = cache.load()
    assert data == {"2330": "半導體業"}
    assert saved_at == NOW
    assert cache.is_fresh(NOW + timedelta(days=6), 7)
    assert not cache.is_fresh(NOW + timedelta(days=7), 7)


def test_cache_corrupt_file_is_ignored(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("{not json", encoding="utf-8")
    assert JsonCache(p).load() is None


def test_settings_default_and_validation(tmp_path):
    s = SettingsStore(tmp_path / "s.json")
    assert s.get() == {"poll_seconds": 60}
    assert s.set_poll_seconds(30) == {"poll_seconds": 30}
    assert s.poll_seconds == 30
    for bad in (29, 601, "60", 45.5):
        with pytest.raises(ValueError):
            s.set_poll_seconds(bad)
    assert s.poll_seconds == 30


def test_watchlist_add_remove_dedupe_and_validation(tmp_path):
    w = Watchlist(tmp_path / "w.json")
    assert w.codes() == []
    assert w.add("2330") == ["2330"]
    assert w.add("00878") == ["2330", "00878"]
    assert w.add("2330") == ["2330", "00878"]
    assert w.remove("2330") == ["00878"]
    assert w.remove("9999") == ["00878"]
    for bad in ("", "23", "2330; rm", "../x", "abcd"):
        with pytest.raises(ValueError):
            w.add(bad)
    assert Watchlist(tmp_path / "w.json").codes() == ["00878"]


def test_settings_kept_in_memory_and_survive_unreadable_file(tmp_path):
    p = tmp_path / "s.json"
    s = SettingsStore(p)
    s.set_poll_seconds(90)
    p.unlink()
    assert s.poll_seconds == 90  # no disk read per access
    assert SettingsStore(p).poll_seconds == 60


def test_watchlist_write_aborts_when_file_unreadable(tmp_path, monkeypatch):
    from pathlib import Path

    w = Watchlist(tmp_path / "w.json")
    w.add("2330")
    w.add("2317")
    real = Path.read_text

    def locked(self, *a, **kw):
        if self.name == "w.json":
            raise PermissionError(13, "Permission denied")
        return real(self, *a, **kw)

    monkeypatch.setattr(Path, "read_text", locked)
    with pytest.raises(PermissionError):
        w.add("2454")
    monkeypatch.setattr(Path, "read_text", real)
    assert w.codes() == ["2330", "2317"]  # nothing lost


def test_cache_and_settings_tolerate_unreadable_files(tmp_path, monkeypatch):
    from pathlib import Path

    def locked(self, *a, **kw):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "read_text", locked)
    assert JsonCache(tmp_path / "c.json").load() is None
    assert SettingsStore(tmp_path / "s.json").poll_seconds == 60
