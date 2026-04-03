"""Shared test fixtures for the Congress Trades Pipeline."""

from datetime import date, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from congress_trades.db.models import (
    Alert,
    Base,
    EnrichedTrade,
    Filing,
    Member,
    Trade,
)


@pytest.fixture
async def db_engine():
    """Create an in-memory SQLite engine for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine) -> AsyncSession:
    """Yield a database session for testing, rolled back after each test."""
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def sample_member() -> Member:
    """A sample Congress member for testing."""
    return Member(
        bioguide_id="P000197",
        name="Nancy Pelosi",
        chamber="house",
        state="CA",
        district="11",
        party="Democrat",
        committees={
            "current": ["Select Committee on the Climate Crisis"],
            "former": ["Appropriations", "Intelligence"],
        },
        photo_url=None,
    )


@pytest.fixture
def sample_filing(sample_member: Member) -> Filing:
    """A sample filing for testing."""
    return Filing(
        filing_id="20012345",
        member_id=sample_member.bioguide_id,
        filing_date=date(2026, 1, 15),
        disclosure_date=date(2026, 2, 28),
        filing_url="https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2026/20012345.pdf",
        filing_type="ptr",
        source="house",
        raw_pdf_path=None,
        parsed_at=None,
    )


@pytest.fixture
def sample_trade(sample_filing: Filing, sample_member: Member) -> Trade:
    """A sample trade for testing."""
    return Trade(
        filing_id=sample_filing.filing_id,
        member_id=sample_member.bioguide_id,
        asset_description="NVIDIA Corporation (NVDA)",
        ticker="NVDA",
        asset_type="Stock",
        trade_type="Purchase",
        trade_date=date(2026, 1, 10),
        owner="Spouse",
        amount_range="$1,000,001 - $5,000,000",
        amount_min=1_000_001,
        amount_max=5_000_000,
        capital_gains_over_200=None,
        comment=None,
    )


@pytest.fixture
def sample_enriched_trade() -> dict:
    """Sample enrichment data as a dict (before being written to EnrichedTrade)."""
    return {
        "resolved_ticker": "NVDA",
        "sector": "Technology",
        "industry": "Semiconductors",
        "price_at_trade": 142.50,
        "price_current": 175.30,
        "return_1d": 0.012,
        "return_7d": 0.034,
        "return_30d": 0.089,
        "return_90d": 0.23,
        "committee_relevance_score": 0.15,
        "anomaly_score": 73.0,
        "flags": [
            "Large trade (>$1M)",
            "Spouse trade",
            "Filed 44 days after trade (near STOCK Act limit)",
        ],
        "scored_at": datetime(2026, 3, 1, 12, 0, 0),
    }


@pytest.fixture
async def populated_db(
    db_session: AsyncSession,
    sample_member: Member,
    sample_filing: Filing,
    sample_trade: Trade,
    sample_enriched_trade: dict,
) -> AsyncSession:
    """A database session pre-populated with sample data."""
    db_session.add(sample_member)
    await db_session.flush()

    db_session.add(sample_filing)
    await db_session.flush()

    db_session.add(sample_trade)
    await db_session.flush()

    enriched = EnrichedTrade(trade_id=sample_trade.trade_id, **sample_enriched_trade)
    db_session.add(enriched)
    await db_session.flush()

    alert = Alert(
        trade_id=sample_trade.trade_id,
        alert_type="high_anomaly",
        channel="telegram",
        message="High anomaly score: 73",
        sent_at=datetime(2026, 3, 1, 12, 5, 0),
    )
    db_session.add(alert)
    await db_session.commit()

    return db_session
