"""Scrapers package — House Clerk, Senate EFD, PDF parser, and scheduler."""

from congress_trades.scrapers.house_clerk import (
    download_pdf,
    scrape_house_all_years,
    scrape_house_disclosures,
)
from congress_trades.scrapers.pdf_parser import (
    parse_filing,
    parse_pdf_structured,
    parse_pdf_with_claude,
)
from congress_trades.scrapers.scheduler import (
    get_scheduler,
    mark_filing_seen,
    scrape_house,
    scrape_senate,
    start_scheduler,
    stop_scheduler,
)
from congress_trades.scrapers.senate_efd import (
    scrape_senate_filings,
    scrape_senate_full,
    scrape_senate_ptr,
)

__all__ = [
    # House Clerk
    "scrape_house_disclosures",
    "scrape_house_all_years",
    "download_pdf",
    # Senate EFD
    "scrape_senate_filings",
    "scrape_senate_full",
    "scrape_senate_ptr",
    # PDF Parser
    "parse_filing",
    "parse_pdf_structured",
    "parse_pdf_with_claude",
    # Scheduler
    "start_scheduler",
    "stop_scheduler",
    "get_scheduler",
    "scrape_house",
    "scrape_senate",
    "mark_filing_seen",
]
