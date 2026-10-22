"""User-defined stock groups (自訂族群), stored in data/groups.json.

A stock may belong to several groups. Group order and code order are kept as entered.
"""

from __future__ import annotations

import threading
from pathlib import Path

from .storage import CODE_RE, _read_json, _write_json_atomic

MAX_NAME_LEN = 30


def _check_name(name: str) -> str:
    name = name.strip()
    # "," separates names in /api/history/index?groups=; "." / ".." are normalised away in URL paths
    if (not name or len(name) > MAX_NAME_LEN or any(c in name for c in "/\\<>\"',")
            or set(name) <= {"."}):
        raise ValueError(f"invalid group name: {name!r}")
    return name


def _check_code(code: str) -> str:
    if not CODE_RE.match(code):
        raise ValueError(f"invalid stock code: {code!r}")
    return code


class GroupStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def all(self) -> list[dict]:
        raw = _read_json(self.path)
        groups = raw.get("groups") if isinstance(raw, dict) else None
        out = []
        for g in groups if isinstance(groups, list) else []:
            if isinstance(g, dict) and isinstance(g.get("name"), str) and isinstance(g.get("codes"), list):
                out.append({"name": g["name"], "codes": [c for c in g["codes"] if isinstance(c, str) and CODE_RE.match(c)]})
        return out

    def _save(self, groups: list[dict]) -> list[dict]:
        _write_json_atomic(self.path, {"groups": groups})
        return groups

    def create(self, name: str) -> list[dict]:
        name = _check_name(name)
        with self._lock:
            groups = self.all()
            if not any(g["name"] == name for g in groups):
                groups.append({"name": name, "codes": []})
            return self._save(groups)

    def delete(self, name: str) -> list[dict]:
        with self._lock:
            return self._save([g for g in self.all() if g["name"] != name])

    def rename(self, name: str, new_name: str) -> list[dict]:
        new_name = _check_name(new_name)
        with self._lock:
            groups = self.all()
            if any(g["name"] == new_name for g in groups if g["name"] != name):
                raise ValueError(f"group already exists: {new_name!r}")
            target = next((g for g in groups if g["name"] == name), None)
            if target is None:
                raise KeyError(name)
            target["name"] = new_name
            return self._save(groups)

    def add(self, name: str, code: str) -> list[dict]:
        code = _check_code(code)
        with self._lock:
            groups = self.all()
            target = next((g for g in groups if g["name"] == name), None)
            if target is None:
                raise KeyError(name)
            if code not in target["codes"]:
                target["codes"].append(code)
            return self._save(groups)

    def remove(self, name: str, code: str) -> list[dict]:
        with self._lock:
            groups = self.all()
            for g in groups:
                if g["name"] == name:
                    g["codes"] = [c for c in g["codes"] if c != code]
            return self._save(groups)

    def mapping(self) -> dict[str, list[str]]:
        """code → group names."""
        out: dict[str, list[str]] = {}
        for g in self.all():
            for c in g["codes"]:
                out.setdefault(c, []).append(g["name"])
        return out
