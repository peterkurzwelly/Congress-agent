"""Trade endpoints."""


from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from congress_trades.api.schemas import (
    LateFilingInfo,
    PaginatedResponse,
    TradeFilterParams,
    TradeWithEnrichment,
)
from congress_trades.config import settings
from congress_trades.db.models import EnrichedTrade, Filing, Member, Trade
from congress_trades.db.session import get_db

router = APIRouter()


def _trade_to_response(trade: Trade) -> TradeWithEnrichment:
    """Convert a Trade ORM object (with loaded relationships) to TradeWithEnrichment."""
    member = trade.member
    enrichment = trade.enrichment
    filing = trade.filing

    # Calculate late filing info
    late_filing = None
    if filing:
        days_diff = (filing.disclosure_date - trade.trade_date).days
        if days_diff > settings.STOCK_ACT_DISCLOSURE_DAYS:
            days_late = days_diff - settings.STOCK_ACT_DISCLOSURE_DAYS
            late_filing = LateFilingInfo(
                is_late=True,
                days_late=days_late,
                fine_exposure=200,
            )
        else:
            late_filing = LateFilingInfo(is_late=False, days_late=0, fine_exposure=0)

    return TradeWithEnrichment(
        trade_id=trade.trade_id,
        filing_id=trade.filing_id,
        member_id=trade.member_id,
        asset_description=trade.asset_description,
        ticker=trade.ticker,
        asset_type=trade.asset_type,
        trade_type=trade.trade_type,
        trade_date=trade.trade_date,
        owner=trade.owner,
        amount_range=trade.amount_range,
        amount_min=trade.amount_min,
        amount_max=trade.amount_max,
        capital_gains_over_200=trade.capital_gains_over_200,
        comment=trade.comment,
        # Member info
        member_name=member.name if member else None,
        member_party=member.party if member else None,
        member_state=member.state if member else None,
        member_chamber=member.chamber if member else None,
        # Enrichment
        resolved_ticker=enrichment.resolved_ticker if enrichment else None,
        sector=enrichment.sector if enrichment else None,
        industry=enrichment.industry if enrichment else None,
        price_at_trade=enrichment.price_at_trade if enrichment else None,
        price_current=enrichment.price_current if enrichment else None,
        return_1d=enrichment.return_1d if enrichment else None,
        return_7d=enrichment.return_7d if enrichment else None,
        return_30d=enrichment.return_30d if enrichment else None,
        return_90d=enrichment.return_90d if enrichment else None,
        committee_relevance_score=enrichment.committee_relevance_score if enrichment else None,
        anomaly_score=enrichment.anomaly_score if enrichment else None,
        flags=enrichment.flags if enrichment and enrichment.flags else [],
        # Filing context
        filing_date=filing.filing_date if filing else None,
        disclosure_date=filing.disclosure_date if filing else None,
        late_filing=late_filing,
    )


def _build_filtered_query(params: TradeFilterParams):
    """Build a SELECT query with filters applied."""
    stmt = (
        select(Trade)
        .join(Member, Trade.member_id == Member.bioguide_id)
        .outerjoin(EnrichedTrade, Trade.trade_id == EnrichedTrade.trade_id)
        .outerjoin(Filing, Trade.filing_id == Filing.filing_id)
        .options(
            selectinload(Trade.member),
            selectinload(Trade.enrichment),
            selectinload(Trade.filing),
        )
    )

    if params.politician:
        stmt = stmt.where(Member.name.ilike(f"%{params.politician}%"))
    if params.ticker:
        stmt = stmt.where(Trade.ticker == params.ticker.upper())
    if params.chamber:
        stmt = stmt.where(Member.chamber == params.chamber.value)
    if params.party:
        stmt = stmt.where(Member.party == params.party)
    if params.state:
        stmt = stmt.where(Member.state == params.state.upper())
    if params.trade_type:
        stmt = stmt.where(Trade.trade_type == params.trade_type)
    if params.asset_type:
        stmt = stmt.where(Trade.asset_type == params.asset_type)
    if params.min_amount is not None:
        stmt = stmt.where(Trade.amount_max >= params.min_amount)
    if params.max_amount is not None:
        stmt = stmt.where(Trade.amount_min <= params.max_amount)
    if params.date_from:
        stmt = stmt.where(Trade.trade_date >= params.date_from)
    if params.date_to:
        stmt = stmt.where(Trade.trade_date <= params.date_to)
    if params.min_anomaly_score is not None:
        stmt = stmt.where(EnrichedTrade.anomaly_score >= params.min_anomaly_score)

    # Sorting
    sort_column_map = {
        "trade_date": Trade.trade_date,
        "amount_min": Trade.amount_min,
        "amount_max": Trade.amount_max,
        "anomaly_score": EnrichedTrade.anomaly_score,
        "ticker": Trade.ticker,
    }
    sort_col = sort_column_map.get(params.sort_by, Trade.trade_date)
    if params.sort_order == "asc":
        stmt = stmt.order_by(sort_col.asc())
    else:
        stmt = stmt.order_by(sort_col.desc())

    return stmt


@router.get("/", response_model=PaginatedResponse)
async def list_trades(
    politician: str | None = None,
    ticker: str | None = None,
    chamber: str | None = None,
    party: str | None = None,
    state: str | None = None,
    trade_type: str | None = None,
    asset_type: str | None = None,
    min_amount: int | None = None,
    max_amount: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    min_anomaly_score: float | None = None,
    sort_by: str = "trade_date",
    sort_order: str = "desc",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=500),
    db: AsyncSession = Depends(get_db),
):
    """List trades with filtering, sorting, and pagination."""
    from datetime import date as date_type

    params = TradeFilterParams(
        politician=politician,
        ticker=ticker,
        chamber=chamber,
        party=party,
        state=state,
        trade_type=trade_type,
        asset_type=asset_type,
        min_amount=min_amount,
        max_amount=max_amount,
        date_from=date_type.fromisoformat(date_from) if date_from else None,
        date_to=date_type.fromisoformat(date_to) if date_to else None,
        min_anomaly_score=min_anomaly_score,
        sort_by=sort_by,
        sort_order=sort_order,
        offset=offset,
        limit=limit,
    )

    # Count total matching
    count_stmt = (
        select(func.count(Trade.trade_id))
        .join(Member, Trade.member_id == Member.bioguide_id)
        .outerjoin(EnrichedTrade, Trade.trade_id == EnrichedTrade.trade_id)
        .outerjoin(Filing, Trade.filing_id == Filing.filing_id)
    )
    # Apply same filters to count
    if params.politician:
        count_stmt = count_stmt.where(Member.name.ilike(f"%{params.politician}%"))
    if params.ticker:
        count_stmt = count_stmt.where(Trade.ticker == params.ticker.upper())
    if params.chamber:
        count_stmt = count_stmt.where(Member.chamber == params.chamber.value)
    if params.party:
        count_stmt = count_stmt.where(Member.party == params.party)
    if params.state:
        count_stmt = count_stmt.where(Member.state == params.state.upper())
    if params.trade_type:
        count_stmt = count_stmt.where(Trade.trade_type == params.trade_type)
    if params.asset_type:
        count_stmt = count_stmt.where(Trade.asset_type == params.asset_type)
    if params.min_amount is not None:
        count_stmt = count_stmt.where(Trade.amount_max >= params.min_amount)
    if params.max_amount is not None:
        count_stmt = count_stmt.where(Trade.amount_min <= params.max_amount)
    if params.date_from:
        count_stmt = count_stmt.where(Trade.trade_date >= params.date_from)
    if params.date_to:
        count_stmt = count_stmt.where(Trade.trade_date <= params.date_to)
    if params.min_anomaly_score is not None:
        count_stmt = count_stmt.where(EnrichedTrade.anomaly_score >= params.min_anomaly_score)

    total = (await db.execute(count_stmt)).scalar_one()

    # Fetch page
    stmt = _build_filtered_query(params).offset(params.offset).limit(params.limit)
    result = await db.execute(stmt)
    trades = result.scalars().unique().all()

    return PaginatedResponse(
        data=[_trade_to_response(t) for t in trades],
        total=total,
        offset=params.offset,
        limit=params.limit,
    )


@router.get("/recent", response_model=PaginatedResponse)
async def recent_trades(db: AsyncSession = Depends(get_db)):
    """Return the 50 most recent trades."""
    count_stmt = select(func.count(Trade.trade_id))
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(Trade)
        .options(
            selectinload(Trade.member),
            selectinload(Trade.enrichment),
            selectinload(Trade.filing),
        )
        .order_by(Trade.trade_date.desc())
        .limit(50)
    )
    result = await db.execute(stmt)
    trades = result.scalars().unique().all()

    return PaginatedResponse(
        data=[_trade_to_response(t) for t in trades],
        total=total,
        offset=0,
        limit=50,
    )


@router.get("/anomalies", response_model=PaginatedResponse)
async def anomalous_trades(
    threshold: float = Query(default=50.0, ge=0, le=100),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Return trades with anomaly_score above the given threshold."""
    count_stmt = (
        select(func.count(Trade.trade_id))
        .join(EnrichedTrade, Trade.trade_id == EnrichedTrade.trade_id)
        .where(EnrichedTrade.anomaly_score >= threshold)
    )
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(Trade)
        .join(EnrichedTrade, Trade.trade_id == EnrichedTrade.trade_id)
        .where(EnrichedTrade.anomaly_score >= threshold)
        .options(
            selectinload(Trade.member),
            selectinload(Trade.enrichment),
            selectinload(Trade.filing),
        )
        .order_by(EnrichedTrade.anomaly_score.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    trades = result.scalars().unique().all()

    return PaginatedResponse(
        data=[_trade_to_response(t) for t in trades],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/{trade_id}", response_model=TradeWithEnrichment)
async def get_trade(trade_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single trade with full enrichment data."""
    stmt = (
        select(Trade)
        .where(Trade.trade_id == trade_id)
        .options(
            selectinload(Trade.member),
            selectinload(Trade.enrichment),
            selectinload(Trade.filing),
        )
    )
    result = await db.execute(stmt)
    trade = result.scalar_one_or_none()

    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    return _trade_to_response(trade)
