"""Score Congressional trades 0-100 on suspiciousness and orchestrate enrichment."""

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from congress_trades.api.schemas import EnrichmentData, LateFilingInfo
from congress_trades.config import settings
from congress_trades.db.models import EnrichedTrade, Filing, Member, Trade
from congress_trades.enrichment.bill_correlator import find_related_bills, score_bill_timing
from congress_trades.enrichment.committee_mapper import (
    fetch_member_committees,
    get_committee_relevance,
)
from congress_trades.enrichment.price_fetcher import fetch_trade_returns
from congress_trades.enrichment.ticker_resolver import resolve_ticker

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Late-filing detection
# ---------------------------------------------------------------------------


def check_late_filing(trade_date: date, disclosure_date: date) -> LateFilingInfo:
    """Check whether a filing violates the STOCK Act's 45-day disclosure rule.

    The STOCK Act requires disclosure within 45 days of the transaction.
    Each late filing carries a $200 fine.
    """
    delta = (disclosure_date - trade_date).days
    threshold = settings.STOCK_ACT_DISCLOSURE_DAYS

    if delta > threshold:
        days_late = delta - threshold
        return LateFilingInfo(
            is_late=True,
            days_late=days_late,
            fine_exposure=200,  # $200 per late filing
        )

    return LateFilingInfo(is_late=False, days_late=0, fine_exposure=0)


# ---------------------------------------------------------------------------
# Individual scoring factors
# ---------------------------------------------------------------------------


def _score_committee_overlap(relevance: float) -> float:
    """Committee overlap score (weight: 25%). Maps 0.0-1.0 relevance to 0-25."""
    return relevance * 25.0


def _score_disclosure_delay(trade_date: date, disclosure_date: date) -> float:
    """Disclosure delay score (weight: 20%). Longer delays = more suspicious."""
    days = (disclosure_date - trade_date).days
    if days <= 30:
        return 0.0
    elif days <= 45:
        # Approaching the limit -- linear ramp 0-10
        return ((days - 30) / 15.0) * 10.0
    else:
        # Past STOCK Act limit -- high score
        return min(10.0 + (days - 45) * 0.5, 20.0)


def _score_trade_size(amount_min: int, amount_max: int) -> float:
    """Trade size score (weight: 15%). Larger trades are more notable."""
    midpoint = (amount_min + amount_max) / 2.0
    if midpoint < 15_000:
        return 0.0
    elif midpoint < 50_000:
        return 3.0
    elif midpoint < 100_000:
        return 6.0
    elif midpoint < 250_000:
        return 9.0
    elif midpoint < 500_000:
        return 12.0
    else:
        return 15.0


def _score_price_movement(returns: dict) -> float:
    """Price movement score (weight: 15%). Large post-trade returns are suspicious."""
    score = 0.0

    # Check 7-day and 30-day returns for significant moves
    r7 = returns.get("return_7d")
    r30 = returns.get("return_30d")
    r90 = returns.get("return_90d")

    if r7 is not None and abs(r7) > 5:
        score += min(abs(r7) / 5.0 * 3.0, 5.0)
    if r30 is not None and abs(r30) > 10:
        score += min(abs(r30) / 10.0 * 3.0, 5.0)
    if r90 is not None and abs(r90) > 15:
        score += min(abs(r90) / 15.0 * 3.0, 5.0)

    return min(score, 15.0)


async def _score_concurrent_trades(
    ticker: str, trade_date: date, member_id: str, session: AsyncSession
) -> float:
    """Concurrent trades score (weight: 10%). Multiple members trading same stock = suspicious."""
    window_start = trade_date - timedelta(days=7)
    window_end = trade_date + timedelta(days=7)

    stmt = (
        select(func.count(func.distinct(Trade.member_id)))
        .where(Trade.ticker == ticker)
        .where(Trade.trade_date.between(window_start, window_end))
        .where(Trade.member_id != member_id)
    )
    result = await session.execute(stmt)
    other_members = result.scalar() or 0

    if other_members == 0:
        return 0.0
    elif other_members <= 2:
        return 3.0
    elif other_members <= 5:
        return 6.0
    else:
        return 10.0


async def _score_trade_timing(
    member_id: str,
    trade_date: date,
    ticker: str | None,
    sector: str | None,
) -> float:
    """Trade timing score (weight: 10%). Cross-references trade with bill activity.

    Uses the bill correlator to find bills sponsored/cosponsored by the member
    near the trade date, then scores based on timing suspiciousness.
    Returns 0.0 gracefully when the Congress API key is not configured.
    """
    try:
        related_bills = await find_related_bills(
            member_id=member_id,
            trade_date=trade_date,
            ticker=ticker,
            sector=sector,
            window_days=30,
        )
        return score_bill_timing(related_bills, trade_date)
    except Exception as exc:
        logger.warning("Bill timing scoring failed for %s: %s", member_id, exc)
        return 0.0


async def _score_historical_pattern(
    member_id: str, ticker: str, amount_min: int, session: AsyncSession
) -> float:
    """Historical pattern score (weight: 5%). Deviation from member's typical behavior."""
    # Calculate the member's average trade size
    stmt = select(func.avg(Trade.amount_min)).where(Trade.member_id == member_id)
    result = await session.execute(stmt)
    avg_amount = result.scalar()

    if avg_amount is None or avg_amount == 0:
        return 0.0

    # Score based on how much this trade deviates from the member's average
    ratio = amount_min / avg_amount
    if ratio > 5.0:
        return 5.0
    elif ratio > 3.0:
        return 3.0
    elif ratio > 2.0:
        return 1.5
    return 0.0


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------


async def score_trade(
    trade: Trade,
    member: Member,
    filing: Filing,
    session: AsyncSession,
) -> EnrichmentData:
    """Score a single trade on suspiciousness (0-100).

    Scoring factors (weighted):
        - Committee overlap:   25%
        - Disclosure delay:    20%
        - Trade size:          15%
        - Price movement:      15%
        - Concurrent trades:   10%
        - Trade timing:        10%
        - Historical pattern:   5%
    """
    flags: list[str] = []

    # --- Resolve ticker ---
    ticker = await resolve_ticker(trade.asset_description, trade.ticker)

    # --- Fetch price data ---
    price_data: dict = {}
    sector: str | None = None
    industry: str | None = None
    if ticker:
        price_data = await fetch_trade_returns(ticker, trade.trade_date)
        sector = price_data.get("sector")
        industry = price_data.get("industry")

    # --- Committee relevance ---
    committees = member.committees
    if not committees or not committees.get("committees"):
        committees = await fetch_member_committees(member.bioguide_id)
    committee_relevance = get_committee_relevance(committees, ticker, sector)
    if committee_relevance > 0.5:
        flags.append("committee_overlap")

    # --- Late filing check ---
    late_info = check_late_filing(trade.trade_date, filing.disclosure_date)
    if late_info.is_late:
        flags.append("late_filing")

    # --- Large trade check ---
    midpoint = (trade.amount_min + trade.amount_max) / 2
    if midpoint >= settings.LARGE_TRADE_THRESHOLD:
        flags.append("large_trade")

    # --- Compute individual scores ---
    s_committee = _score_committee_overlap(committee_relevance)
    s_delay = _score_disclosure_delay(trade.trade_date, filing.disclosure_date)
    s_size = _score_trade_size(trade.amount_min, trade.amount_max)
    s_price = _score_price_movement(price_data)
    s_concurrent = 0.0
    if ticker:
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
        trade.member_id, ticker or "", trade.amount_min, session
    )

    total_score = (
        s_committee + s_delay + s_size + s_price + s_concurrent + s_timing + s_historical
    )
    total_score = round(min(max(total_score, 0.0), 100.0), 1)

    if total_score >= settings.ANOMALY_ALERT_THRESHOLD:
        flags.append("high_anomaly")

    return EnrichmentData(
        resolved_ticker=ticker,
        sector=sector,
        industry=industry,
        price_at_trade=price_data.get("price_at_trade"),
        price_current=price_data.get("price_current"),
        return_1d=price_data.get("return_1d"),
        return_7d=price_data.get("return_7d"),
        return_30d=price_data.get("return_30d"),
        return_90d=price_data.get("return_90d"),
        committee_relevance_score=round(committee_relevance, 3),
        anomaly_score=total_score,
        flags=flags,
    )


# ---------------------------------------------------------------------------
# Orchestrator: enrich + score + persist
# ---------------------------------------------------------------------------


async def enrich_and_score(trade_id: int, session: AsyncSession) -> EnrichedTrade:
    """Full enrichment pipeline for a single trade.

    1. Load trade, member, and filing from DB.
    2. Resolve ticker.
    3. Fetch prices and sector info.
    4. Score anomaly.
    5. Write EnrichedTrade row.

    Returns the persisted EnrichedTrade object.
    """
    # Load trade with relationships
    stmt = select(Trade).where(Trade.trade_id == trade_id)
    result = await session.execute(stmt)
    trade = result.scalar_one_or_none()
    if trade is None:
        raise ValueError(f"Trade {trade_id} not found")

    # Load member
    stmt_m = select(Member).where(Member.bioguide_id == trade.member_id)
    result_m = await session.execute(stmt_m)
    member = result_m.scalar_one_or_none()
    if member is None:
        raise ValueError(f"Member {trade.member_id} not found")

    # Load filing
    stmt_f = select(Filing).where(Filing.filing_id == trade.filing_id)
    result_f = await session.execute(stmt_f)
    filing = result_f.scalar_one_or_none()
    if filing is None:
        raise ValueError(f"Filing {trade.filing_id} not found")

    # Run scoring
    enrichment_data = await score_trade(trade, member, filing, session)

    # Check for existing enrichment row
    stmt_e = select(EnrichedTrade).where(EnrichedTrade.trade_id == trade_id)
    result_e = await session.execute(stmt_e)
    enriched = result_e.scalar_one_or_none()

    if enriched is None:
        enriched = EnrichedTrade(trade_id=trade_id)
        session.add(enriched)

    # Update fields
    enriched.resolved_ticker = enrichment_data.resolved_ticker
    enriched.sector = enrichment_data.sector
    enriched.industry = enrichment_data.industry
    enriched.price_at_trade = enrichment_data.price_at_trade
    enriched.price_current = enrichment_data.price_current
    enriched.return_1d = enrichment_data.return_1d
    enriched.return_7d = enrichment_data.return_7d
    enriched.return_30d = enrichment_data.return_30d
    enriched.return_90d = enrichment_data.return_90d
    enriched.committee_relevance_score = enrichment_data.committee_relevance_score
    enriched.anomaly_score = enrichment_data.anomaly_score
    enriched.flags = enrichment_data.flags
    enriched.scored_at = datetime.utcnow()

    # Also update the trade's resolved ticker if it was missing
    if enrichment_data.resolved_ticker and not trade.ticker:
        trade.ticker = enrichment_data.resolved_ticker

    await session.flush()

    logger.info(
        "Enriched trade %d: ticker=%s score=%.1f flags=%s",
        trade_id,
        enriched.resolved_ticker,
        enriched.anomaly_score or 0,
        enriched.flags,
    )

    return enriched
