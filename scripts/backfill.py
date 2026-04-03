"""Backfill historical data from House Clerk and Senate EFD.

Downloads and parses House PTR filings for specified years.
Senate filings can be backfilled by extending the date range.

Usage:
    uv run python scripts/backfill.py                     # 2024+2025 House
    uv run python scripts/backfill.py --years 2023 2024 2025
    uv run python scripts/backfill.py --senate --days 90  # Senate last 90 days
    uv run python scripts/backfill.py --limit 50          # limit per year
"""

import argparse
import asyncio
import logging
from datetime import date, timedelta

from congress_trades.db.session import init_db
from congress_trades.pipeline import (
    scrape_and_store_house,
    scrape_and_store_senate,
    enrich_trades,
)

logger = logging.getLogger(__name__)


async def backfill_house(years: list[int], limit: int | None = None) -> list[int]:
    """Scrape House filings for multiple years."""
    all_trade_ids: list[int] = []

    for year in years:
        logger.info("=== Backfilling House filings for %d ===", year)
        trade_ids = await scrape_and_store_house(year=year)

        if limit and len(trade_ids) > limit:
            trade_ids = trade_ids[:limit]

        all_trade_ids.extend(trade_ids)
        logger.info("Year %d: stored %d trades (total: %d)", year, len(trade_ids), len(all_trade_ids))

    return all_trade_ids


async def backfill_senate(days: int = 90) -> list[int]:
    """Scrape Senate filings going back N days."""
    logger.info("=== Backfilling Senate filings (last %d days) ===", days)
    return await scrape_and_store_senate(days_back=days)


async def main(args: argparse.Namespace) -> None:
    await init_db()

    all_trade_ids: list[int] = []

    if args.senate:
        senate_ids = await backfill_senate(days=args.days)
        all_trade_ids.extend(senate_ids)
    else:
        house_ids = await backfill_house(years=args.years, limit=args.limit)
        all_trade_ids.extend(house_ids)

    logger.info("Backfill complete: %d total new trades", len(all_trade_ids))

    if args.enrich and all_trade_ids:
        # Enrich in batches to avoid overwhelming external APIs
        batch_size = 20
        for i in range(0, len(all_trade_ids), batch_size):
            batch = all_trade_ids[i : i + batch_size]
            logger.info("Enriching batch %d-%d of %d", i + 1, i + len(batch), len(all_trade_ids))
            await enrich_trades(batch)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill historical Congressional trade data")
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=[2024, 2025],
        help="Years to backfill (default: 2024 2025)",
    )
    parser.add_argument("--senate", action="store_true", help="Backfill Senate instead of House")
    parser.add_argument("--days", type=int, default=90, help="Days back for Senate backfill")
    parser.add_argument("--limit", type=int, default=None, help="Limit filings per year")
    parser.add_argument("--enrich", action="store_true", help="Also run enrichment on new trades")
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")

    asyncio.run(main(args))
