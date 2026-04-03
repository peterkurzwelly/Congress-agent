"""Member endpoints."""

from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from congress_trades.api.schemas import (
    MemberResponse,
    MemberSummary,
    PaginatedResponse,
    TradeWithEnrichment,
    LateFilingInfo,
)
from congress_trades.config import settings
from congress_trades.db.models import EnrichedTrade, Filing, Member, Trade
from congress_trades.db.session import get_db

router = APIRouter()


def _build_member_summary_query():
    """Build query that returns members with aggregate trade stats."""
    return (
        select(
            Member,
            func.count(Trade.trade_id).label("trade_count"),
            func.coalesce(
                func.sum(
                    case(
                        (Trade.trade_type.in_(["Purchase"]), Trade.amount_max),
                        else_=0,
                    )
                ),
                0,
            ).label("total_buy_volume"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            Trade.trade_type.in_(["Sale", "Sale (Full)", "Sale (Partial)"]),
                            Trade.amount_max,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("total_sell_volume"),
            func.max(Trade.trade_date).label("latest_trade_date"),
        )
        .outerjoin(Trade, Member.bioguide_id == Trade.member_id)
        .group_by(Member.bioguide_id)
    )


def _row_to_member_summary(row) -> MemberSummary:
    """Convert a query row to MemberSummary."""
    member = row[0]
    return MemberSummary(
        bioguide_id=member.bioguide_id,
        name=member.name,
        chamber=member.chamber,
        state=member.state,
        district=member.district,
        party=member.party,
        committees=member.committees,
        photo_url=member.photo_url,
        trade_count=row[1] or 0,
        total_buy_volume=row[2] or 0,
        total_sell_volume=row[3] or 0,
        latest_trade_date=row[4],
    )


@router.get("/", response_model=PaginatedResponse)
async def list_members(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=500),
    chamber: Optional[str] = None,
    party: Optional[str] = None,
    state: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all members with trade counts."""
    stmt = _build_member_summary_query()

    if chamber:
        stmt = stmt.where(Member.chamber == chamber)
    if party:
        stmt = stmt.where(Member.party == party)
    if state:
        stmt = stmt.where(Member.state == state.upper())

    # Count
    count_stmt = select(func.count(Member.bioguide_id))
    if chamber:
        count_stmt = count_stmt.where(Member.chamber == chamber)
    if party:
        count_stmt = count_stmt.where(Member.party == party)
    if state:
        count_stmt = count_stmt.where(Member.state == state.upper())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(Member.name).offset(offset).limit(limit)
    result = await db.execute(stmt)
    rows = result.all()

    return PaginatedResponse(
        data=[_row_to_member_summary(r) for r in rows],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/top-traders", response_model=list[MemberSummary])
async def top_traders(
    limit: int = Query(default=20, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Members ranked by trade count."""
    stmt = (
        _build_member_summary_query()
        .having(func.count(Trade.trade_id) > 0)
        .order_by(func.count(Trade.trade_id).desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()

    return [_row_to_member_summary(r) for r in rows]


@router.get("/late-filers", response_model=list[MemberSummary])
async def late_filers(
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Members with trades where disclosure_date > trade_date + 45 days."""
    disclosure_days = settings.STOCK_ACT_DISCLOSURE_DAYS

    # Subquery: members who have at least one late filing
    late_member_ids = (
        select(Trade.member_id)
        .join(Filing, Trade.filing_id == Filing.filing_id)
        .where(
            func.julianday(Filing.disclosure_date) - func.julianday(Trade.trade_date)
            > disclosure_days
        )
        .distinct()
        .scalar_subquery()
    )

    stmt = (
        _build_member_summary_query()
        .where(Member.bioguide_id.in_(late_member_ids))
        .order_by(Member.name)
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()

    return [_row_to_member_summary(r) for r in rows]


@router.get("/{bioguide_id}", response_model=dict)
async def get_member(bioguide_id: str, db: AsyncSession = Depends(get_db)):
    """Single member profile with trade history."""
    # Fetch member
    stmt = select(Member).where(Member.bioguide_id == bioguide_id)
    result = await db.execute(stmt)
    member = result.scalar_one_or_none()

    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    # Fetch trades with enrichment
    trades_stmt = (
        select(Trade)
        .where(Trade.member_id == bioguide_id)
        .options(
            selectinload(Trade.member),
            selectinload(Trade.enrichment),
            selectinload(Trade.filing),
        )
        .order_by(Trade.trade_date.desc())
    )
    trades_result = await db.execute(trades_stmt)
    trades = trades_result.scalars().unique().all()

    # Aggregate stats
    buy_volume = sum(
        t.amount_max for t in trades if t.trade_type == "Purchase"
    )
    sell_volume = sum(
        t.amount_max
        for t in trades
        if t.trade_type in ("Sale", "Sale (Full)", "Sale (Partial)")
    )

    # Build trade responses inline (reuse logic from trades module)
    from congress_trades.api.routes.trades import _trade_to_response

    member_data = MemberResponse.model_validate(member).model_dump()
    member_data["trade_count"] = len(trades)
    member_data["total_buy_volume"] = buy_volume
    member_data["total_sell_volume"] = sell_volume
    member_data["latest_trade_date"] = (
        trades[0].trade_date.isoformat() if trades else None
    )
    member_data["trades"] = [_trade_to_response(t).model_dump() for t in trades]

    return member_data
