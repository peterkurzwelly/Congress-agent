"""Async scraper for Senate Electronic Financial Disclosures (efdsearch.senate.gov).

Handles the multi-step flow:
1. GET /search/home/ to obtain CSRF token and session cookie
2. POST /search/home/ to accept the usage agreement
3. POST /search/ with search filters to get filing listings
4. Scrape individual PTR pages for structured transaction tables
"""

import asyncio
import hashlib
import logging
import re
from datetime import date, datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup, Tag

from congress_trades.api.schemas import RawTradeRecord
from congress_trades.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://efdsearch.senate.gov"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

MAX_RETRIES = 3
INITIAL_BACKOFF = 2.0

# Amount range mapping for common Senate disclosure ranges
AMOUNT_RANGES: dict[str, tuple[int, int]] = {
    "$1,001 - $15,000": (1_001, 15_000),
    "$15,001 - $50,000": (15_001, 50_000),
    "$50,001 - $100,000": (50_001, 100_000),
    "$100,001 - $250,000": (100_001, 250_000),
    "$250,001 - $500,000": (250_001, 500_000),
    "$500,001 - $1,000,000": (500_001, 1_000_000),
    "$1,000,001 - $5,000,000": (1_000_001, 5_000_000),
    "$5,000,001 - $25,000,000": (5_000_001, 25_000_000),
    "$25,000,001 - $50,000,000": (25_000_001, 50_000_000),
    "Over $50,000,000": (50_000_001, 100_000_000),
}


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


def _extract_csrf_token(html: str) -> str:
    """Extract the CSRF middleware token from the page HTML."""
    soup = BeautifulSoup(html, "html.parser")
    token_input = soup.find("input", {"name": "csrfmiddlewaretoken"})
    if token_input and isinstance(token_input, Tag):
        return str(token_input.get("value", ""))

    # Fallback: look in a <script> or meta tag
    meta = soup.find("meta", {"name": "csrf-token"})
    if meta and isinstance(meta, Tag):
        return str(meta.get("content", ""))

    raise ValueError("Could not extract CSRF token from page")


def _parse_amount_range(text: str) -> tuple[str, int, int]:
    """Parse an amount range string into (display, min, max).

    Returns the original text as display and best-effort numeric bounds.
    """
    text = text.strip()

    # Check known ranges first
    if text in AMOUNT_RANGES:
        low, high = AMOUNT_RANGES[text]
        return text, low, high

    # Try to parse generic "$X - $Y" format
    match = re.match(
        r"\$?([\d,]+)\s*-\s*\$?([\d,]+)",
        text.replace(",", ""),
    )
    if match:
        low = int(match.group(1).replace(",", ""))
        high = int(match.group(2).replace(",", ""))
        return text, low, high

    # "Over $X" format
    match = re.match(r"[Oo]ver\s*\$?([\d,]+)", text)
    if match:
        low = int(match.group(1).replace(",", ""))
        return text, low, low * 2

    logger.warning("Could not parse amount range: %r", text)
    return text, 0, 0


def _parse_date_text(text: str) -> date:
    """Parse a date string from Senate EFD pages."""
    text = text.strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%b %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    # Fallback regex
    match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", text)
    if match:
        m, d, y = match.groups()
        y_int = int(y) if len(y) == 4 else 2000 + int(y)
        return date(y_int, int(m), int(d))
    logger.warning("Could not parse date: %r, using today", text)
    return date.today()


def _generate_filing_id(url: str) -> str:
    """Create a stable unique filing ID from the filing URL."""
    return "senate-" + hashlib.sha256(url.encode()).hexdigest()[:16]


async def _accept_agreement(client: httpx.AsyncClient) -> None:
    """Complete the Senate EFD agreement flow to get an authenticated session.

    Steps:
    1. GET /search/home/ to get the CSRF token and initial cookies
    2. POST /search/home/ with the agreement acceptance
    """
    home_url = f"{BASE_URL}/search/home/"

    # Step 1: Get CSRF token
    response = await _request_with_backoff(client, "GET", home_url)
    csrf_token = _extract_csrf_token(response.text)
    logger.debug("Got CSRF token: %s...", csrf_token[:10])

    # Step 2: Accept the agreement
    await _request_with_backoff(
        client,
        "POST",
        home_url,
        data={
            "csrfmiddlewaretoken": csrf_token,
            "prohibition_agreement": "1",
        },
        headers={
            **HEADERS,
            "Referer": home_url,
        },
    )
    logger.info("Senate EFD agreement accepted")


def _parse_search_results(html: str) -> list[dict[str, Any]]:
    """Parse the search results page for filing links.

    Returns a list of dicts with filing_url, name, filing_date, filing_type.
    """
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, Any]] = []

    table = soup.find("table", class_="table") or soup.find("table")
    if not table:
        logger.info("No results table found in Senate search results")
        return results

    rows = table.find_all("tr")[1:]  # skip header
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 4:
            continue

        try:
            # Name is in the first column
            name = cols[0].get_text(strip=True)

            # Filing link
            link = row.find("a", href=True)
            if not link:
                continue
            href = str(link["href"])
            filing_url = href if href.startswith("http") else BASE_URL + href

            # Office / filer type
            office = cols[1].get_text(strip=True) if len(cols) > 1 else ""

            # Filing type
            filing_type_text = cols[2].get_text(strip=True) if len(cols) > 2 else ""

            # Date
            date_text = cols[3].get_text(strip=True) if len(cols) > 3 else ""
            filing_date = _parse_date_text(date_text) if date_text else date.today()

            filing_id = _generate_filing_id(filing_url)

            results.append(
                {
                    "name": name,
                    "office": office,
                    "filing_type": filing_type_text,
                    "filing_url": filing_url,
                    "filing_date": filing_date,
                    "filing_id": filing_id,
                    "source": "senate",
                }
            )
        except (ValueError, IndexError) as exc:
            logger.warning("Failed to parse search row: %s", exc)
            continue

    return results


def _parse_ptr_table(html: str) -> list[RawTradeRecord]:
    """Parse a Senate PTR detail page for transaction rows.

    Senate PTR pages have an HTML table with columns:
    #, Transaction Date, Owner, Ticker, Asset Name, Asset Type, Type, Amount, Comment
    """
    soup = BeautifulSoup(html, "html.parser")
    records: list[RawTradeRecord] = []

    # Find the transaction table
    table = soup.find("table", class_="table") or soup.find("table")
    if not table:
        logger.info("No transaction table found on PTR page")
        return records

    # Get header columns to determine indices
    header_row = table.find("tr")
    if not header_row:
        return records

    headers = [th.get_text(strip=True).lower() for th in header_row.find_all(["th", "td"])]

    # Build a column index map
    col_map: dict[str, int] = {}
    for idx, header in enumerate(headers):
        if "transaction" in header and "date" in header:
            col_map["date"] = idx
        elif header in ("owner",):
            col_map["owner"] = idx
        elif header in ("ticker",):
            col_map["ticker"] = idx
        elif "asset" in header and "name" in header:
            col_map["asset_name"] = idx
        elif "asset" in header and "type" in header:
            col_map["asset_type"] = idx
        elif header in ("type",) and "asset" not in header:
            col_map["tx_type"] = idx
        elif header in ("amount",):
            col_map["amount"] = idx
        elif header in ("comment", "comments"):
            col_map["comment"] = idx
        elif header == "#":
            col_map["row_num"] = idx

    # Fallback column indices if header detection fails
    if not col_map:
        col_map = {
            "row_num": 0,
            "date": 1,
            "owner": 2,
            "ticker": 3,
            "asset_name": 4,
            "asset_type": 5,
            "tx_type": 6,
            "amount": 7,
            "comment": 8,
        }

    rows = table.find_all("tr")[1:]  # skip header
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 5:
            continue

        try:
            def _get(key: str, default: str = "") -> str:
                idx = col_map.get(key)
                if idx is not None and idx < len(cols):
                    return cols[idx].get_text(strip=True)
                return default

            date_text = _get("date")
            owner = _get("owner", "Self")
            ticker = _get("ticker") or None
            asset_name = _get("asset_name", "Unknown")
            asset_type = _get("asset_type", "Stock")
            tx_type = _get("tx_type", "Purchase")
            amount_text = _get("amount", "$1,001 - $15,000")
            comment = _get("comment") or None

            transaction_date = _parse_date_text(date_text)
            amount_range, amount_min, amount_max = _parse_amount_range(amount_text)

            # Clean up ticker (sometimes has extra whitespace or dashes)
            if ticker:
                ticker = ticker.strip().strip("-").strip()
                if not ticker or ticker == "--":
                    ticker = None

            record = RawTradeRecord(
                transaction_date=transaction_date,
                owner=owner or "Self",
                asset_description=asset_name,
                ticker=ticker,
                asset_type=asset_type or "Stock",
                tx_type=tx_type,
                amount_range=amount_range,
                amount_min=amount_min,
                amount_max=amount_max,
                comment=comment,
            )
            records.append(record)

        except Exception as exc:
            logger.warning("Failed to parse PTR row: %s", exc)
            continue

    return records


async def scrape_senate_filings(
    date_from: date | None = None,
    date_to: date | None = None,
    first_name: str = "",
    last_name: str = "",
) -> list[dict[str, Any]]:
    """Search for Senate PTR filings and return metadata.

    Parameters
    ----------
    date_from : date | None
        Start date for the search. Defaults to 30 days ago.
    date_to : date | None
        End date for the search. Defaults to today.
    first_name : str
        Filter by first name.
    last_name : str
        Filter by last name.

    Returns
    -------
    list[dict[str, Any]]
        List of filing metadata dicts.
    """
    from datetime import timedelta

    if date_to is None:
        date_to = date.today()
    if date_from is None:
        date_from = date_to - timedelta(days=30)

    async with httpx.AsyncClient(
        headers=HEADERS,
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
        cookies=httpx.Cookies(),
    ) as client:
        # Step 1+2: Accept agreement, get session
        await _accept_agreement(client)

        # Step 3: POST search with filters
        search_url = f"{BASE_URL}/search/"
        search_data = {
            "filer_type": "1",  # Senator
            "report_type": "11",  # Periodic Transaction Report
            "submitted_start_date": date_from.strftime("%m/%d/%Y"),
            "submitted_end_date": date_to.strftime("%m/%d/%Y"),
            "first_name": first_name,
            "last_name": last_name,
        }

        # We need the CSRF token for the search POST too
        search_page = await _request_with_backoff(client, "GET", search_url)
        csrf_token = _extract_csrf_token(search_page.text)

        search_data["csrfmiddlewaretoken"] = csrf_token

        logger.info(
            "Searching Senate filings: %s to %s",
            date_from.isoformat(),
            date_to.isoformat(),
        )
        response = await _request_with_backoff(
            client,
            "POST",
            search_url,
            data=search_data,
            headers={**HEADERS, "Referer": search_url},
        )

        filings = _parse_search_results(response.text)
        logger.info("Found %d Senate filings", len(filings))
        return filings


async def scrape_senate_ptr(
    filing_url: str,
    client: httpx.AsyncClient | None = None,
) -> list[RawTradeRecord]:
    """Scrape a single Senate PTR page for transaction records.

    Parameters
    ----------
    filing_url : str
        URL to the PTR detail page (e.g., /search/view/ptr/{uuid}/).
    client : httpx.AsyncClient | None
        Reuse an existing client, or create a new one.

    Returns
    -------
    list[RawTradeRecord]
        Parsed transaction records from the PTR.
    """
    should_close = client is None

    if client is None:
        client = httpx.AsyncClient(
            headers=HEADERS,
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
            cookies=httpx.Cookies(),
        )
        await _accept_agreement(client)

    try:
        response = await _request_with_backoff(client, "GET", filing_url)
        records = _parse_ptr_table(response.text)
        logger.info("Parsed %d transactions from %s", len(records), filing_url)
        return records
    finally:
        if should_close:
            await client.aclose()


async def scrape_senate_full(
    date_from: date | None = None,
    date_to: date | None = None,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Full scrape: search for filings, then parse each PTR page.

    Returns filing metadata dicts augmented with a 'transactions' key
    containing the list of RawTradeRecord for that filing.
    """
    from datetime import timedelta

    if date_to is None:
        date_to = date.today()
    if date_from is None:
        date_from = date_to - timedelta(days=30)

    async with httpx.AsyncClient(
        headers=HEADERS,
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
        cookies=httpx.Cookies(),
    ) as client:
        await _accept_agreement(client)

        # Search for filings
        search_url = f"{BASE_URL}/search/"
        search_page = await _request_with_backoff(client, "GET", search_url)
        csrf_token = _extract_csrf_token(search_page.text)

        search_data = {
            "csrfmiddlewaretoken": csrf_token,
            "filer_type": "1",
            "report_type": "11",
            "submitted_start_date": date_from.strftime("%m/%d/%Y"),
            "submitted_end_date": date_to.strftime("%m/%d/%Y"),
            "first_name": kwargs.get("first_name", ""),
            "last_name": kwargs.get("last_name", ""),
        }

        response = await _request_with_backoff(
            client,
            "POST",
            search_url,
            data=search_data,
            headers={**HEADERS, "Referer": search_url},
        )
        filings = _parse_search_results(response.text)
        logger.info("Found %d Senate filings to scrape", len(filings))

        # Parse each PTR page
        for filing in filings:
            try:
                url = filing["filing_url"]
                # Only scrape PTR detail pages
                if "/ptr/" in url or "/view/" in url:
                    records = await scrape_senate_ptr(url, client=client)
                    filing["transactions"] = [r.model_dump() for r in records]
                else:
                    filing["transactions"] = []
            except Exception as exc:
                logger.error("Failed to scrape PTR %s: %s", filing.get("filing_url"), exc)
                filing["transactions"] = []

    return filings
