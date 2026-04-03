"""Seed the database with sample data for testing and development."""

import asyncio
from datetime import date, datetime

from congress_trades.db.models import Alert, EnrichedTrade, Filing, Member, Trade
from congress_trades.db.session import async_session, init_db


MEMBERS = [
    Member(
        bioguide_id="P000197",
        name="Nancy Pelosi",
        chamber="house",
        state="CA",
        district="11",
        party="Democrat",
        committees={"current": ["Select Committee on the Climate Crisis"], "former": ["Appropriations", "Intelligence"]},
    ),
    Member(
        bioguide_id="T000478",
        name="Tommy Tuberville",
        chamber="senate",
        state="AL",
        district=None,
        party="Republican",
        committees={"current": ["Armed Services", "Agriculture", "Veterans' Affairs"]},
    ),
    Member(
        bioguide_id="C001035",
        name="Susan Collins",
        chamber="senate",
        state="ME",
        district=None,
        party="Republican",
        committees={"current": ["Appropriations", "Health, Education, Labor and Pensions"]},
    ),
    Member(
        bioguide_id="O000174",
        name="Alexandria Ocasio-Cortez",
        chamber="house",
        state="NY",
        district="14",
        party="Democrat",
        committees={"current": ["Financial Services", "Oversight and Accountability"]},
    ),
    Member(
        bioguide_id="G000596",
        name="Dan Goldman",
        chamber="house",
        state="NY",
        district="10",
        party="Democrat",
        committees={"current": ["Homeland Security", "Oversight and Accountability"]},
    ),
]

FILINGS = [
    Filing(
        filing_id="house-pelosi-2026-001",
        member_id="P000197",
        filing_date=date(2026, 1, 15),
        disclosure_date=date(2026, 2, 28),
        filing_url="https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2026/20012345.pdf",
        filing_type="ptr",
        source="house",
    ),
    Filing(
        filing_id="senate-tuberville-2026-001",
        member_id="T000478",
        filing_date=date(2026, 2, 1),
        disclosure_date=date(2026, 3, 15),
        filing_url="https://efdsearch.senate.gov/search/view/ptr/abc123/",
        filing_type="ptr",
        source="senate",
    ),
    Filing(
        filing_id="senate-collins-2026-001",
        member_id="C001035",
        filing_date=date(2026, 1, 20),
        disclosure_date=date(2026, 3, 25),
        filing_url="https://efdsearch.senate.gov/search/view/ptr/def456/",
        filing_type="ptr",
        source="senate",
    ),
    Filing(
        filing_id="house-goldman-2026-001",
        member_id="G000596",
        filing_date=date(2026, 2, 10),
        disclosure_date=date(2026, 2, 20),
        filing_url="https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2026/20067890.pdf",
        filing_type="ptr",
        source="house",
    ),
]

TRADES = [
    # Pelosi trades
    Trade(
        filing_id="house-pelosi-2026-001",
        member_id="P000197",
        asset_description="NVIDIA Corporation",
        ticker="NVDA",
        asset_type="Stock",
        trade_type="Purchase",
        trade_date=date(2026, 1, 10),
        owner="Spouse",
        amount_range="$1,000,001 - $5,000,000",
        amount_min=1_000_001,
        amount_max=5_000_000,
    ),
    Trade(
        filing_id="house-pelosi-2026-001",
        member_id="P000197",
        asset_description="Apple Inc.",
        ticker="AAPL",
        asset_type="Stock",
        trade_type="Sale (Partial)",
        trade_date=date(2026, 1, 12),
        owner="Spouse",
        amount_range="$250,001 - $500,000",
        amount_min=250_001,
        amount_max=500_000,
    ),
    Trade(
        filing_id="house-pelosi-2026-001",
        member_id="P000197",
        asset_description="Alphabet Inc. Class A",
        ticker="GOOGL",
        asset_type="Stock",
        trade_type="Purchase",
        trade_date=date(2026, 1, 14),
        owner="Spouse",
        amount_range="$500,001 - $1,000,000",
        amount_min=500_001,
        amount_max=1_000_000,
    ),
    # Tuberville trades — defense stocks while on Armed Services
    Trade(
        filing_id="senate-tuberville-2026-001",
        member_id="T000478",
        asset_description="Lockheed Martin Corporation",
        ticker="LMT",
        asset_type="Stock",
        trade_type="Purchase",
        trade_date=date(2026, 1, 25),
        owner="Self",
        amount_range="$15,001 - $50,000",
        amount_min=15_001,
        amount_max=50_000,
    ),
    Trade(
        filing_id="senate-tuberville-2026-001",
        member_id="T000478",
        asset_description="Raytheon Technologies Corp",
        ticker="RTX",
        asset_type="Stock",
        trade_type="Purchase",
        trade_date=date(2026, 1, 28),
        owner="Self",
        amount_range="$50,001 - $100,000",
        amount_min=50_001,
        amount_max=100_000,
    ),
    Trade(
        filing_id="senate-tuberville-2026-001",
        member_id="T000478",
        asset_description="General Dynamics Corporation",
        ticker="GD",
        asset_type="Stock",
        trade_type="Purchase",
        trade_date=date(2026, 2, 1),
        owner="Self",
        amount_range="$1,001 - $15,000",
        amount_min=1_001,
        amount_max=15_000,
    ),
    # Collins — pharma while on HELP committee
    Trade(
        filing_id="senate-collins-2026-001",
        member_id="C001035",
        asset_description="Pfizer Inc.",
        ticker="PFE",
        asset_type="Stock",
        trade_type="Purchase",
        trade_date=date(2026, 1, 18),
        owner="Self",
        amount_range="$15,001 - $50,000",
        amount_min=15_001,
        amount_max=50_000,
    ),
    Trade(
        filing_id="senate-collins-2026-001",
        member_id="C001035",
        asset_description="Johnson & Johnson",
        ticker="JNJ",
        asset_type="Stock",
        trade_type="Sale",
        trade_date=date(2026, 1, 22),
        owner="Joint",
        amount_range="$100,001 - $250,000",
        amount_min=100_001,
        amount_max=250_000,
    ),
    # Goldman — financial stocks while on Financial Services (via Oversight)
    Trade(
        filing_id="house-goldman-2026-001",
        member_id="G000596",
        asset_description="JPMorgan Chase & Co.",
        ticker="JPM",
        asset_type="Stock",
        trade_type="Purchase",
        trade_date=date(2026, 2, 5),
        owner="Self",
        amount_range="$100,001 - $250,000",
        amount_min=100_001,
        amount_max=250_000,
    ),
    Trade(
        filing_id="house-goldman-2026-001",
        member_id="G000596",
        asset_description="Microsoft Corporation",
        ticker="MSFT",
        asset_type="Stock",
        trade_type="Sale (Full)",
        trade_date=date(2026, 2, 8),
        owner="Self",
        amount_range="$50,001 - $100,000",
        amount_min=50_001,
        amount_max=100_000,
    ),
]


async def seed() -> None:
    await init_db()

    async with async_session() as session:
        # Add members
        for member in MEMBERS:
            session.add(member)
        await session.flush()
        print(f"Added {len(MEMBERS)} members")

        # Add filings
        for filing in FILINGS:
            session.add(filing)
        await session.flush()
        print(f"Added {len(FILINGS)} filings")

        # Add trades
        for trade in TRADES:
            session.add(trade)
        await session.flush()
        print(f"Added {len(TRADES)} trades")

        # Add enrichment data for some trades
        enrichments = [
            EnrichedTrade(
                trade_id=1,  # Pelosi NVDA
                resolved_ticker="NVDA",
                sector="Technology",
                industry="Semiconductors",
                price_at_trade=142.50,
                price_current=175.30,
                return_1d=0.012,
                return_7d=0.034,
                return_30d=0.089,
                return_90d=0.23,
                committee_relevance_score=0.15,
                anomaly_score=73.0,
                flags=["Large trade (>$1M)", "Spouse trade", "Filed 44 days after trade"],
                scored_at=datetime(2026, 3, 1, 12, 0, 0),
            ),
            EnrichedTrade(
                trade_id=4,  # Tuberville LMT
                resolved_ticker="LMT",
                sector="Aerospace & Defense",
                industry="Defense",
                price_at_trade=485.00,
                price_current=512.40,
                return_1d=-0.003,
                return_7d=0.015,
                return_30d=0.056,
                return_90d=0.082,
                committee_relevance_score=0.95,
                anomaly_score=88.0,
                flags=[
                    "Armed Services Committee member bought defense stock",
                    "High committee relevance (0.95)",
                    "Filed 43 days after trade",
                ],
                scored_at=datetime(2026, 3, 1, 12, 0, 0),
            ),
            EnrichedTrade(
                trade_id=5,  # Tuberville RTX
                resolved_ticker="RTX",
                sector="Aerospace & Defense",
                industry="Defense",
                price_at_trade=98.20,
                price_current=105.70,
                return_1d=0.008,
                return_7d=0.022,
                return_30d=0.076,
                return_90d=0.11,
                committee_relevance_score=0.95,
                anomaly_score=82.0,
                flags=[
                    "Armed Services Committee member bought defense stock",
                    "Multiple defense purchases in same period",
                ],
                scored_at=datetime(2026, 3, 1, 12, 0, 0),
            ),
            EnrichedTrade(
                trade_id=7,  # Collins PFE
                resolved_ticker="PFE",
                sector="Healthcare",
                industry="Pharmaceuticals",
                price_at_trade=28.30,
                price_current=31.50,
                return_1d=0.005,
                return_7d=0.018,
                return_30d=0.045,
                return_90d=0.113,
                committee_relevance_score=0.80,
                anomaly_score=65.0,
                flags=[
                    "HELP Committee member bought pharma stock",
                    "Filed 64 days after trade — STOCK Act violation",
                ],
                scored_at=datetime(2026, 3, 1, 12, 0, 0),
            ),
            EnrichedTrade(
                trade_id=9,  # Goldman JPM
                resolved_ticker="JPM",
                sector="Financial Services",
                industry="Banking",
                price_at_trade=198.50,
                price_current=210.30,
                return_1d=0.002,
                return_7d=0.011,
                return_30d=0.059,
                return_90d=0.087,
                committee_relevance_score=0.40,
                anomaly_score=52.0,
                flags=["Large trade (>$100K)", "Financial sector trade by Oversight member"],
                scored_at=datetime(2026, 3, 1, 12, 0, 0),
            ),
        ]
        for enrichment in enrichments:
            session.add(enrichment)
        await session.flush()
        print(f"Added {len(enrichments)} enrichment records")

        await session.commit()
        print("Database seeded successfully!")


if __name__ == "__main__":
    asyncio.run(seed())
