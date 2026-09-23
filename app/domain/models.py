from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Market(str, Enum):
    TW = "TW"
    US = "US"


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class Bar(BaseModel):
    symbol: str
    market: Market
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class NewsItem(BaseModel):
    title: str
    summary: str | None = None
    url: str | None = None
    published_at: datetime | None = None
    source: str | None = None


class AnalystReport(BaseModel):
    role: str
    symbol: str = ""
    market: Market | None = None
    summary: str = ""
    score: float = 0.0
    key_points: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class DebateResult(BaseModel):
    bull_case: str = ""
    bear_case: str = ""
    rounds: list[dict] = Field(default_factory=list)


class RiskReview(BaseModel):
    max_position_pct: float = 0.1
    stop_loss_pct: float = 0.08
    take_profit_pct: float = 0.2
    approved: bool = False
    notes: str = ""


class FinalDecision(BaseModel):
    symbol: str
    market: Market
    action: Literal["BUY", "HOLD", "SELL", "AVOID"] = "HOLD"
    confidence: float = 0.0
    target_position_pct: float = 0.0
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    thesis: str = ""
    reports: list[AnalystReport] = Field(default_factory=list)
    debate: DebateResult | None = None
    risk: RiskReview | None = None
