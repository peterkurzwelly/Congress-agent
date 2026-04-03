"""Maps Congress members to committee assignments and committees to sectors."""

import logging

import httpx

from congress_trades.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Committee -> Sector mapping
# ---------------------------------------------------------------------------

COMMITTEE_SECTOR_MAP: dict[str, list[str]] = {
    # House committees
    "Armed Services": ["Defense", "Aerospace"],
    "Financial Services": ["Banking", "Finance", "Insurance"],
    "Energy and Commerce": ["Energy", "Healthcare", "Telecommunications"],
    "Ways and Means": ["Finance", "Tax", "Trade"],
    "Appropriations": ["Government Spending"],
    "Agriculture": ["Agriculture", "Commodities"],
    "Transportation and Infrastructure": ["Transportation", "Infrastructure", "Construction"],
    "Science, Space, and Technology": ["Technology", "Aerospace", "Science"],
    "Judiciary": ["Legal", "Technology"],
    "Oversight and Accountability": ["Government"],
    "Education and the Workforce": ["Education", "Labor"],
    "Foreign Affairs": ["Defense", "International"],
    "Homeland Security": ["Defense", "Cybersecurity"],
    "Natural Resources": ["Energy", "Mining", "Real Estate"],
    "Small Business": ["Small Business"],
    "Veterans' Affairs": ["Healthcare", "Defense"],
    "Intelligence": ["Defense", "Technology", "Cybersecurity"],
    # Senate committees
    "Banking, Housing, and Urban Affairs": ["Banking", "Finance", "Real Estate"],
    "Commerce, Science, and Transportation": ["Technology", "Telecommunications", "Transportation"],
    "Environment and Public Works": ["Energy", "Infrastructure", "Environment"],
    "Finance": ["Finance", "Tax", "Healthcare"],
    "Health, Education, Labor, and Pensions": ["Healthcare", "Education", "Pharma"],
    "Indian Affairs": ["Gaming", "Natural Resources"],
    "Rules and Administration": ["Government"],
    "Budget": ["Finance", "Government Spending"],
    "Aging": ["Healthcare", "Pharma"],
}

# Ticker -> sector mapping for well-known stocks (used for overlap scoring)
_TICKER_SECTOR_HINTS: dict[str, list[str]] = {
    # Defense
    "LMT": ["Defense", "Aerospace"],
    "RTX": ["Defense", "Aerospace"],
    "BA": ["Defense", "Aerospace"],
    "NOC": ["Defense", "Aerospace"],
    "GD": ["Defense", "Aerospace"],
    "LHX": ["Defense", "Technology"],
    "HII": ["Defense"],
    # Tech
    "AAPL": ["Technology"],
    "MSFT": ["Technology"],
    "GOOGL": ["Technology"],
    "AMZN": ["Technology", "Retail"],
    "META": ["Technology", "Telecommunications"],
    "NVDA": ["Technology"],
    "TSLA": ["Technology", "Automotive"],
    "CRM": ["Technology"],
    "INTC": ["Technology"],
    "AMD": ["Technology"],
    # Finance
    "JPM": ["Banking", "Finance"],
    "BAC": ["Banking", "Finance"],
    "GS": ["Banking", "Finance"],
    "MS": ["Banking", "Finance"],
    "WFC": ["Banking", "Finance"],
    "C": ["Banking", "Finance"],
    "V": ["Finance"],
    "MA": ["Finance"],
    # Healthcare / Pharma
    "JNJ": ["Healthcare", "Pharma"],
    "PFE": ["Healthcare", "Pharma"],
    "UNH": ["Healthcare", "Insurance"],
    "LLY": ["Healthcare", "Pharma"],
    "MRK": ["Healthcare", "Pharma"],
    "ABBV": ["Healthcare", "Pharma"],
    "MRNA": ["Healthcare", "Pharma"],
    # Energy
    "XOM": ["Energy"],
    "CVX": ["Energy"],
    "COP": ["Energy"],
    "OXY": ["Energy"],
    "NEE": ["Energy", "Utilities"],
    # Telecom
    "T": ["Telecommunications"],
    "VZ": ["Telecommunications"],
    "TMUS": ["Telecommunications"],
    "CMCSA": ["Telecommunications", "Media"],
}


def get_committee_relevance(
    committees: dict | None,
    ticker: str | None,
    sector: str | None = None,
) -> float:
    """Calculate overlap score (0.0-1.0) between a member's committees and a trade.

    Higher scores mean the member sits on committees with jurisdiction over the
    sector/industry of the traded stock, which raises conflict-of-interest flags.
    """
    if not committees or not ticker:
        return 0.0

    # Determine sectors relevant to this ticker
    ticker_sectors: set[str] = set()
    if ticker.upper() in _TICKER_SECTOR_HINTS:
        ticker_sectors.update(_TICKER_SECTOR_HINTS[ticker.upper()])
    if sector:
        ticker_sectors.add(sector)

    if not ticker_sectors:
        return 0.0

    # Collect sectors covered by the member's committees
    member_sectors: set[str] = set()
    committee_names: list[str] = []

    # committees might be {"committees": [{"name": "...", ...}]} or a flat list
    raw_committees = committees
    if isinstance(raw_committees, dict):
        raw_committees = raw_committees.get("committees", [])

    if isinstance(raw_committees, list):
        for c in raw_committees:
            if isinstance(c, dict):
                committee_names.append(c.get("name", ""))
            elif isinstance(c, str):
                committee_names.append(c)
    elif isinstance(raw_committees, dict):
        # Fallback: keys are committee names
        committee_names = list(raw_committees.keys())

    for cname in committee_names:
        for map_key, sectors in COMMITTEE_SECTOR_MAP.items():
            if map_key.lower() in cname.lower() or cname.lower() in map_key.lower():
                member_sectors.update(sectors)

    if not member_sectors:
        return 0.0

    # Score = fraction of ticker sectors that overlap with member's committee sectors
    overlap = ticker_sectors & member_sectors
    score = len(overlap) / len(ticker_sectors)
    return min(score, 1.0)


async def fetch_member_committees(bioguide_id: str) -> dict:
    """Fetch committee assignments from Congress.gov API.

    Returns dict like:
        {"committees": [{"name": "Armed Services", "chamber": "house", ...}]}
    """
    if not settings.CONGRESS_API_KEY:
        logger.debug("No CONGRESS_API_KEY configured; returning empty committees.")
        return {"committees": []}

    url = f"https://api.congress.gov/v3/member/{bioguide_id}"
    params = {"api_key": settings.CONGRESS_API_KEY, "format": "json"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                logger.warning(
                    "Congress.gov API returned %d for member %s",
                    resp.status_code,
                    bioguide_id,
                )
                return {"committees": []}

            data = resp.json()
            member_data = data.get("member", {})

            # Extract current committee assignments
            committees: list[dict] = []

            # The v3 API nests committees under the member object
            # Try fetching the committee membership endpoint
            terms = member_data.get("terms", [])
            chamber = "house"
            if terms:
                last_term = terms[-1]
                chamber = last_term.get("chamber", "House of Representatives")
                chamber = "senate" if "Senate" in chamber else "house"

        # Fetch committee memberships separately
        committee_url = (
            f"https://api.congress.gov/v3/member/{bioguide_id}/committees"
        )
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(committee_url, params=params)
            if resp.status_code == 200:
                cdata = resp.json()
                for c in cdata.get("committees", []):
                    committees.append(
                        {
                            "name": c.get("name", ""),
                            "chamber": c.get("chamber", chamber),
                            "url": c.get("url", ""),
                        }
                    )

        return {"committees": committees}

    except Exception as exc:
        logger.warning(
            "Failed to fetch committees for %s: %s", bioguide_id, exc
        )
        return {"committees": []}
