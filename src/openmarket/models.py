"""Shared data contracts. JSON field names are the dataclass field names (snake_case)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

Market = Literal["上市", "上櫃", "未知"]
# loading = no fetch attempt finished yet; error = attempts failed and none ever succeeded
Status = Literal["loading", "ok", "stale", "error"]
# stock = 普通股/創新板/KY; etf = ETF + ETN; other = 特別股/TDR/REITs/其他（不放進熱力圖）
Kind = Literal["stock", "etf", "other"]

OTHER_INDUSTRY = "其他"
ETF_INDUSTRY = "ETF"


class ParseError(Exception):
    """Raised when an upstream page/JSON no longer matches the expected format."""


@dataclass(frozen=True, slots=True)
class Quote:
    """One row of the HiStock rank table. Missing/unparseable numbers are None."""

    code: str
    name: str
    price: float | None
    change: float | None
    change_pct: float | None
    week_pct: float | None
    amplitude_pct: float | None
    open: float | None
    high: float | None
    low: float | None
    prev_close: float | None
    volume_lots: float | None
    turnover_100m: float | None


@dataclass(frozen=True, slots=True)
class StockInfo:
    """Static classification from the TWSE ISIN listing."""

    code: str
    name: str
    industry: str
    market: Market
    kind: Kind


@dataclass(frozen=True, slots=True)
class Stock:
    code: str
    name: str
    price: float | None
    change: float | None
    change_pct: float | None
    week_pct: float | None
    amplitude_pct: float | None
    open: float | None
    high: float | None
    low: float | None
    prev_close: float | None
    volume_lots: float | None
    turnover_100m: float | None
    industry: str
    market: Market
    kind: Kind
    market_cap: float | None  # 元


@dataclass(slots=True)
class Snapshot:
    version: int = 0
    as_of: str | None = None
    status: Status = "loading"
    message: str = ""
    market_open: bool = False
    stocks: list[Stock] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
