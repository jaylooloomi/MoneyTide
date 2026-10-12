"""Issued common shares from the TWSE / TPEx OpenAPI company-profile datasets.

Values are digit-only strings in 股 (shares). TDR rows (TWSE 產業別 "91") carry the underlying
original share count rather than TDR units, so they are skipped → market cap stays None.
"""

from __future__ import annotations

from typing import Any

import httpx

from ..models import ParseError
from .http import get_with_retry

TWSE_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TPEX_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"

TWSE_CODE, TWSE_SHARES, TWSE_INDUSTRY = "公司代號", "已發行普通股數或TDR原股發行股數", "產業別"
TPEX_CODE, TPEX_SHARES = "SecuritiesCompanyCode", "IssueShares"
TDR_INDUSTRY_CODE = "91"
# Live datasets have ~1,090 (TWSE) and ~890 (TPEx) companies; far fewer means a partial response,
# which must not overwrite a good cache for 7 days.
MIN_TWSE, MIN_TPEX = 800, 600


def _parse(records: Any, code_key: str, shares_key: str, skip=lambda r: False) -> dict[str, int]:
    if not isinstance(records, list):
        raise ParseError("shares payload is not a JSON array")
    if records and not (isinstance(records[0], dict) and code_key in records[0] and shares_key in records[0]):
        raise ParseError(f"shares payload missing keys {code_key!r}/{shares_key!r}")
    out: dict[str, int] = {}
    for rec in records:
        if not isinstance(rec, dict) or skip(rec):
            continue
        code = str(rec.get(code_key, "")).strip()
        raw = str(rec.get(shares_key, "")).replace(",", "").strip()
        if code and raw.isdigit() and int(raw) > 0:
            out[code] = int(raw)
    return out


def parse_twse_shares(records: Any) -> dict[str, int]:
    return _parse(
        records, TWSE_CODE, TWSE_SHARES,
        skip=lambda r: str(r.get(TWSE_INDUSTRY, "")).strip() == TDR_INDUSTRY_CODE,
    )


def parse_tpex_shares(records: Any) -> dict[str, int]:
    return _parse(records, TPEX_CODE, TPEX_SHARES)


async def fetch_shares(client: httpx.AsyncClient) -> dict[str, int]:
    twse = parse_twse_shares((await get_with_retry(client, TWSE_URL)).json())
    tpex = parse_tpex_shares((await get_with_retry(client, TPEX_URL)).json())
    if len(twse) < MIN_TWSE or len(tpex) < MIN_TPEX:
        raise ParseError(f"shares data looks partial (TWSE {len(twse)}, TPEx {len(tpex)})")
    return {**twse, **tpex}
