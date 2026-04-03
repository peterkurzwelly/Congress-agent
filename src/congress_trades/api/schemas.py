"""Pydantic v2 schemas — the shared contracts between all agents.

- Scraper agent outputs RawTradeRecord
- Analyst agent reads RawTradeRecord, writes EnrichmentData
- Fullstack agent uses *Response models for API responses
"""

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------- Enums ----------


class Chamber(str, Enum):
    HOUSE = "house"
    SENATE = "senate"


class TradeType(str, Enum):
    PURCHASE = "Purchase"
    SALE = "Sale"
    SALE_FULL = "Sale (Full)"
    SALE_PARTIAL = "Sale (Partial)"
    EXCHANGE = "Exchange"


class AssetType(str, Enum):
    STOCK = "Stock"
    BOND = "Bond"
    OPTION = "Option"
    FUND = "Fund"
    CRYPTO = "Crypto"
    REAL_ESTATE = "Real Estate"
    OTHER = "Other"


class Owner(str, Enum):
    SELF = "Self"
    SPOUSE = "Spouse"
    JOINT = "Joint"
    DEPENDENT_CHILD = "Dependent Child"


class FilingType(str, Enum):
    PTR = "ptr"
    ANNUAL = "annual"
    AMENDMENT = "amendment"


class AlertType(str, Enum):
    NEW_FILING = "new_filing"
    HIGH_ANOMALY = "high_anomaly"
    LARGE_TRADE = "large_trade"
    LATE_FILING = "late_filing"


# ---------- Scraper Output (contract between Scraper and DB) ----------


class RawTradeRecord(BaseModel):
    """The standard output format for all scrapers. One per transaction line."""

    transaction_date: date
    owner: str
    asset_description: str
    ticker: Optional[str] = None
    asset_type: str = "Stock"
    tx_type: str  # Purchase, Sale, etc.
    amount_range: str  # "$1,001 - $15,000"
    amount_min: int
    amount_max: int
    capital_gains_over_200: Optional[bool] = None
    comment: Optional[str] = None


class ParsedFiling(BaseModel):
    """Claude/pdfplumber output for a complete filing."""

    politician: str
    office: Optional[str] = None
    filing_date: Optional[date] = None
    transactions: list[RawTradeRecord]


# ---------- Enrichment Data (contract between Analyst and DB) ----------


class EnrichmentData(BaseModel):
    """Data produced by the Analyst agent for a single trade."""

    resolved_ticker: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    price_at_trade: Optional[float] = None
    price_current: Optional[float] = None
    return_1d: Optional[float] = None
    return_7d: Optional[float] = None
    return_30d: Optional[float] = None
    return_90d: Optional[float] = None
    committee_relevance_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    anomaly_score: Optional[float] = Field(None, ge=0.0, le=100.0)
    flags: list[str] = Field(default_factory=list)


class LateFilingInfo(BaseModel):
    """STOCK Act late-filing detection result."""

    is_late: bool
    days_late: int = 0
    fine_exposure: int = 0  # $200 per late filing


# ---------- API Response Models (contract between Fullstack and frontend) ----------


class MemberResponse(BaseModel):
    bioguide_id: str
    name: str
    chamber: str
    state: str
    district: Optional[str] = None
    party: str
    committees: Optional[dict] = None
    photo_url: Optional[str] = None

    model_config = {"from_attributes": True}


class MemberSummary(MemberResponse):
    """Member with aggregate trade stats."""

    trade_count: int = 0
    total_buy_volume: int = 0
    total_sell_volume: int = 0
    latest_trade_date: Optional[date] = None
    avg_anomaly_score: Optional[float] = None


class FilingResponse(BaseModel):
    filing_id: str
    member_id: str
    filing_date: date
    disclosure_date: date
    filing_url: str
    filing_type: str
    source: str
    raw_pdf_path: Optional[str] = None
    parsed_at: Optional[datetime] = None
    amendment_of: Optional[str] = None

    model_config = {"from_attributes": True}


class TradeResponse(BaseModel):
    trade_id: int
    filing_id: str
    member_id: str
    asset_description: str
    ticker: Optional[str] = None
    asset_type: str
    trade_type: str
    trade_date: date
    owner: str
    amount_range: str
    amount_min: int
    amount_max: int
    capital_gains_over_200: Optional[bool] = None
    comment: Optional[str] = None

    model_config = {"from_attributes": True}


class TradeWithEnrichment(TradeResponse):
    """Full trade with enrichment data and member info — the main API response."""

    # Member info (denormalized for convenience)
    member_name: Optional[str] = None
    member_party: Optional[str] = None
    member_state: Optional[str] = None
    member_chamber: Optional[str] = None

    # Enrichment
    resolved_ticker: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    price_at_trade: Optional[float] = None
    price_current: Optional[float] = None
    return_1d: Optional[float] = None
    return_7d: Optional[float] = None
    return_30d: Optional[float] = None
    return_90d: Optional[float] = None
    committee_relevance_score: Optional[float] = None
    anomaly_score: Optional[float] = None
    flags: list[str] = Field(default_factory=list)

    # Late filing
    late_filing: Optional[LateFilingInfo] = None

    # Filing context
    filing_date: Optional[date] = None
    disclosure_date: Optional[date] = None


class AnomalyReport(BaseModel):
    """A trade flagged as suspicious."""

    trade: TradeWithEnrichment
    score: float = Field(ge=0.0, le=100.0)
    flags: list[str]
    summary: str


# ---------- Query/Filter Params ----------


class TradeFilterParams(BaseModel):
    """Query parameters for filtering trades."""

    politician: Optional[str] = None
    ticker: Optional[str] = None
    chamber: Optional[Chamber] = None
    party: Optional[str] = None
    state: Optional[str] = None
    trade_type: Optional[str] = None
    asset_type: Optional[str] = None
    min_amount: Optional[int] = None
    max_amount: Optional[int] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    min_anomaly_score: Optional[float] = None
    sort_by: str = "trade_date"
    sort_order: str = "desc"
    offset: int = 0
    limit: int = Field(default=50, le=500)


class PaginatedResponse(BaseModel):
    """Wrapper for paginated list endpoints."""

    data: list
    total: int
    offset: int
    limit: int


# ---------- Stats ----------


class AggregateStats(BaseModel):
    """Dashboard aggregate stats."""

    total_trades: int
    total_buys: int
    total_sells: int
    unique_tickers: int
    unique_politicians: int
    avg_anomaly_score: Optional[float] = None
    late_filings_count: int = 0


class SectorFlow(BaseModel):
    """Net buy/sell volume by sector."""

    sector: str
    net_buy_volume: int  # positive = net buying, negative = net selling
    buy_count: int
    sell_count: int


class TimelinePoint(BaseModel):
    """Trade volume at a point in time."""

    date: date
    buy_count: int
    sell_count: int
    total_volume: int
