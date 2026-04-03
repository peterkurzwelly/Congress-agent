"""Analytics endpoints."""

from datetime import date as date_type
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from congress_trades.api.schemas import (
    AggregateStats,
    SectorFlow,
    TimelinePoint,
)
from congress_trades.config import settings
from congress_trades.db.models import EnrichedTrade, Filing, Member, Trade
from congress_trades.db.session import get_db

router = APIRouter()


@router.get("/stats", response_model=AggregateStats)
async def aggregate_stats(db: AsyncSession = Depends(get_db)):
    """Dashboard aggregate statistics."""
    # Total trades
    total = (await db.execute(select(func.count(Trade.trade_id)))).scalar_one()

    # Buys
    total_buys = (
        await db.execute(
            select(func.count(Trade.trade_id)).where(Trade.trade_type == "Purchase")
        )
    ).scalar_one()

    # Sells
    total_sells = (
        await db.execute(
            select(func.count(Trade.trade_id)).where(
                Trade.trade_type.in_(["Sale", "Sale (Full)", "Sale (Partial)"])
            )
        )
    ).scalar_one()

    # Unique tickers
    unique_tickers = (
        await db.execute(
            select(func.count(func.distinct(Trade.ticker))).where(
                Trade.ticker.isnot(None)
            )
        )
    ).scalar_one()

    # Unique politicians
    unique_politicians = (
        await db.execute(select(func.count(func.distinct(Trade.member_id))))
    ).scalar_one()

    # Average anomaly score
    avg_anomaly = (
        await db.execute(select(func.avg(EnrichedTrade.anomaly_score)))
    ).scalar_one()

    # Late filings count
    disclosure_days = settings.STOCK_ACT_DISCLOSURE_DAYS
    late_count = (
        await db.execute(
            select(func.count(Trade.trade_id))
            .join(Filing, Trade.filing_id == Filing.filing_id)
            .where(
                func.julianday(Filing.disclosure_date) - func.julianday(Trade.trade_date)
                > disclosure_days
            )
        )
    ).scalar_one()

    return AggregateStats(
        total_trades=total,
        total_buys=total_buys,
        total_sells=total_sells,
        unique_tickers=unique_tickers,
        unique_politicians=unique_politicians,
        avg_anomaly_score=round(avg_anomaly, 2) if avg_anomaly is not None else None,
        late_filings_count=late_count,
    )


@router.get("/sector-flows", response_model=list[SectorFlow])
async def sector_flows(db: AsyncSession = Depends(get_db)):
    """Net buy/sell volume by sector from enriched trades."""
    stmt = (
        select(
            EnrichedTrade.sector,
            func.sum(
                case(
                    (Trade.trade_type == "Purchase", Trade.amount_max),
                    else_=0,
                )
            ).label("buy_volume"),
            func.sum(
                case(
                    (
                        Trade.trade_type.in_(["Sale", "Sale (Full)", "Sale (Partial)"]),
                        Trade.amount_max,
                    ),
                    else_=0,
                )
            ).label("sell_volume"),
            func.sum(
                case(
                    (Trade.trade_type == "Purchase", 1),
                    else_=0,
                )
            ).label("buy_count"),
            func.sum(
                case(
                    (
                        Trade.trade_type.in_(["Sale", "Sale (Full)", "Sale (Partial)"]),
                        1,
                    ),
                    else_=0,
                )
            ).label("sell_count"),
        )
        .join(Trade, EnrichedTrade.trade_id == Trade.trade_id)
        .where(EnrichedTrade.sector.isnot(None))
        .group_by(EnrichedTrade.sector)
        .order_by(func.count(Trade.trade_id).desc())
    )

    result = await db.execute(stmt)
    rows = result.all()

    return [
        SectorFlow(
            sector=row[0],
            net_buy_volume=(row[1] or 0) - (row[2] or 0),
            buy_count=row[3] or 0,
            sell_count=row[4] or 0,
        )
        for row in rows
    ]


@router.get("/timeline", response_model=list[TimelinePoint])
async def timeline(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Trade volume aggregated by date."""
    stmt = select(
        Trade.trade_date,
        func.sum(
            case(
                (Trade.trade_type == "Purchase", 1),
                else_=0,
            )
        ).label("buy_count"),
        func.sum(
            case(
                (
                    Trade.trade_type.in_(["Sale", "Sale (Full)", "Sale (Partial)"]),
                    1,
                ),
                else_=0,
            )
        ).label("sell_count"),
        func.sum(Trade.amount_max).label("total_volume"),
    ).group_by(Trade.trade_date)

    if date_from:
        stmt = stmt.where(Trade.trade_date >= date_type.fromisoformat(date_from))
    if date_to:
        stmt = stmt.where(Trade.trade_date <= date_type.fromisoformat(date_to))

    stmt = stmt.order_by(Trade.trade_date)

    result = await db.execute(stmt)
    rows = result.all()

    return [
        TimelinePoint(
            date=row[0],
            buy_count=row[1] or 0,
            sell_count=row[2] or 0,
            total_volume=row[3] or 0,
        )
        for row in rows
    ]


@router.get("/concurrent", response_model=list[dict])
async def concurrent_trades(
    days_window: int = Query(default=7, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
):
    """Find stocks traded by 2+ different members within a given time window.

    Returns groups of trades on the same ticker where multiple members traded
    within `days_window` days of each other.
    """
    # Alias for self-join
    from sqlalchemy.orm import aliased

    T1 = aliased(Trade, name="t1")
    T2 = aliased(Trade, name="t2")

    # Find ticker + member pairs where multiple distinct members traded the
    # same ticker within the window
    stmt = (
        select(
            T1.ticker,
            func.count(func.distinct(T1.member_id)).label("member_count"),
            func.count(T1.trade_id).label("trade_count"),
            func.min(T1.trade_date).label("first_trade"),
            func.max(T1.trade_date).label("last_trade"),
        )
        .where(T1.ticker.isnot(None))
        .group_by(T1.ticker)
        .having(func.count(func.distinct(T1.member_id)) >= 2)
    )

    # We filter for tickers where the date spread is within the window
    # by using a subquery approach: first find tickers with 2+ members,
    # then check date proximity
    result = await db.execute(stmt)
    candidate_rows = result.all()

    concurrent_results = []

    for row in candidate_rows:
        ticker = row[0]

        # Fetch all trades for this ticker
        trades_stmt = (
            select(
                Trade.trade_id,
                Trade.member_id,
                Trade.trade_date,
                Trade.trade_type,
                Trade.amount_range,
                Member.name,
            )
            .join(Member, Trade.member_id == Member.bioguide_id)
            .where(Trade.ticker == ticker)
            .order_by(Trade.trade_date)
        )
        trades_result = await db.execute(trades_stmt)
        trades = trades_result.all()

        # Sliding window: find clusters where trades from different members
        # fall within days_window
        if len(trades) < 2:
            continue

        # Group trades into clusters within the time window
        clusters = []
        current_cluster = [trades[0]]

        for t in trades[1:]:
            if (t[2] - current_cluster[0][2]).days <= days_window:
                current_cluster.append(t)
            else:
                if len(set(tr[1] for tr in current_cluster)) >= 2:
                    clusters.append(current_cluster)
                current_cluster = [t]

        # Check last cluster
        if len(set(tr[1] for tr in current_cluster)) >= 2:
            clusters.append(current_cluster)

        for cluster in clusters:
            unique_members = set(tr[1] for tr in cluster)
            concurrent_results.append(
                {
                    "ticker": ticker,
                    "member_count": len(unique_members),
                    "trade_count": len(cluster),
                    "date_range": {
                        "from": cluster[0][2].isoformat(),
                        "to": cluster[-1][2].isoformat(),
                    },
                    "trades": [
                        {
                            "trade_id": tr[0],
                            "member_id": tr[1],
                            "member_name": tr[5],
                            "trade_date": tr[2].isoformat(),
                            "trade_type": tr[3],
                            "amount_range": tr[4],
                        }
                        for tr in cluster
                    ],
                }
            )

    # Sort by member count descending
    concurrent_results.sort(key=lambda x: x["member_count"], reverse=True)

    return concurrent_results
