"""Analytics endpoints."""

from datetime import date as date_type

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from congress_trades.api.schemas import (
    AggregateStats,
    DisclosureDelayBucket,
    MemberPerformance,
    PartyComparison,
    SectorFlow,
    TimelinePoint,
    TopTicker,
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
    date_from: str | None = None,
    date_to: str | None = None,
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

    t1 = aliased(Trade, name="t1")  # noqa: N806 — alias intentionally short

    # Find ticker + member pairs where multiple distinct members traded the
    # same ticker within the window
    stmt = (
        select(
            t1.ticker,
            func.count(func.distinct(t1.member_id)).label("member_count"),
            func.count(t1.trade_id).label("trade_count"),
            func.min(t1.trade_date).label("first_trade"),
            func.max(t1.trade_date).label("last_trade"),
        )
        .where(t1.ticker.isnot(None))
        .group_by(t1.ticker)
        .having(func.count(func.distinct(t1.member_id)) >= 2)
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


@router.get("/party-comparison", response_model=list[PartyComparison])
async def party_comparison(db: AsyncSession = Depends(get_db)):
    """Compare trading activity aggregated by political party."""
    stmt = (
        select(
            Member.party,
            func.count(Trade.trade_id).label("total_trades"),
            func.sum(
                case(
                    (Trade.trade_type == "Purchase", Trade.amount_max),
                    else_=0,
                )
            ).label("total_buy_volume"),
            func.sum(
                case(
                    (
                        Trade.trade_type.in_(["Sale", "Sale (Full)", "Sale (Partial)"]),
                        Trade.amount_max,
                    ),
                    else_=0,
                )
            ).label("total_sell_volume"),
            func.avg(EnrichedTrade.anomaly_score).label("avg_anomaly_score"),
            func.count(func.distinct(Trade.ticker)).label("unique_tickers"),
        )
        .join(Member, Trade.member_id == Member.bioguide_id)
        .outerjoin(EnrichedTrade, Trade.trade_id == EnrichedTrade.trade_id)
        .where(Member.party.isnot(None))
        .group_by(Member.party)
        .order_by(func.count(Trade.trade_id).desc())
    )

    result = await db.execute(stmt)
    rows = result.all()

    return [
        PartyComparison(
            party=row[0],
            total_trades=row[1] or 0,
            total_buy_volume=row[2] or 0,
            total_sell_volume=row[3] or 0,
            avg_anomaly_score=round(row[4], 2) if row[4] is not None else None,
            unique_tickers=row[5] or 0,
        )
        for row in rows
    ]


@router.get("/top-tickers", response_model=list[TopTicker])
async def top_tickers(
    limit: int = Query(default=20, ge=1, le=200),
    days: int = Query(default=90, ge=1, le=3650),
    db: AsyncSession = Depends(get_db),
):
    """Most traded tickers with aggregate stats over a trailing window."""
    from datetime import date as date_type
    from datetime import timedelta

    cutoff = date_type.today() - timedelta(days=days)

    stmt = (
        select(
            Trade.ticker,
            func.count(Trade.trade_id).label("trade_count"),
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
            func.count(func.distinct(Trade.member_id)).label("unique_members"),
            func.avg(EnrichedTrade.anomaly_score).label("avg_anomaly_score"),
        )
        .outerjoin(EnrichedTrade, Trade.trade_id == EnrichedTrade.trade_id)
        .where(Trade.ticker.isnot(None))
        .where(Trade.trade_date >= cutoff)
        .group_by(Trade.ticker)
        .order_by(func.count(Trade.trade_id).desc())
        .limit(limit)
    )

    result = await db.execute(stmt)
    rows = result.all()

    return [
        TopTicker(
            ticker=row[0],
            trade_count=row[1] or 0,
            buy_count=row[2] or 0,
            sell_count=row[3] or 0,
            unique_members=row[4] or 0,
            avg_anomaly_score=round(row[5], 2) if row[5] is not None else None,
        )
        for row in rows
    ]


@router.get("/disclosure-delays", response_model=list[DisclosureDelayBucket])
async def disclosure_delays(db: AsyncSession = Depends(get_db)):
    """Histogram of disclosure delay distribution (days between trade and disclosure)."""
    stmt = (
        select(
            Trade.trade_id,
            (
                func.julianday(Filing.disclosure_date) - func.julianday(Trade.trade_date)
            ).label("delay_days"),
        )
        .join(Filing, Trade.filing_id == Filing.filing_id)
        .where(Filing.disclosure_date.isnot(None))
        .where(Trade.trade_date.isnot(None))
    )

    result = await db.execute(stmt)
    rows = result.all()

    buckets: dict[str, int] = {
        "0-7 days": 0,
        "8-14 days": 0,
        "15-30 days": 0,
        "31-45 days": 0,
        "45+ days": 0,
    }

    for row in rows:
        delay = row[1]
        if delay is None:
            continue
        delay = max(0, int(delay))
        if delay <= 7:
            buckets["0-7 days"] += 1
        elif delay <= 14:
            buckets["8-14 days"] += 1
        elif delay <= 30:
            buckets["15-30 days"] += 1
        elif delay <= 45:
            buckets["31-45 days"] += 1
        else:
            buckets["45+ days"] += 1

    return [
        DisclosureDelayBucket(delay_bucket=bucket, count=count)
        for bucket, count in buckets.items()
    ]


@router.get("/member-performance", response_model=list[MemberPerformance])
async def member_performance(
    limit: int = Query(default=20, ge=1, le=200),
    min_trades: int = Query(default=3, ge=1),
    db: AsyncSession = Depends(get_db),
):
    """Members ranked by average anomaly score (highest first)."""
    stmt = (
        select(
            Member.name,
            Member.bioguide_id,
            Member.party,
            func.avg(EnrichedTrade.anomaly_score).label("avg_anomaly_score"),
            func.count(Trade.trade_id).label("trade_count"),
            func.sum(
                case(
                    (EnrichedTrade.anomaly_score >= 70, 1),
                    else_=0,
                )
            ).label("flagged_trades_count"),
        )
        .join(Trade, Member.bioguide_id == Trade.member_id)
        .join(EnrichedTrade, Trade.trade_id == EnrichedTrade.trade_id)
        .group_by(Member.bioguide_id, Member.name, Member.party)
        .having(func.count(Trade.trade_id) >= min_trades)
        .order_by(func.avg(EnrichedTrade.anomaly_score).desc())
        .limit(limit)
    )

    result = await db.execute(stmt)
    rows = result.all()

    return [
        MemberPerformance(
            name=row[0],
            bioguide_id=row[1],
            party=row[2] or "Unknown",
            avg_anomaly_score=round(row[3], 2) if row[3] is not None else None,
            trade_count=row[4] or 0,
            flagged_trades_count=row[5] or 0,
        )
        for row in rows
    ]
