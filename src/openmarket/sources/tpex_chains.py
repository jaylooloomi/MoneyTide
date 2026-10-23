"""Fine-grained industry groups (細產業) from the TPEx 產業價值鏈資訊平台 (https://ic.tpex.org.tw).

- Index https://ic.tpex.org.tw/ links ~40 chains as `introduce.php?ic=<code>` (半導體, 被動元件…).
- Each chain page holds hidden member lists `<div id="companyList_<id>" title="<sub-category>">`
  (every list appears twice in the page). Members are links `company_basic.php?stk_code=<code>`;
  foreign companies without a Taiwan listing link to their own sites and are ignored.
- Some lists split further: `<div id="sc_link_<sid>" ...>&#9658;&nbsp;<name>&nbsp;(N家)</div>` with
  the members in `<table id="sc_company_<sid>">` — the finest level is used where it exists.
Group names: "<sub>／<finer>" for split lists, "<chain>／<sub>" otherwise; a name already taken by
another chain gets that chain as a prefix. Public government-run site, fetched politely.
"""

from __future__ import annotations

import asyncio
import html as htmllib
import re
from collections.abc import Awaitable, Callable

import httpx

from ..models import ParseError
from .http import get_with_retry

BASE_URL = "https://ic.tpex.org.tw/"
REQUEST_DELAY_SECONDS = 3.0
MIN_CHAINS = 30  # the live index has 40; fewer means the page changed

_CHAIN_LINK = re.compile(r'<a[^>]*href="introduce\.php\?ic=([0-9A-Z]+)"[^>]*>(.*?)</a>', re.S)
_LIST = re.compile(r'<div id="companyList_(\w+)" title="([^"]*)"')
_SUB_LINK = re.compile(r'<div id="sc_link_(\w+)"[^>]*>(.*?)</div>', re.S)
_SUB_TABLE = re.compile(r'<table id="sc_company_(\w+)"')
_CODE = re.compile(r'company_basic\.php\?stk_code=(\w+)')
_COUNT = re.compile(r"\(\d+家\)\s*$")


def clean_name(text: str) -> str:
    """Plain text, single spaces, and no characters that break group URLs or comma lists."""
    s = htmllib.unescape(re.sub(r"<[^>]+>", "", text)).replace("\xa0", " ").replace("►", "")
    s = _COUNT.sub("", re.sub(r"\s+", " ", s).strip()).strip()
    return s.replace("/", "／").replace(",", "、")


def parse_chain_index(page: str) -> list[tuple[str, str]]:
    """[(ic code, chain name)] in page order, deduplicated."""
    seen: dict[str, str] = {}
    for code, label in _CHAIN_LINK.findall(page):
        name = clean_name(label)
        if name and code not in seen:
            seen[code] = name
    return list(seen.items())


def _codes(fragment: str) -> list[str]:
    out: list[str] = []
    for c in _CODE.findall(fragment):
        if c not in out:
            out.append(c)
    return out


def parse_chain_page(page: str, chain: str) -> dict[str, list[str]]:
    """{group name: [codes]} for one chain page (names not yet de-duplicated across chains)."""
    starts = [(m.start(), m.group(1), clean_name(m.group(2))) for m in _LIST.finditer(page)]
    groups: dict[str, list[str]] = {}
    done: set[str] = set()
    for i, (pos, list_id, title) in enumerate(starts):
        if list_id in done:
            continue  # the page repeats every list
        done.add(list_id)
        end = starts[i + 1][0] if i + 1 < len(starts) else len(page)
        chunk = page[pos:end]
        subs = {sid: clean_name(label) for sid, label in _SUB_LINK.findall(chunk)}
        tables = list(_SUB_TABLE.finditer(chunk))
        if subs and tables:
            for j, t in enumerate(tables):
                t_end = tables[j + 1].start() if j + 1 < len(tables) else len(chunk)
                codes = _codes(chunk[t.start():t_end])
                name = f"{title}／{subs.get(t.group(1), t.group(1))}"
                if codes:
                    groups.setdefault(name, []).extend(c for c in codes if c not in groups.get(name, []))
        else:
            codes = _codes(chunk)
            if codes:
                name = f"{chain}／{title}"
                groups.setdefault(name, []).extend(c for c in codes if c not in groups.get(name, []))
    return groups


def merge_chains(per_chain: list[tuple[str, dict[str, list[str]]]]) -> dict[str, list[str]]:
    """Combine chain pages; a group name used by an earlier chain gets the later chain's prefix."""
    out: dict[str, list[str]] = {}
    for chain, groups in per_chain:
        for name, codes in groups.items():
            key = name if name not in out or name.startswith(chain + "／") else f"{chain}／{name}"
            bucket = out.setdefault(key, [])
            bucket.extend(c for c in codes if c not in bucket)
    return out


async def fetch_chains(
    client: httpx.AsyncClient,
    progress: Callable[[int, int], None] = lambda done, total: None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    delay: float = REQUEST_DELAY_SECONDS,
) -> dict[str, list[str]]:
    index = parse_chain_index((await get_with_retry(client, BASE_URL)).text)
    if len(index) < MIN_CHAINS:
        raise ParseError(f"TPEx chain index has only {len(index)} chains")
    per_chain = []
    for i, (code, chain) in enumerate(index):
        progress(i, len(index))
        await sleep(delay)
        page = (await get_with_retry(client, f"{BASE_URL}introduce.php?ic={code}")).text
        per_chain.append((chain, parse_chain_page(page, chain)))
    progress(len(index), len(index))
    groups = merge_chains(per_chain)
    if not groups:
        raise ParseError("TPEx chain pages had no member lists")
    return groups
