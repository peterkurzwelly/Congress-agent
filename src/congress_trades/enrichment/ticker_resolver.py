"""Layered ticker resolution: local dict -> SEC EDGAR -> Claude fuzzy match."""

import logging

import httpx

from congress_trades.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Layer 1: Local dictionary of ~100 most-traded tickers in Congress filings
# ---------------------------------------------------------------------------

COMMON_TICKERS: dict[str, str] = {
    # Mega-cap tech
    "AAPL": "Apple Inc",
    "MSFT": "Microsoft Corporation",
    "GOOGL": "Alphabet Inc",
    "GOOG": "Alphabet Inc",
    "AMZN": "Amazon.com Inc",
    "META": "Meta Platforms Inc",
    "NVDA": "NVIDIA Corporation",
    "TSLA": "Tesla Inc",
    "AVGO": "Broadcom Inc",
    "ORCL": "Oracle Corporation",
    "CRM": "Salesforce Inc",
    "ADBE": "Adobe Inc",
    "CSCO": "Cisco Systems Inc",
    "AMD": "Advanced Micro Devices Inc",
    "INTC": "Intel Corporation",
    "QCOM": "Qualcomm Inc",
    "IBM": "International Business Machines",
    "TXN": "Texas Instruments Inc",
    "NOW": "ServiceNow Inc",
    "INTU": "Intuit Inc",
    "AMAT": "Applied Materials Inc",
    "MU": "Micron Technology Inc",
    "PANW": "Palo Alto Networks Inc",
    "SNPS": "Synopsys Inc",
    "CDNS": "Cadence Design Systems Inc",
    # Finance
    "JPM": "JPMorgan Chase & Co",
    "BAC": "Bank of America Corporation",
    "WFC": "Wells Fargo & Company",
    "GS": "Goldman Sachs Group Inc",
    "MS": "Morgan Stanley",
    "C": "Citigroup Inc",
    "BLK": "BlackRock Inc",
    "SCHW": "Charles Schwab Corporation",
    "AXP": "American Express Company",
    "V": "Visa Inc",
    "MA": "Mastercard Inc",
    "PYPL": "PayPal Holdings Inc",
    # Healthcare / Pharma
    "JNJ": "Johnson & Johnson",
    "UNH": "UnitedHealth Group Inc",
    "PFE": "Pfizer Inc",
    "ABBV": "AbbVie Inc",
    "LLY": "Eli Lilly and Company",
    "MRK": "Merck & Co Inc",
    "TMO": "Thermo Fisher Scientific Inc",
    "ABT": "Abbott Laboratories",
    "BMY": "Bristol-Myers Squibb Company",
    "AMGN": "Amgen Inc",
    "GILD": "Gilead Sciences Inc",
    "ISRG": "Intuitive Surgical Inc",
    "MRNA": "Moderna Inc",
    # Defense / Aerospace
    "LMT": "Lockheed Martin Corporation",
    "RTX": "RTX Corporation",
    "BA": "Boeing Company",
    "NOC": "Northrop Grumman Corporation",
    "GD": "General Dynamics Corporation",
    "LHX": "L3Harris Technologies Inc",
    "HII": "Huntington Ingalls Industries Inc",
    # Energy
    "XOM": "Exxon Mobil Corporation",
    "CVX": "Chevron Corporation",
    "COP": "ConocoPhillips",
    "SLB": "Schlumberger NV",
    "EOG": "EOG Resources Inc",
    "OXY": "Occidental Petroleum Corporation",
    "PSX": "Phillips 66",
    "VLO": "Valero Energy Corporation",
    # Consumer
    "WMT": "Walmart Inc",
    "COST": "Costco Wholesale Corporation",
    "HD": "Home Depot Inc",
    "PG": "Procter & Gamble Company",
    "KO": "Coca-Cola Company",
    "PEP": "PepsiCo Inc",
    "MCD": "McDonald's Corporation",
    "NKE": "Nike Inc",
    "SBUX": "Starbucks Corporation",
    "TGT": "Target Corporation",
    "DIS": "Walt Disney Company",
    # Industrial / Transport
    "CAT": "Caterpillar Inc",
    "DE": "Deere & Company",
    "UPS": "United Parcel Service Inc",
    "HON": "Honeywell International Inc",
    "GE": "General Electric Company",
    "MMM": "3M Company",
    "UNP": "Union Pacific Corporation",
    # Telecom / Media
    "T": "AT&T Inc",
    "VZ": "Verizon Communications Inc",
    "TMUS": "T-Mobile US Inc",
    "CMCSA": "Comcast Corporation",
    "NFLX": "Netflix Inc",
    # Real-estate / Utilities
    "NEE": "NextEra Energy Inc",
    "AMT": "American Tower Corporation",
    "D": "Dominion Energy Inc",
    "SO": "Southern Company",
    "DUK": "Duke Energy Corporation",
}

# Reverse map: lowercase company name fragment -> ticker
_NAME_TO_TICKER: dict[str, str] = {v.lower(): k for k, v in COMMON_TICKERS.items()}

# Module-level resolution cache (asset_description -> ticker)
_resolve_cache: dict[str, str | None] = {}


def _local_lookup(description: str) -> str | None:
    """Try to match against the local dictionary."""
    desc_lower = description.lower().strip()

    # Direct ticker match (e.g., description is just "AAPL")
    desc_upper = description.strip().upper()
    if desc_upper in COMMON_TICKERS:
        return desc_upper

    # Check if description contains a known ticker in parentheses, e.g. "Apple Inc (AAPL)"
    for ticker in COMMON_TICKERS:
        if f"({ticker})" in description.upper():
            return ticker

    # Substring match against known company names
    for name, ticker in _NAME_TO_TICKER.items():
        if name in desc_lower:
            return ticker
        # Match on core company name without suffixes
        core = (
            name.replace(" inc", "")
            .replace(" corporation", "")
            .replace(" company", "")
            .replace(" & co", "")
            .replace(" nv", "")
            .strip()
        )
        if len(core) > 3 and core in desc_lower:
            return ticker

    return None


async def _sec_edgar_lookup(description: str) -> str | None:
    """Search SEC EDGAR company tickers JSON for a match."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://www.sec.gov/files/company_tickers.json",
                headers={
                    "User-Agent": "CongressTradesBot/1.0 (research@example.com)"
                },
            )
            if resp.status_code != 200:
                return None

            data = resp.json()
            desc_lower = description.lower()
            best_match: str | None = None
            best_score = 0

            for _key, entry in data.items():
                title = entry.get("title", "").lower()
                if not title:
                    continue
                # Exact containment in either direction
                if title in desc_lower or desc_lower in title:
                    score = len(title)
                    if score > best_score:
                        best_score = score
                        best_match = entry.get("ticker", "").upper()

            return best_match
    except Exception as exc:
        logger.debug("SEC EDGAR lookup failed: %s", exc)
        return None


async def _claude_fuzzy_match(description: str) -> str | None:
    """Use Claude to extract / guess the ticker from an asset description."""
    if not settings.ANTHROPIC_API_KEY:
        logger.debug("No ANTHROPIC_API_KEY; skipping Claude fuzzy match.")
        return None

    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        message = await client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=50,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "What is the stock ticker symbol for this asset? "
                        "Respond with ONLY the ticker symbol in uppercase, "
                        "or 'UNKNOWN' if you cannot determine it.\n\n"
                        f"Asset description: {description}"
                    ),
                }
            ],
        )
        result = message.content[0].text.strip().upper()
        if result and result != "UNKNOWN" and len(result) <= 10:
            return result
    except Exception as exc:
        logger.warning("Claude fuzzy match failed for %r: %s", description, exc)

    return None


async def resolve_ticker(
    asset_description: str, known_ticker: str | None = None
) -> str | None:
    """Resolve an asset description to a stock ticker using a layered approach.

    Resolution order:
    1. Return known_ticker if already provided and valid.
    2. Local dictionary lookup (~100 common Congressional trades).
    3. SEC EDGAR company tickers JSON (free, no auth).
    4. Claude fuzzy matching fallback.

    Results are cached in a module-level dict.
    """
    # If a valid ticker is already provided, trust it
    if known_ticker and known_ticker.strip():
        ticker = known_ticker.strip().upper()
        _resolve_cache[asset_description] = ticker
        return ticker

    # Check cache
    if asset_description in _resolve_cache:
        return _resolve_cache[asset_description]

    # Layer 1: Local dictionary
    result = _local_lookup(asset_description)
    if result:
        logger.info("Resolved via local dict: %r -> %s", asset_description, result)
        _resolve_cache[asset_description] = result
        return result

    # Layer 2: SEC EDGAR
    result = await _sec_edgar_lookup(asset_description)
    if result:
        logger.info("Resolved via SEC EDGAR: %r -> %s", asset_description, result)
        _resolve_cache[asset_description] = result
        return result

    # Layer 3: Claude fuzzy matching
    result = await _claude_fuzzy_match(asset_description)
    if result:
        logger.info("Resolved via Claude: %r -> %s", asset_description, result)
        _resolve_cache[asset_description] = result
        return result

    logger.warning("Could not resolve ticker for: %r", asset_description)
    _resolve_cache[asset_description] = None
    return None
