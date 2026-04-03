"""Cross-reference Congressional trades with federal contracts from USAspending.gov."""

import logging
from datetime import date, timedelta

import httpx

logger = logging.getLogger(__name__)

# USAspending.gov API base URL
_API_BASE = "https://api.usaspending.gov/api/v2"


async def find_related_contracts(
    ticker: str,
    company_name: str,
    trade_date: date,
    window_days: int = 90,
) -> list[dict]:
    """Search USAspending.gov for federal contracts awarded to *company_name*
    within a window around the trade date.

    Args:
        ticker: Stock ticker (used for logging/context).
        company_name: Company name to search for.
        trade_date: Date the trade was executed.
        window_days: Number of days before/after trade_date to search.

    Returns:
        List of dicts with keys: agency, amount, date, description, award_id.
    """
    if not company_name or not company_name.strip():
        return []

    start_date = trade_date - timedelta(days=window_days)
    end_date = trade_date + timedelta(days=window_days)

    # Clean up company name for search -- remove common suffixes
    search_name = (
        company_name.replace(" Inc", "")
        .replace(" Inc.", "")
        .replace(" Corp", "")
        .replace(" Corp.", "")
        .replace(" Corporation", "")
        .replace(" Company", "")
        .replace(" Co.", "")
        .replace(" Ltd", "")
        .replace(" Ltd.", "")
        .replace(" NV", "")
        .replace(" PLC", "")
        .replace(",", "")
        .strip()
    )

    payload = {
        "filters": {
            "keyword": search_name,
            "time_period": [
                {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                }
            ],
            "award_type_codes": [
                "A",
                "B",
                "C",
                "D",
            ],  # Contract award types
        },
        "fields": [
            "Award ID",
            "Recipient Name",
            "Award Amount",
            "Awarding Agency",
            "Start Date",
            "Description",
        ],
        "page": 1,
        "limit": 25,
        "sort": "Award Amount",
        "order": "desc",
    }

    contracts: list[dict] = []

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{_API_BASE}/search/spending_by_award/",
                json=payload,
                headers={"Content-Type": "application/json"},
            )

            if resp.status_code != 200:
                logger.warning(
                    "USAspending API returned %d for %s (%s)",
                    resp.status_code,
                    company_name,
                    ticker,
                )
                return []

            data = resp.json()
            results = data.get("results", [])

            for award in results:
                contracts.append(
                    {
                        "award_id": award.get("Award ID", ""),
                        "agency": award.get("Awarding Agency", ""),
                        "amount": award.get("Award Amount", 0),
                        "date": award.get("Start Date", ""),
                        "description": award.get("Description", ""),
                        "recipient": award.get("Recipient Name", ""),
                    }
                )

            logger.info(
                "Found %d contracts for %s (%s) near %s",
                len(contracts),
                company_name,
                ticker,
                trade_date,
            )

    except Exception as exc:
        logger.warning(
            "USAspending lookup failed for %s (%s): %s",
            company_name,
            ticker,
            exc,
        )

    return contracts
