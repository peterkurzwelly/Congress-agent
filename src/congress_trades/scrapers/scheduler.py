"""APScheduler-based scheduling for periodic scraping jobs.

Provides start_scheduler() and stop_scheduler() functions that manage
recurring House and Senate scraping jobs with deduplication via
last-seen filing ID tracking.
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from congress_trades.config import settings

logger = logging.getLogger(__name__)

# Module-level scheduler instance
_scheduler: AsyncIOScheduler | None = None

# Track last-seen filing IDs to avoid reprocessing.
# In production this would be backed by the database, but we keep an
# in-memory set here as a fast first-pass filter.
_seen_house_filing_ids: set[str] = set()
_seen_senate_filing_ids: set[str] = set()


async def scrape_house() -> None:
    """Scheduled job: scrape House financial disclosures.

    Calls the real pipeline function to scrape, parse PDFs, store in DB,
    then enriches the newly discovered trades.
    """
    from congress_trades.pipeline import enrich_trades, scrape_and_store_house

    logger.info("Starting scheduled House scrape")

    try:
        new_trade_ids = await scrape_and_store_house()
        logger.info("House scrape stored %d new trades", len(new_trade_ids))

        if new_trade_ids:
            await enrich_trades(new_trade_ids)
            logger.info("Enriched %d House trades", len(new_trade_ids))

    except Exception as exc:
        logger.error("House scrape job failed: %s", exc, exc_info=True)


async def scrape_senate() -> None:
    """Scheduled job: scrape Senate periodic transaction reports.

    Calls the real pipeline function to scrape, parse PTR tables, store in DB,
    then enriches the newly discovered trades.
    """
    from congress_trades.pipeline import enrich_trades, scrape_and_store_senate

    logger.info("Starting scheduled Senate scrape")

    try:
        new_trade_ids = await scrape_and_store_senate()
        logger.info("Senate scrape stored %d new trades", len(new_trade_ids))

        if new_trade_ids:
            await enrich_trades(new_trade_ids)
            logger.info("Enriched %d Senate trades", len(new_trade_ids))

    except Exception as exc:
        logger.error("Senate scrape job failed: %s", exc, exc_info=True)


def start_scheduler() -> AsyncIOScheduler:
    """Create and start the APScheduler with House and Senate scrape jobs.

    Returns the scheduler instance so callers can inspect or modify jobs.
    """
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        logger.warning("Scheduler is already running")
        return _scheduler

    _scheduler = AsyncIOScheduler()

    # House scrape job
    _scheduler.add_job(
        scrape_house,
        trigger=IntervalTrigger(hours=settings.SCRAPE_INTERVAL_HOURS),
        id="scrape_house",
        name="House Financial Disclosure Scraper",
        replace_existing=True,
        max_instances=1,
    )

    # Senate scrape job
    _scheduler.add_job(
        scrape_senate,
        trigger=IntervalTrigger(hours=settings.SENATE_SCRAPE_INTERVAL_HOURS),
        id="scrape_senate",
        name="Senate EFD PTR Scraper",
        replace_existing=True,
        max_instances=1,
    )

    _scheduler.start()
    logger.info(
        "Scheduler started: House every %dh, Senate every %dh",
        settings.SCRAPE_INTERVAL_HOURS,
        settings.SENATE_SCRAPE_INTERVAL_HOURS,
    )
    return _scheduler


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler if running."""
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=True)
        logger.info("Scheduler stopped")
    else:
        logger.info("Scheduler was not running")

    _scheduler = None


def get_scheduler() -> AsyncIOScheduler | None:
    """Return the current scheduler instance (or None if not started)."""
    return _scheduler


def get_seen_filing_ids() -> dict[str, set[str]]:
    """Return the current sets of seen filing IDs (for debugging/monitoring)."""
    return {
        "house": _seen_house_filing_ids.copy(),
        "senate": _seen_senate_filing_ids.copy(),
    }


def mark_filing_seen(filing_id: str, source: str = "house") -> None:
    """Manually mark a filing ID as seen (e.g., when loading from DB on startup).

    Parameters
    ----------
    filing_id : str
        The filing ID to mark.
    source : str
        Either "house" or "senate".
    """
    if source == "house":
        _seen_house_filing_ids.add(filing_id)
    elif source == "senate":
        _seen_senate_filing_ids.add(filing_id)
    else:
        logger.warning("Unknown source %r for filing ID %s", source, filing_id)
