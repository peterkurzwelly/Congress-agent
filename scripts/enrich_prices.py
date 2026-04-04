"""Enrich resolved tickers with yfinance price data and re-score anomalies.

Queries EnrichedTrade rows that have a resolved_ticker but no price_at_trade,
fetches historical prices, updates returns, and re-runs anomaly scoring.

Usage:
    uv run python scripts/enrich_prices.py
    uv run python scripts/enrich_prices.py --limit 50 -v
    uv run python scripts/enrich_prices.py --ticker AAPL
    uv run python scripts/enrich_prices.py --dry-run
"""

import argparse
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from congress_trades.db.models import EnrichedTrade, Filing, Member, Trade
from congress_trades.db.session import async_session, init_db
from congress_trades.enrichment.price_fetcher import fetch_trade_returns
from congress_trades.scoring.anomaly_scorer import (
    _score_committee_overlap,
    _score_concurrent_trades,
    _score_disclosure_delay,
    _score_historical_pattern,
    _score_price_movement,
    _score_trade_size,
    _score_trade_timing,
    check_late_filing,
)

logger = logging.getLogger(__name__)

# Batch settings
BATCH_SIZE = 20
BATCH_DELAY_SECONDS = 2.0


async def _load_enriched_rows(
    session: AsyncSession,
    limit: int | None,
    ticker_filter: str | None,
) -> list[EnrichedTrade]:
    """Query EnrichedTrade rows that have a ticker but no price data."""
    stmt = (
        select(EnrichedTrade)
        .where(EnrichedTrade.resolved_ticker.isnot(None))
        .where(EnrichedTrade.price_at_trade.is_(None))
    )

    if ticker_filter:
        stmt = stmt.where(EnrichedTrade.resolved_ticker == ticker_filter.upper())

    if limit:
        stmt = stmt.limit(limit)

    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _rescore_anomaly(
    enriched: EnrichedTrade,
    trade: Trade,
    member: Member,
    filing: Filing,
    price_data: dict,
    session: AsyncSession,
) -> tuple[float, list[str]]:
    """Re-compute anomaly score and flags using updated price data.

    Returns (total_score, flags).
    """
    from congress_trades.config import settings
    from congress_trades.enrichment.committee_mapper import get_committee_relevance

    flags: list[str] = []

    sector = price_data.get("sector") or enriched.sector
    ticker = enriched.resolved_ticker or ""

    # Committee relevance
    committees = member.committees or {}
    committee_relevance = get_committee_relevance(committees, ticker, sector)
    if committee_relevance > 0.5:
        flags.append("committee_overlap")

    # Late filing
    late_info = check_late_filing(trade.trade_date, filing.disclosure_date)
    if late_info.is_late:
        flags.append("late_filing")

    # Large trade
    midpoint = (trade.amount_min + trade.amount_max) / 2
    if midpoint >= settings.LARGE_TRADE_THRESHOLD:
        flags.append("large_trade")

    # Individual scoring factors
    s_committee = _score_committee_overlap(committee_relevance)
    s_delay = _score_disclosure_delay(trade.trade_date, filing.disclosure_date)
    s_size = _score_trade_size(trade.amount_min, trade.amount_max)
    s_price = _score_price_movement(price_data)
    s_concurrent = await _score_concurrent_trades(
        ticker, trade.trade_date, trade.member_id, session
    )
    s_timing = await _score_trade_timing(
        member_id=trade.member_id,
        trade_date=trade.trade_date,
        ticker=ticker,
        sector=sector,
    )
    if s_timing >= 5.0:
        flags.append("bill_timing")

    s_historical = await _score_historical_pattern(
        trade.member_id, ticker, trade.amount_min, session
    )

    total_score = (
        s_committee + s_delay + s_size + s_price + s_concurrent + s_timing + s_historical
    )
    total_score = round(min(max(total_score, 0.0), 100.0), 1)

    if total_score >= settings.ANOMALY_ALERT_THRESHOLD:
        flags.append("high_anomaly")

    return total_score, flags


async def _enrich_single(
    enriched: EnrichedTrade,
    session: AsyncSession,
    dry_run: bool,
) -> bool:
    """Fetch prices and re-score a single EnrichedTrade. Returns True on success."""
    ticker = enriched.resolved_ticker
    if not ticker:
        return False

    # Load the parent trade and its member/filing
    stmt_trade = select(Trade).where(Trade.trade_id == enriched.trade_id)
    result_trade = await session.execute(stmt_trade)
    trade = result_trade.scalar_one_or_none()
    if trade is None:
        logger.warning("Trade %d not found for enriched row, skipping", enriched.trade_id)
        return False

    stmt_member = select(Member).where(Member.bioguide_id == trade.member_id)
    result_member = await session.execute(stmt_member)
    member = result_member.scalar_one_or_none()
    if member is None:
        logger.warning("Member %s not found, skipping trade %d", trade.member_id, trade.trade_id)
        return False

    stmt_filing = select(Filing).where(Filing.filing_id == trade.filing_id)
    result_filing = await session.execute(stmt_filing)
    filing = result_filing.scalar_one_or_none()
    if filing is None:
        logger.warning("Filing %s not found, skipping trade %d", trade.filing_id, trade.trade_id)
        return False

    # Fetch price data
    price_data = await fetch_trade_returns(ticker, trade.trade_date)

    price_at_trade = price_data.get("price_at_trade")
    if price_at_trade is None:
        logger.debug("No price data available for %s on %s", ticker, trade.trade_date)
        # Still continue so we attempt the re-score with what we have

    if dry_run:
        logger.info(
            "[DRY RUN] Would update trade %d (%s): price_at_trade=%s return_7d=%s",
            enriched.trade_id,
            ticker,
            price_at_trade,
            price_data.get("return_7d"),
        )
        return True

    # Update price fields
    enriched.price_at_trade = price_at_trade
    enriched.price_current = price_data.get("price_current")
    enriched.return_1d = price_data.get("return_1d")
    enriched.return_7d = price_data.get("return_7d")
    enriched.return_30d = price_data.get("return_30d")
    enriched.return_90d = price_data.get("return_90d")

    # Update sector/industry if previously missing
    if price_data.get("sector") and not enriched.sector:
        enriched.sector = price_data["sector"]
    if price_data.get("industry") and not enriched.industry:
        enriched.industry = price_data["industry"]

    # Re-run anomaly scoring
    anomaly_score, flags = await _rescore_anomaly(
        enriched, trade, member, filing, price_data, session
    )
    enriched.anomaly_score = anomaly_score
    enriched.flags = flags
    enriched.scored_at = datetime.utcnow()

    logger.debug(
        "Trade %d (%s): price=%.2f return_7d=%s score=%.1f flags=%s",
        enriched.trade_id,
        ticker,
        price_at_trade or 0.0,
        price_data.get("return_7d"),
        anomaly_score,
        flags,
    )
    return True


async def run_enrichment(
    limit: int | None,
    ticker_filter: str | None,
    dry_run: bool,
) -> None:
    """Main async entrypoint: load rows, process in batches, persist."""
    await init_db()

    async with async_session() as session:
        rows = await _load_enriched_rows(session, limit, ticker_filter)

    total = len(rows)
    if total == 0:
        logger.info("No EnrichedTrade rows need price enrichment — nothing to do.")
        return

    logger.info(
        "Found %d EnrichedTrade rows with resolved ticker but no price data%s.",
        total,
        f" (filtered to ticker={ticker_filter})" if ticker_filter else "",
    )

    enriched_count = 0
    failed_count = 0

    for batch_start in range(0, total, BATCH_SIZE):
        batch = rows[batch_start : batch_start + BATCH_SIZE]
        batch_tickers = [r.resolved_ticker for r in batch if r.resolved_ticker]

        async with async_session() as session:
            for enriched in batch:
                # Re-fetch the row within this session to allow mutations
                stmt = select(EnrichedTrade).where(
                    EnrichedTrade.trade_id == enriched.trade_id
                )
                result = await session.execute(stmt)
                live_row = result.scalar_one_or_none()
                if live_row is None:
                    continue

                try:
                    success = await _enrich_single(live_row, session, dry_run)
                    if success:
                        enriched_count += 1
                    else:
                        failed_count += 1
                except Exception as exc:
                    logger.error(
                        "Failed to enrich trade %d (%s): %s",
                        enriched.trade_id,
                        enriched.resolved_ticker,
                        exc,
                    )
                    failed_count += 1

            if not dry_run:
                try:
                    await session.commit()
                except Exception as exc:
                    logger.error("Commit failed for batch: %s", exc)
                    await session.rollback()

        # Progress report
        done = min(batch_start + BATCH_SIZE, total)
        ticker_sample = ", ".join(batch_tickers[:5])
        if len(batch_tickers) > 5:
            ticker_sample += f"... (+{len(batch_tickers) - 5} more)"
        print(f"Enriched {done}/{total} trades ({ticker_sample})")

        # Rate-limit pause between batches (skip after last batch)
        if batch_start + BATCH_SIZE < total:
            logger.debug("Sleeping %.1fs between batches", BATCH_DELAY_SECONDS)
            await asyncio.sleep(BATCH_DELAY_SECONDS)

    suffix = " [DRY RUN — no writes performed]" if dry_run else ""
    logger.info(
        "Price enrichment complete: %d succeeded, %d failed out of %d total.%s",
        enriched_count,
        failed_count,
        total,
        suffix,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich Congressional trades with yfinance price data."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Only enrich N trades (useful for testing).",
    )
    parser.add_argument(
        "--ticker",
        type=str,
        default=None,
        metavar="SYMBOL",
        help="Only enrich trades for a specific ticker symbol.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be enriched without writing to the database.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug logging.",
    )

    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    asyncio.run(
        run_enrichment(
            limit=args.limit,
            ticker_filter=args.ticker,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
