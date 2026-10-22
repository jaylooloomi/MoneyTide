import pytest

from openmarket.groups import GroupStore


def test_group_crud_and_mapping(tmp_path):
    g = GroupStore(tmp_path / "g.json")
    assert g.all() == []
    g.create("散熱")
    g.create("AI 伺服器")
    g.create("散熱")  # idempotent
    g.add("散熱", "3017")
    g.add("散熱", "3324")
    g.add("AI 伺服器", "3017")
    g.add("散熱", "3017")  # no duplicate
    assert [x["name"] for x in g.all()] == ["散熱", "AI 伺服器"]
    assert g.mapping() == {"3017": ["散熱", "AI 伺服器"], "3324": ["散熱"]}
    g.remove("散熱", "3017")
    assert g.mapping()["3017"] == ["AI 伺服器"]
    g.rename("散熱", "散熱模組")
    assert g.mapping()["3324"] == ["散熱模組"]
    g.delete("AI 伺服器")
    assert "3017" not in g.mapping()
    assert GroupStore(tmp_path / "g.json").all() == [{"name": "散熱模組", "codes": ["3324"]}]


def test_group_validation(tmp_path):
    g = GroupStore(tmp_path / "g.json")
    for bad in ("", "  ", "a/b", "x" * 31, "<b>"):
        with pytest.raises(ValueError):
            g.create(bad)
    g.create("A")
    g.create("B")
    with pytest.raises(ValueError):
        g.add("A", "bad!")
    with pytest.raises(KeyError):
        g.add("nope", "2330")
    with pytest.raises(ValueError):
        g.rename("A", "B")
    with pytest.raises(KeyError):
        g.rename("zzz", "C")
