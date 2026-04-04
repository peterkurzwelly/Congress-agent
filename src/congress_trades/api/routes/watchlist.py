"""Watchlist endpoints — track specific politicians and tickers."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from congress_trades.api.routes.trades import _trade_to_response
from congress_trades.api.schemas import WatchlistCreate, WatchlistItem, WatchlistMatch
from congress_trades.db.models import Trade, Watchlist
from congress_trades.db.session import get_db

router = APIRouter()


@router.get("/", response_model=list[WatchlistItem])
async def list_watchlist(db: AsyncSession = Depends(get_db)) -> list[WatchlistItem]:
    """List all watchlist items."""
    result = await db.execute(select(Watchlist).order_by(Watchlist.created_at.desc()))
    items = result.scalars().all()
    return [WatchlistItem.model_validate(item) for item in items]


@router.post("/", response_model=WatchlistItem, status_code=201)
async def add_watchlist_item(
    payload: WatchlistCreate,
    db: AsyncSession = Depends(get_db),
) -> WatchlistItem:
    """Add a new watchlist item."""
    if payload.watch_type not in ("politician", "ticker"):
        raise HTTPException(
            status_code=422,
            detail="watch_type must be 'politician' or 'ticker'",
        )

    item = Watchlist(
        watch_type=payload.watch_type,
        value=payload.value,
        label=payload.label,
        notify=payload.notify,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return WatchlistItem.model_validate(item)


@router.delete("/{item_id}", status_code=204)
async def remove_watchlist_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove a watchlist item."""
    result = await db.execute(select(Watchlist).where(Watchlist.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Watchlist item not found")
    await db.delete(item)
    await db.commit()


@router.get("/matches", response_model=list[WatchlistMatch])
async def get_watchlist_matches(
    days: int = Query(default=7, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> list[WatchlistMatch]:
    """Get recent trades matching any watchlist item within the last N days."""
    # Fetch all watchlist items
    wl_result = await db.execute(select(Watchlist))
    watchlist_items = wl_result.scalars().all()

    if not watchlist_items:
        return []

    since = date.today() - timedelta(days=days)

    # Separate by type
    politician_ids = [w.value for w in watchlist_items if w.watch_type == "politician"]
    tickers = [w.value.upper() for w in watchlist_items if w.watch_type == "ticker"]

    # Build query for matching trades
    stmt = (
        select(Trade)
        .options(
            selectinload(Trade.member),
            selectinload(Trade.enrichment),
            selectinload(Trade.filing),
        )
        .where(Trade.trade_date >= since)
    )

    # Filter to trades matching any watchlist entry
    from sqlalchemy import or_

    conditions = []
    if politician_ids:
        conditions.append(Trade.member_id.in_(politician_ids))
    if tickers:
        conditions.append(Trade.ticker.in_(tickers))

    if not conditions:
        return []

    stmt = stmt.where(or_(*conditions)).order_by(Trade.trade_date.desc())

    result = await db.execute(stmt)
    trades = result.scalars().unique().all()

    matches: list[WatchlistMatch] = []
    for trade in trades:
        # Find which watchlist items match this trade
        for wl_item in watchlist_items:
            matched = False
            if wl_item.watch_type == "politician" and trade.member_id == wl_item.value:
                matched = True
            elif (
                wl_item.watch_type == "ticker"
                and trade.ticker
                and trade.ticker.upper() == wl_item.value.upper()
            ):
                matched = True

            if matched:
                matches.append(
                    WatchlistMatch(
                        watchlist_id=wl_item.id,
                        watch_type=wl_item.watch_type,
                        value=wl_item.value,
                        label=wl_item.label,
                        trade=_trade_to_response(trade),
                    )
                )

    return matches
