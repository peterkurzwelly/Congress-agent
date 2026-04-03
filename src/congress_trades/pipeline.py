"""Full pipeline: scrape → parse → store → enrich → score → alert.

Usage:
    uv run python -m congress_trades.pipeline              # scrape latest + enrich
    uv run python -m congress_trades.pipeline --house-only # House only
    uv run python -m congress_trades.pipeline --senate-only
    uv run python -m congress_trades.pipeline --enrich-only # just re-enrich existing trades
"""

import argparse
import asyncio
import logging
from datetime import date, timedelta

from sqlalchemy import select

from congress_trades.api.schemas import RawTradeRecord
from congress_trades.db.models import Filing, Member, Trade
from congress_trades.db.session import async_session, init_db
from congress_trades.scoring.anomaly_scorer import enrich_and_score
from congress_trades.scrapers.house_clerk import scrape_house_disclosures
from congress_trades.scrapers.pdf_parser import parse_filing
from congress_trades.scrapers.senate_efd import scrape_senate_full

logger = logging.getLogger(__name__)


async def _get_or_create_member(
    session, name: str, office: str, source: str
) -> Member:
    """Find or create a placeholder Member record from scraper metadata."""
    # Try to find by name
    stmt = select(Member).where(Member.name == name)
    result = await session.execute(stmt)
    member = result.scalar_one_or_none()
    if member:
        return member

    # Create a placeholder — enrichment will fill in later
    state = ""
    district = None
    chamber = source
    if office:
        state = office[:2]
        district = office[2:] if len(office) > 2 else None

    # Use a hash-based bioguide_id placeholder until we resolve the real one
    import hashlib
    bio_id = "X" + hashlib.sha256(name.encode()).hexdigest()[:6].upper()

    member = Member(
        bioguide_id=bio_id,
        name=name,
        chamber=chamber,
        state=state,
        district=district,
        party="Unknown",
        committees={},
    )
    session.add(member)
    await session.flush()
    logger.info("Created placeholder member: %s (%s)", name, bio_id)
    return member


async def _store_filing(session, filing_meta: dict, member: Member) -> Filing | None:
    """Store a filing record, skipping if it already exists."""
    filing_id = filing_meta["filing_id"]

    stmt = select(Filing).where(Filing.filing_id == filing_id)
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing:
        logger.debug("Filing %s already exists, skipping", filing_id)
        return None

    filing = Filing(
        filing_id=filing_id,
        member_id=member.bioguide_id,
        filing_date=filing_meta.get("filing_date", date.today()),
        disclosure_date=filing_meta.get("filing_date", date.today()),
        filing_url=filing_meta.get("pdf_url") or filing_meta.get("filing_url", ""),
        filing_type=_classify_filing_type(filing_meta.get("filing_type", "")),
        source=filing_meta.get("source", "house"),
        raw_pdf_path=filing_meta.get("pdf_path"),
    )
    session.add(filing)
    await session.flush()
    return filing


def _classify_filing_type(text: str) -> str:
    """Normalize filing type text to ptr/annual/amendment."""
    lower = text.lower()
    if "amendment" in lower:
        return "amendment"
    if "annual" in lower:
        return "annual"
    return "ptr"


async def _store_trades(
    session, records: list[RawTradeRecord], filing: Filing, member: Member
) -> list[Trade]:
    """Store parsed trade records in the database."""
    trades = []
    for record in records:
        trade = Trade(
            filing_id=filing.filing_id,
            member_id=member.bioguide_id,
            asset_description=record.asset_description,
            ticker=record.ticker,
            asset_type=record.asset_type,
            trade_type=record.tx_type,
            trade_date=record.transaction_date,
            owner=record.owner,
            amount_range=record.amount_range,
            amount_min=record.amount_min,
            amount_max=record.amount_max,
            capital_gains_over_200=record.capital_gains_over_200,
            comment=record.comment,
        )
        session.add(trade)
        trades.append(trade)

    await session.flush()
    return trades


async def scrape_and_store_house(year: int | None = None) -> list[int]:
    """Scrape House filings, parse PDFs, store in DB. Returns new trade IDs."""
    if year is None:
        year = date.today().year

    logger.info("=== Scraping House filings for %d ===", year)
    filings = await scrape_house_disclosures(filing_year=year, download_pdfs=True)
    logger.info("Found %d House filings", len(filings))

    new_trade_ids: list[int] = []

    async with async_session() as session:
        for filing_meta in filings:
            try:
                member = await _get_or_create_member(
                    session,
                    filing_meta["name"],
                    filing_meta.get("office", ""),
                    "house",
                )

                filing = await _store_filing(session, filing_meta, member)
                if filing is None:
                    continue  # already processed

                # Parse the PDF if we downloaded it
                pdf_path = filing_meta.get("pdf_path")
                if pdf_path:
                    records = await parse_filing(pdf_path)
                    trades = await _store_trades(session, records, filing, member)
                    new_trade_ids.extend(t.trade_id for t in trades)
                    logger.info(
                        "Stored %d trades from %s (%s)",
                        len(trades),
                        filing_meta["name"],
                        filing.filing_id,
                    )

                await session.commit()

            except Exception as exc:
                logger.error("Failed to process filing %s: %s", filing_meta.get("name"), exc)
                await session.rollback()

    return new_trade_ids


async def scrape_and_store_senate(days_back: int = 30) -> list[int]:
    """Scrape Senate filings, parse PTR tables, store in DB. Returns new trade IDs."""
    date_to = date.today()
    date_from = date_to - timedelta(days=days_back)

    logger.info("=== Scraping Senate filings from %s to %s ===", date_from, date_to)
    filings = await scrape_senate_full(date_from=date_from, date_to=date_to)
    logger.info("Found %d Senate filings", len(filings))

    new_trade_ids: list[int] = []

    async with async_session() as session:
        for filing_meta in filings:
            try:
                member = await _get_or_create_member(
                    session,
                    filing_meta["name"],
                    filing_meta.get("office", ""),
                    "senate",
                )

                filing = await _store_filing(session, filing_meta, member)
                if filing is None:
                    continue

                # Senate filings have transactions already parsed from HTML
                transactions = filing_meta.get("transactions", [])
                records = [
                    RawTradeRecord(**t) if isinstance(t, dict) else t
                    for t in transactions
                ]

                if records:
                    trades = await _store_trades(session, records, filing, member)
                    new_trade_ids.extend(t.trade_id for t in trades)
                    logger.info(
                        "Stored %d trades from %s (%s)",
                        len(trades),
                        filing_meta["name"],
                        filing.filing_id,
                    )

                await session.commit()

            except Exception as exc:
                logger.error("Failed to process Senate filing %s: %s", filing_meta.get("name"), exc)
                await session.rollback()

    return new_trade_ids


async def enrich_trades(trade_ids: list[int]) -> None:
    """Run enrichment and scoring on a list of trade IDs."""
    if not trade_ids:
        logger.info("No trades to enrich")
        return

    logger.info("=== Enriching %d trades ===", len(trade_ids))
    async with async_session() as session:
        for trade_id in trade_ids:
            try:
                enriched = await enrich_and_score(trade_id, session)
                await session.commit()
                logger.info(
                    "Trade %d: ticker=%s score=%.1f",
                    trade_id,
                    enriched.resolved_ticker,
                    enriched.anomaly_score or 0,
                )
            except Exception as exc:
                logger.error("Failed to enrich trade %d: %s", trade_id, exc)
                await session.rollback()


async def enrich_all_unenriched() -> None:
    """Find and enrich all trades missing enrichment data."""
    from congress_trades.db.models import EnrichedTrade

    async with async_session() as session:
        stmt = (
            select(Trade.trade_id)
            .outerjoin(EnrichedTrade)
            .where(EnrichedTrade.trade_id.is_(None))
        )
        result = await session.execute(stmt)
        trade_ids = [row[0] for row in result.all()]

    logger.info("Found %d unenriched trades", len(trade_ids))
    await enrich_trades(trade_ids)


async def run_pipeline(
    house: bool = True,
    senate: bool = True,
    enrich: bool = True,
) -> None:
    """Run the full pipeline."""
    await init_db()

    new_trade_ids: list[int] = []

    if house:
        house_ids = await scrape_and_store_house()
        new_trade_ids.extend(house_ids)

    if senate:
        senate_ids = await scrape_and_store_senate()
        new_trade_ids.extend(senate_ids)

    if enrich and new_trade_ids:
        await enrich_trades(new_trade_ids)

    logger.info("Pipeline complete: %d new trades processed", len(new_trade_ids))


def main() -> None:
    parser = argparse.ArgumentParser(description="Congress Trades Pipeline")
    parser.add_argument("--house-only", action="store_true", help="Scrape House only")
    parser.add_argument("--senate-only", action="store_true", help="Scrape Senate only")
    parser.add_argument("--enrich-only", action="store_true", help="Only enrich existing trades")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    if args.enrich_only:
        asyncio.run(enrich_all_unenriched())
    else:
        house = not args.senate_only
        senate = not args.house_only
        asyncio.run(run_pipeline(house=house, senate=senate))


if __name__ == "__main__":
    main()
