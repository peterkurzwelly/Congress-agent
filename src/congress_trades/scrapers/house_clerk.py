"""Async scraper for House Financial Disclosures (disclosures-clerk.house.gov).

Scrapes the House Clerk's financial disclosure search page for periodic
transaction reports (PTRs) and other filing types. Downloads PDFs for
subsequent parsing by the pdf_parser module.
"""

import asyncio
import hashlib
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from congress_trades.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://disclosures-clerk.house.gov"
SEARCH_URL = f"{BASE_URL}/FinancialDisclosure/ViewMemberSearchResult"

# Directory where downloaded PDFs are stored
PDF_DIR = Path("data/house_pdfs")

# Headers to mimic a real browser
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": f"{BASE_URL}/FinancialDisclosure",
}

# Exponential backoff parameters
MAX_RETRIES = 3
INITIAL_BACKOFF = 2.0


async def _request_with_backoff(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    **kwargs: Any,
) -> httpx.Response:
    """Make an HTTP request with exponential backoff on failure."""
    backoff = INITIAL_BACKOFF
    last_exc: Exception | None = None

    for attempt in range(MAX_RETRIES):
        try:
            await asyncio.sleep(settings.REQUEST_DELAY_SECONDS)
            response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            last_exc = exc
            if attempt < MAX_RETRIES - 1:
                logger.warning(
                    "Request to %s failed (attempt %d/%d): %s — retrying in %.1fs",
                    url,
                    attempt + 1,
                    MAX_RETRIES,
                    exc,
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff *= 2
            else:
                logger.error(
                    "Request to %s failed after %d attempts: %s",
                    url,
                    MAX_RETRIES,
                    exc,
                )

    raise last_exc  # type: ignore[misc]


def _parse_search_results(html: str) -> list[dict[str, Any]]:
    """Parse the HTML results table and return a list of filing metadata dicts.

    Each dict contains:
        - name: str (member name)
        - office: str (state/district)
        - year: int (filing year)
        - filing_type: str (e.g. "Periodic Transaction Report")
        - pdf_url: str (absolute URL to the PDF)
        - filing_date: date
        - filing_id: str (hash-based unique ID)
    """
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, Any]] = []

    table = soup.find("table", class_="library-table") or soup.find("table")
    if not table:
        logger.info("No results table found in HTML response")
        return results

    rows = table.find_all("tr")[1:]  # skip header row
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 5:
            continue

        try:
            name = cols[0].get_text(strip=True)
            office = cols[1].get_text(strip=True)
            year_text = cols[2].get_text(strip=True)
            filing_type = cols[3].get_text(strip=True)

            # The PDF link is usually in the first or last column
            link_tag = row.find("a", href=True)
            if not link_tag:
                continue
            href = link_tag["href"]
            pdf_url = urljoin(BASE_URL, href)

            # Filing date is typically the last column
            date_text = cols[-1].get_text(strip=True)
            filing_date = _parse_date(date_text)

            year = int(year_text) if year_text.isdigit() else datetime.now().year

            # Generate a deterministic filing ID from the PDF URL
            filing_id = _generate_filing_id(pdf_url)

            results.append(
                {
                    "name": name,
                    "office": office,
                    "year": year,
                    "filing_type": filing_type,
                    "pdf_url": pdf_url,
                    "filing_date": filing_date,
                    "filing_id": filing_id,
                    "source": "house",
                }
            )
        except (ValueError, IndexError) as exc:
            logger.warning("Failed to parse row: %s — %s", row.get_text(strip=True)[:80], exc)
            continue

    return results


def _parse_date(text: str) -> date:
    """Try common date formats used by the House Clerk site."""
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%b %d, %Y"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    # If nothing works, try to extract anything that looks like a date
    match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", text)
    if match:
        m, d, y = match.groups()
        y_int = int(y) if len(y) == 4 else 2000 + int(y)
        return date(y_int, int(m), int(d))
    logger.warning("Could not parse date: %r, using today", text)
    return date.today()


def _generate_filing_id(pdf_url: str) -> str:
    """Create a stable, unique filing ID from the PDF URL."""
    return "house-" + hashlib.sha256(pdf_url.encode()).hexdigest()[:16]


async def download_pdf(
    client: httpx.AsyncClient,
    pdf_url: str,
    dest_dir: Path | None = None,
) -> Path:
    """Download a PDF from the given URL and return the local file path."""
    dest_dir = dest_dir or PDF_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    filename = pdf_url.split("/")[-1]
    if not filename.endswith(".pdf"):
        filename = _generate_filing_id(pdf_url) + ".pdf"
    local_path = dest_dir / filename

    if local_path.exists():
        logger.debug("PDF already downloaded: %s", local_path)
        return local_path

    response = await _request_with_backoff(client, "GET", pdf_url)
    local_path.write_bytes(response.content)
    logger.info("Downloaded PDF: %s -> %s", pdf_url, local_path)
    return local_path


async def scrape_house_disclosures(
    last_name: str = "",
    filing_year: int | None = None,
    state: str = "",
    district: str = "",
    download_pdfs: bool = True,
) -> list[dict[str, Any]]:
    """Scrape House financial disclosures and optionally download PDFs.

    Parameters
    ----------
    last_name : str
        Filter by member last name (empty string for all).
    filing_year : int | None
        Filing year to search. Defaults to current year.
    state : str
        Two-letter state code (empty for all).
    district : str
        District number (empty for all).
    download_pdfs : bool
        If True, download PDFs to the local data directory.

    Returns
    -------
    list[dict[str, Any]]
        List of filing metadata dicts. Each dict includes 'pdf_path' if
        download_pdfs is True.
    """
    if filing_year is None:
        filing_year = datetime.now().year

    form_data = {
        "LastName": last_name,
        "FilingYear": str(filing_year),
        "State": state,
        "District": district,
    }

    async with httpx.AsyncClient(
        headers=HEADERS,
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
    ) as client:
        logger.info(
            "Scraping House disclosures: year=%d, last_name=%r, state=%r",
            filing_year,
            last_name,
            state,
        )
        response = await _request_with_backoff(
            client,
            "POST",
            SEARCH_URL,
            data=form_data,
        )

        filings = _parse_search_results(response.text)
        logger.info("Found %d House filings", len(filings))

        if download_pdfs:
            for filing in filings:
                try:
                    pdf_path = await download_pdf(client, filing["pdf_url"])
                    filing["pdf_path"] = str(pdf_path)
                except Exception as exc:
                    logger.error(
                        "Failed to download PDF %s: %s",
                        filing["pdf_url"],
                        exc,
                    )
                    filing["pdf_path"] = None

    return filings


async def scrape_house_all_years(
    years: list[int] | None = None,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Scrape across multiple filing years.

    Parameters
    ----------
    years : list[int] | None
        Years to scrape. Defaults to current year only.

    Returns
    -------
    list[dict[str, Any]]
        Combined list of filings from all years.
    """
    if years is None:
        years = [datetime.now().year]

    all_filings: list[dict[str, Any]] = []
    for year in years:
        filings = await scrape_house_disclosures(filing_year=year, **kwargs)
        all_filings.extend(filings)

    return all_filings
