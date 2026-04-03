"""Cross-reference Congressional trades with legislative activity from Congress.gov.

This module fetches bills sponsored/cosponsored by members of Congress and
correlates them with trades to detect suspicious timing patterns -- e.g., a
member buying stock in a sector right before introducing a bill that benefits it.
"""

import logging
from datetime import date, timedelta

import httpx

from congress_trades.config import settings

logger = logging.getLogger(__name__)

_API_BASE = "https://api.congress.gov"

# Mapping from broad sector names to keywords that commonly appear in bill titles
# and subjects. Used for fuzzy matching between a trade's sector and a bill's text.
SECTOR_KEYWORDS: dict[str, list[str]] = {
    "Technology": [
        "technology", "cyber", "data", "digital", "software", "internet",
        "artificial intelligence", "AI", "semiconductor", "chip", "broadband",
        "telecom", "privacy", "encryption",
    ],
    "Healthcare": [
        "health", "medicare", "medicaid", "drug", "pharmaceutical", "hospital",
        "biotech", "vaccine", "medical", "FDA", "prescription", "insurance",
        "patient", "clinical",
    ],
    "Financial Services": [
        "bank", "financial", "securities", "SEC", "loan", "credit", "insurance",
        "fintech", "crypto", "digital asset", "wall street", "interest rate",
        "mortgage",
    ],
    "Energy": [
        "energy", "oil", "gas", "solar", "wind", "nuclear", "renewable",
        "petroleum", "pipeline", "electric", "utility", "carbon", "emission",
        "climate", "fuel",
    ],
    "Defense": [
        "defense", "military", "veteran", "armed forces", "weapon", "missile",
        "navy", "army", "pentagon", "national security", "intelligence",
        "homeland security",
    ],
    "Real Estate": [
        "housing", "real estate", "mortgage", "construction", "zoning",
        "infrastructure", "building", "property",
    ],
    "Consumer Cyclical": [
        "consumer", "retail", "trade", "tariff", "commerce", "import",
        "export", "manufacturing",
    ],
    "Industrials": [
        "infrastructure", "transportation", "highway", "rail", "aviation",
        "manufacturing", "construction", "supply chain",
    ],
    "Communication Services": [
        "telecom", "media", "broadcast", "FCC", "spectrum", "internet",
        "social media", "content", "streaming",
    ],
    "Utilities": [
        "utility", "water", "electric", "power", "grid", "infrastructure",
        "public works",
    ],
    "Basic Materials": [
        "mining", "steel", "chemical", "material", "lumber", "rare earth",
        "mineral",
    ],
}


async def fetch_member_bills(
    bioguide_id: str,
    date_from: date,
    date_to: date,
) -> list[dict]:
    """Fetch bills sponsored and cosponsored by a member within a date range.

    Args:
        bioguide_id: The member's Bioguide identifier.
        date_from: Start of the date window (inclusive).
        date_to: End of the date window (inclusive).

    Returns:
        List of bill dicts with keys: bill_id, title, type, introduced_date,
        subjects, latest_action, relationship ("sponsored" or "cosponsored").
        Returns an empty list when CONGRESS_API_KEY is not configured or on
        API errors.
    """
    api_key = settings.CONGRESS_API_KEY
    if not api_key:
        logger.debug("CONGRESS_API_KEY not set; skipping bill fetch for %s", bioguide_id)
        return []

    bills: list[dict] = []

    for relationship in ("sponsored-legislation", "cosponsored-legislation"):
        try:
            bills.extend(
                await _fetch_bills_for_relationship(
                    bioguide_id, relationship, date_from, date_to, api_key
                )
            )
        except Exception as exc:
            logger.warning(
                "Failed to fetch %s for %s: %s", relationship, bioguide_id, exc
            )

    return bills


async def _fetch_bills_for_relationship(
    bioguide_id: str,
    relationship: str,
    date_from: date,
    date_to: date,
    api_key: str,
) -> list[dict]:
    """Page through the Congress.gov API for a single relationship type."""
    results: list[dict] = []
    offset = 0
    limit = 250
    rel_label = "sponsored" if "cosponsored" not in relationship else "cosponsored"

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            url = f"{_API_BASE}/v3/member/{bioguide_id}/{relationship}"
            params = {
                "api_key": api_key,
                "format": "json",
                "offset": offset,
                "limit": limit,
            }

            resp = await client.get(url, params=params)

            if resp.status_code != 200:
                logger.warning(
                    "Congress.gov API returned %d for %s/%s",
                    resp.status_code,
                    bioguide_id,
                    relationship,
                )
                break

            data = resp.json()
            legislation = data.get("sponsoredLegislation") or data.get(
                "cosponsoredLegislation", []
            )

            if not legislation:
                break

            for bill in legislation:
                introduced_str = bill.get("introducedDate", "")
                if not introduced_str:
                    continue

                try:
                    introduced = date.fromisoformat(introduced_str)
                except ValueError:
                    continue

                if introduced < date_from or introduced > date_to:
                    # Congress.gov returns all bills, not filtered by date,
                    # so we filter client-side.
                    if introduced < date_from:
                        # Bills are returned newest-first by default; once we
                        # pass the window we can stop for sponsored (sorted by
                        # date). But for safety, just skip rather than break.
                        continue
                    continue

                latest_action = bill.get("latestAction", {})
                results.append(
                    {
                        "bill_id": (
                            f"{bill.get('type', '').lower()}"
                            f"{bill.get('number', '')}"
                            f"-{bill.get('congress', '')}"
                        ),
                        "title": bill.get("title", ""),
                        "type": bill.get("type", ""),
                        "introduced_date": introduced_str,
                        "subjects": _extract_subjects(bill),
                        "latest_action": latest_action.get("text", ""),
                        "latest_action_date": latest_action.get("actionDate", ""),
                        "relationship": rel_label,
                    }
                )

            # Pagination: if we got fewer results than the limit, we're done.
            if len(legislation) < limit:
                break
            offset += limit

    return results


def _extract_subjects(bill: dict) -> list[str]:
    """Pull subject terms from a bill dict, handling various API shapes."""
    subjects: list[str] = []

    # The list endpoint may include policyArea at the top level
    policy_area = bill.get("policyArea")
    if isinstance(policy_area, dict) and policy_area.get("name"):
        subjects.append(policy_area["name"])

    # Some responses nest subjects under a "subjects" key
    subj_block = bill.get("subjects")
    if isinstance(subj_block, dict):
        for item in subj_block.get("legislativeSubjects", []):
            if isinstance(item, dict) and item.get("name"):
                subjects.append(item["name"])

    return subjects


def _bill_matches_sector(bill: dict, sector: str | None) -> tuple[bool, str]:
    """Check whether a bill's title or subjects relate to a given sector.

    Returns:
        (is_match, explanation) tuple.
    """
    if not sector:
        return False, ""

    keywords = SECTOR_KEYWORDS.get(sector, [])
    if not keywords:
        # Fallback: try the sector name itself as a keyword
        keywords = [sector.lower()]

    # Combine title and subjects into a searchable text blob
    searchable = bill.get("title", "").lower()
    for subj in bill.get("subjects", []):
        searchable += " " + subj.lower()

    matched_keywords: list[str] = []
    for kw in keywords:
        if kw.lower() in searchable:
            matched_keywords.append(kw)

    if matched_keywords:
        explanation = (
            f"Bill '{bill.get('title', '')[:80]}' matches sector "
            f"'{sector}' via keywords: {', '.join(matched_keywords[:3])}"
        )
        return True, explanation

    return False, ""


async def find_related_bills(
    member_id: str,
    trade_date: date,
    ticker: str | None,
    sector: str | None,
    window_days: int = 30,
) -> list[dict]:
    """Find bills potentially related to a trade.

    Searches for bills sponsored or cosponsored by the member within
    *window_days* of the trade date, then filters to bills whose subjects
    or titles overlap with the traded company's sector.

    Args:
        member_id: The member's bioguide_id.
        trade_date: Date the trade was executed.
        ticker: Resolved ticker symbol (for logging).
        sector: The company's sector (e.g. "Technology", "Energy").
        window_days: Days before and after the trade to search.

    Returns:
        List of bill dicts augmented with a "relevance" explanation and
        "days_from_trade" field. Sorted by proximity to the trade date.
    """
    if not settings.CONGRESS_API_KEY:
        return []

    date_from = trade_date - timedelta(days=window_days)
    date_to = trade_date + timedelta(days=window_days)

    all_bills = await fetch_member_bills(member_id, date_from, date_to)

    related: list[dict] = []
    for bill in all_bills:
        matches, explanation = _bill_matches_sector(bill, sector)
        if not matches:
            continue

        # Calculate days between trade and bill introduction
        try:
            bill_date = date.fromisoformat(bill["introduced_date"])
            days_from_trade = (bill_date - trade_date).days
        except (ValueError, KeyError):
            days_from_trade = 0

        related.append(
            {
                **bill,
                "relevance": explanation,
                "days_from_trade": days_from_trade,
            }
        )

    # Sort by absolute proximity to trade date
    related.sort(key=lambda b: abs(b.get("days_from_trade", 999)))

    if related:
        logger.info(
            "Found %d bills related to %s/%s trade by %s near %s",
            len(related),
            ticker,
            sector,
            member_id,
            trade_date,
        )

    return related


def score_bill_timing(bills: list[dict], trade_date: date) -> float:
    """Score 0-10 based on how suspicious trade timing is relative to bills.

    Scoring logic:
        - No related bills -> 0.0
        - Bills introduced *after* the trade (member may have had advance
          knowledge of their own upcoming legislation) score higher than
          bills already introduced before the trade.
        - Closer proximity = higher score.
        - Multiple related bills compound the score.

    The scale:
        - Bill introduced 1-3 days after trade:  base 8-10
        - Bill introduced 4-7 days after trade:  base 5-7
        - Bill introduced 8-14 days after trade: base 3-5
        - Bill introduced 15-30 days after trade: base 1-3
        - Bill introduced before the trade:      base 0-2
          (still somewhat relevant -- could indicate ongoing legislative work)
    """
    if not bills:
        return 0.0

    max_single_score = 0.0

    for bill in bills:
        days = bill.get("days_from_trade", 0)

        if days > 0:
            # Bill introduced AFTER the trade -- more suspicious
            if days <= 3:
                single = 10.0
            elif days <= 7:
                single = 7.0
            elif days <= 14:
                single = 5.0
            elif days <= 30:
                single = 3.0
            else:
                single = 1.0
        elif days == 0:
            # Same day -- very suspicious
            single = 9.0
        else:
            # Bill introduced BEFORE the trade
            abs_days = abs(days)
            if abs_days <= 3:
                single = 4.0
            elif abs_days <= 7:
                single = 3.0
            elif abs_days <= 14:
                single = 2.0
            elif abs_days <= 30:
                single = 1.0
            else:
                single = 0.5

        # Sponsored bills are more suspicious than cosponsored
        if bill.get("relationship") == "sponsored":
            single *= 1.0  # full weight
        else:
            single *= 0.7  # cosponsored -- less direct connection

        max_single_score = max(max_single_score, single)

    # Bonus for multiple related bills (capped at +2)
    multi_bonus = min(len(bills) - 1, 4) * 0.5 if len(bills) > 1 else 0.0

    total = min(max_single_score + multi_bonus, 10.0)
    return round(total, 1)
