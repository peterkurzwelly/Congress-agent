"""Export endpoints — CSV and JSON downloads for trades, members, and analytics."""

import csv
import io
import json
from datetime import date as date_type
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from congress_trades.api.routes.trades import _build_filtered_query, _trade_to_response
from congress_trades.api.schemas import TradeFilterParams
from congress_trades.db.models import EnrichedTrade, Member, Trade
from congress_trades.db.session import get_db

router = APIRouter()

# CSV field names for the trades export
_TRADE_FIELDS = [
    "trade_id",
    "filing_id",
    "member_id",
    "member_name",
    "member_party",
    "member_state",
    "member_chamber",
    "asset_description",
    "ticker",
    "resolved_ticker",
    "asset_type",
    "trade_type",
    "trade_date",
    "owner",
    "amount_range",
    "amount_min",
    "amount_max",
    "capital_gains_over_200",
    "comment",
    "sector",
    "industry",
    "price_at_trade",
    "price_current",
    "return_1d",
    "return_7d",
    "return_30d",
    "return_90d",
    "committee_relevance_score",
    "anomaly_score",
    "flags",
    "filing_date",
    "disclosure_date",
]


def _parse_filter_params(
    politician: str | None,
    ticker: str | None,
    chamber: str | None,
    party: str | None,
    state: str | None,
    trade_type: str | None,
    asset_type: str | None,
    min_amount: int | None,
    max_amount: int | None,
    date_from: str | None,
    date_to: str | None,
    min_anomaly_score: float | None,
    sort_by: str,
    sort_order: str,
) -> TradeFilterParams:
    """Build a TradeFilterParams from raw query strings."""
    return TradeFilterParams(
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
        offset=0,
        limit=500,  # exports ignore pagination limit
    )


async def _fetch_all_trades(params: TradeFilterParams, db: AsyncSession):
    """Fetch all trades matching the filter (no pagination cap)."""
    stmt = _build_filtered_query(params)
    result = await db.execute(stmt)
    return result.scalars().unique().all()


@router.get("/trades/csv")
async def export_trades_csv(
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
    db: AsyncSession = Depends(get_db),
):
    """Export filtered trades as a CSV download."""
    params = _parse_filter_params(
        politician, ticker, chamber, party, state, trade_type, asset_type,
        min_amount, max_amount, date_from, date_to, min_anomaly_score,
        sort_by, sort_order,
    )
    trades = await _fetch_all_trades(params, db)

    def generate():
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=_TRADE_FIELDS, extrasaction="ignore")
        writer.writeheader()
        yield buf.getvalue()

        for trade in trades:
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=_TRADE_FIELDS, extrasaction="ignore")
            t = _trade_to_response(trade)
            row = t.model_dump()
            # Flatten nested late_filing
            row.pop("late_filing", None)
            # Serialize lists as pipe-separated strings
            row["flags"] = "|".join(row.get("flags") or [])
            writer.writerow(row)
            yield buf.getvalue()

    today = date_type.today().isoformat()
    filename = f"congress_trades_{today}.csv"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(generate(), media_type="text/csv", headers=headers)


@router.get("/trades/json")
async def export_trades_json(
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
    db: AsyncSession = Depends(get_db),
):
    """Export filtered trades as a JSON download."""
    params = _parse_filter_params(
        politician, ticker, chamber, party, state, trade_type, asset_type,
        min_amount, max_amount, date_from, date_to, min_anomaly_score,
        sort_by, sort_order,
    )
    trades = await _fetch_all_trades(params, db)
    records = [_trade_to_response(t).model_dump(mode="json") for t in trades]

    today = date_type.today().isoformat()
    filename = f"congress_trades_{today}.json"

    def generate():
        payload = {
            "exported_at": datetime.utcnow().isoformat(),
            "count": len(records),
            "trades": records,
        }
        yield json.dumps(payload, default=str)

    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(generate(), media_type="application/json", headers=headers)


@router.get("/members/csv")
async def export_members_csv(
    chamber: str | None = None,
    party: str | None = None,
    state: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Export member list with trade counts as a CSV download."""
    stmt = (
        select(
            Member,
            func.count(Trade.trade_id).label("trade_count"),
            func.coalesce(
                func.sum(
                    case((Trade.trade_type.in_(["Purchase"]), Trade.amount_max), else_=0)
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

    if chamber:
        stmt = stmt.where(Member.chamber == chamber)
    if party:
        stmt = stmt.where(Member.party == party)
    if state:
        stmt = stmt.where(Member.state == state.upper())

    stmt = stmt.order_by(Member.name)
    result = await db.execute(stmt)
    rows = result.all()

    fields = [
        "bioguide_id", "name", "chamber", "state", "district", "party",
        "trade_count", "total_buy_volume", "total_sell_volume", "latest_trade_date",
    ]

    def generate():
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        yield buf.getvalue()

        for row in rows:
            member = row[0]
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
            writer.writerow({
                "bioguide_id": member.bioguide_id,
                "name": member.name,
                "chamber": member.chamber,
                "state": member.state,
                "district": member.district,
                "party": member.party,
                "trade_count": row[1] or 0,
                "total_buy_volume": row[2] or 0,
                "total_sell_volume": row[3] or 0,
                "latest_trade_date": row[4].isoformat() if row[4] else "",
            })
            yield buf.getvalue()

    today = date_type.today().isoformat()
    filename = f"congress_members_{today}.csv"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(generate(), media_type="text/csv", headers=headers)


@router.get("/analytics/csv")
async def export_analytics_csv(
    db: AsyncSession = Depends(get_db),
):
    """Export aggregate analytics (top tickers + party comparison) as a CSV download."""
    # Top tickers
    ticker_stmt = (
        select(
            Trade.ticker,
            func.count(Trade.trade_id).label("trade_count"),
            func.sum(case((Trade.trade_type == "Purchase", 1), else_=0)).label("buy_count"),
            func.sum(
                case(
                    (Trade.trade_type.in_(["Sale", "Sale (Full)", "Sale (Partial)"]), 1),
                    else_=0,
                )
            ).label("sell_count"),
            func.count(func.distinct(Trade.member_id)).label("unique_members"),
            func.avg(EnrichedTrade.anomaly_score).label("avg_anomaly_score"),
        )
        .outerjoin(EnrichedTrade, Trade.trade_id == EnrichedTrade.trade_id)
        .where(Trade.ticker.isnot(None))
        .group_by(Trade.ticker)
        .order_by(func.count(Trade.trade_id).desc())
        .limit(50)
    )
    ticker_rows = (await db.execute(ticker_stmt)).all()

    # Party comparison
    party_stmt = (
        select(
            Member.party,
            func.count(Trade.trade_id).label("total_trades"),
            func.coalesce(
                func.sum(case((Trade.trade_type == "Purchase", Trade.amount_max), else_=0)), 0
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
            func.avg(EnrichedTrade.anomaly_score).label("avg_anomaly_score"),
            func.count(func.distinct(Trade.ticker)).label("unique_tickers"),
        )
        .join(Member, Trade.member_id == Member.bioguide_id)
        .outerjoin(EnrichedTrade, Trade.trade_id == EnrichedTrade.trade_id)
        .group_by(Member.party)
        .order_by(func.count(Trade.trade_id).desc())
    )
    party_rows = (await db.execute(party_stmt)).all()

    def generate():
        buf = io.StringIO()
        buf.write("=== TOP TICKERS ===\n")
        yield buf.getvalue()

        buf = io.StringIO()
        ticker_fields = [
            "ticker", "trade_count", "buy_count",
            "sell_count", "unique_members", "avg_anomaly_score",
        ]
        writer = csv.DictWriter(buf, fieldnames=ticker_fields)
        writer.writeheader()
        yield buf.getvalue()

        for r in ticker_rows:
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=ticker_fields)
            writer.writerow({
                "ticker": r.ticker,
                "trade_count": r.trade_count,
                "buy_count": r.buy_count,
                "sell_count": r.sell_count,
                "unique_members": r.unique_members,
                "avg_anomaly_score": round(r.avg_anomaly_score, 2) if r.avg_anomaly_score else "",
            })
            yield buf.getvalue()

        buf = io.StringIO()
        buf.write("\n=== PARTY COMPARISON ===\n")
        yield buf.getvalue()

        buf = io.StringIO()
        party_fields = [
            "party", "total_trades", "total_buy_volume",
            "total_sell_volume", "avg_anomaly_score", "unique_tickers",
        ]
        writer = csv.DictWriter(buf, fieldnames=party_fields)
        writer.writeheader()
        yield buf.getvalue()

        for r in party_rows:
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=party_fields)
            writer.writerow({
                "party": r.party,
                "total_trades": r.total_trades,
                "total_buy_volume": r.total_buy_volume,
                "total_sell_volume": r.total_sell_volume,
                "avg_anomaly_score": round(r.avg_anomaly_score, 2) if r.avg_anomaly_score else "",
                "unique_tickers": r.unique_tickers,
            })
            yield buf.getvalue()

    today = date_type.today().isoformat()
    filename = f"congress_analytics_{today}.csv"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(generate(), media_type="text/csv", headers=headers)
