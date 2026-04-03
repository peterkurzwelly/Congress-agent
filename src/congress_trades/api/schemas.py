"""Pydantic v2 schemas — the shared contracts between all agents.

- Scraper agent outputs RawTradeRecord
- Analyst agent reads RawTradeRecord, writes EnrichmentData
- Fullstack agent uses *Response models for API responses
"""

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

# ---------- Enums ----------


class Chamber(StrEnum):
    HOUSE = "house"
    SENATE = "senate"


class TradeType(StrEnum):
    PURCHASE = "Purchase"
    SALE = "Sale"
    SALE_FULL = "Sale (Full)"
    SALE_PARTIAL = "Sale (Partial)"
    EXCHANGE = "Exchange"


class AssetType(StrEnum):
    STOCK = "Stock"
    BOND = "Bond"
    OPTION = "Option"
    FUND = "Fund"
    CRYPTO = "Crypto"
    REAL_ESTATE = "Real Estate"
    OTHER = "Other"


class Owner(StrEnum):
    SELF = "Self"
    SPOUSE = "Spouse"
    JOINT = "Joint"
    DEPENDENT_CHILD = "Dependent Child"


class FilingType(StrEnum):
    PTR = "ptr"
    ANNUAL = "annual"
    AMENDMENT = "amendment"


class AlertType(StrEnum):
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
    ticker: str | None = None
    asset_type: str = "Stock"
    tx_type: str  # Purchase, Sale, etc.
    amount_range: str  # "$1,001 - $15,000"
    amount_min: int
    amount_max: int
    capital_gains_over_200: bool | None = None
    comment: str | None = None


class ParsedFiling(BaseModel):
    """Claude/pdfplumber output for a complete filing."""

    politician: str
    office: str | None = None
    filing_date: date | None = None
    transactions: list[RawTradeRecord]


# ---------- Enrichment Data (contract between Analyst and DB) ----------


class EnrichmentData(BaseModel):
    """Data produced by the Analyst agent for a single trade."""

    resolved_ticker: str | None = None
    sector: str | None = None
    industry: str | None = None
    price_at_trade: float | None = None
    price_current: float | None = None
    return_1d: float | None = None
    return_7d: float | None = None
    return_30d: float | None = None
    return_90d: float | None = None
    committee_relevance_score: float | None = Field(None, ge=0.0, le=1.0)
    anomaly_score: float | None = Field(None, ge=0.0, le=100.0)
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
    district: str | None = None
    party: str
    committees: dict | None = None
    photo_url: str | None = None

    model_config = {"from_attributes": True}


class MemberSummary(MemberResponse):
    """Member with aggregate trade stats."""

    trade_count: int = 0
    total_buy_volume: int = 0
    total_sell_volume: int = 0
    latest_trade_date: date | None = None
    avg_anomaly_score: float | None = None


class FilingResponse(BaseModel):
    filing_id: str
    member_id: str
    filing_date: date
    disclosure_date: date
    filing_url: str
    filing_type: str
    source: str
    raw_pdf_path: str | None = None
    parsed_at: datetime | None = None
    amendment_of: str | None = None

    model_config = {"from_attributes": True}


class TradeResponse(BaseModel):
    trade_id: int
    filing_id: str
    member_id: str
    asset_description: str
    ticker: str | None = None
    asset_type: str
    trade_type: str
    trade_date: date
    owner: str
    amount_range: str
    amount_min: int
    amount_max: int
    capital_gains_over_200: bool | None = None
    comment: str | None = None

    model_config = {"from_attributes": True}


class TradeWithEnrichment(TradeResponse):
    """Full trade with enrichment data and member info — the main API response."""

    # Member info (denormalized for convenience)
    member_name: str | None = None
    member_party: str | None = None
    member_state: str | None = None
    member_chamber: str | None = None

    # Enrichment
    resolved_ticker: str | None = None
    sector: str | None = None
    industry: str | None = None
    price_at_trade: float | None = None
    price_current: float | None = None
    return_1d: float | None = None
    return_7d: float | None = None
    return_30d: float | None = None
    return_90d: float | None = None
    committee_relevance_score: float | None = None
    anomaly_score: float | None = None
    flags: list[str] = Field(default_factory=list)

    # Late filing
    late_filing: LateFilingInfo | None = None

    # Filing context
    filing_date: date | None = None
    disclosure_date: date | None = None


class AnomalyReport(BaseModel):
    """A trade flagged as suspicious."""

    trade: TradeWithEnrichment
    score: float = Field(ge=0.0, le=100.0)
    flags: list[str]
    summary: str


# ---------- Query/Filter Params ----------


class TradeFilterParams(BaseModel):
    """Query parameters for filtering trades."""

    politician: str | None = None
    ticker: str | None = None
    chamber: Chamber | None = None
    party: str | None = None
    state: str | None = None
    trade_type: str | None = None
    asset_type: str | None = None
    min_amount: int | None = None
    max_amount: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    min_anomaly_score: float | None = None
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
    avg_anomaly_score: float | None = None
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


class PartyComparison(BaseModel):
    """Trading activity aggregated by political party."""

    party: str
    total_trades: int
    total_buy_volume: int
    total_sell_volume: int
    avg_anomaly_score: float | None = None
    unique_tickers: int


class TopTicker(BaseModel):
    """Most traded ticker with aggregate stats."""

    ticker: str
    trade_count: int
    buy_count: int
    sell_count: int
    unique_members: int
    avg_anomaly_score: float | None = None


class DisclosureDelayBucket(BaseModel):
    """Histogram bucket for disclosure delay distribution."""

    delay_bucket: str
    count: int


class MemberPerformance(BaseModel):
    """Member ranked by anomaly score."""

    name: str
    bioguide_id: str
    party: str
    avg_anomaly_score: float | None = None
    trade_count: int
    flagged_trades_count: int
