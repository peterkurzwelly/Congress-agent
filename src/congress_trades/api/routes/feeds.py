"""RSS feed endpoints."""

from datetime import UTC, datetime
from email.utils import format_datetime
from xml.etree.ElementTree import Element, SubElement, tostring

from fastapi import Depends
from fastapi.responses import Response
from fastapi.routing import APIRouter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from congress_trades.config import settings
from congress_trades.db.models import EnrichedTrade, Trade
from congress_trades.db.session import get_db

router = APIRouter()

_RSS_CONTENT_TYPE = "application/rss+xml; charset=utf-8"


def _build_rss_feed(trades: list[Trade], title: str, description: str) -> bytes:
    """Build an RSS 2.0 XML document from a list of Trade ORM objects."""
    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")

    SubElement(channel, "title").text = title
    SubElement(channel, "link").text = "https://congress-trades.example.com"
    SubElement(channel, "description").text = description
    SubElement(channel, "language").text = "en-us"
    SubElement(channel, "lastBuildDate").text = format_datetime(
        datetime.now(tz=UTC), usegmt=True
    )

    for trade in trades:
        member = trade.member
        enrichment = trade.enrichment

        member_name = member.name if member else "Unknown"
        ticker = trade.ticker or trade.asset_description or "N/A"
        trade_type = trade.trade_type or "Unknown"
        amount_range = trade.amount_range or "Unknown"
        trade_date = trade.trade_date.isoformat() if trade.trade_date else "Unknown"
        if enrichment and enrichment.anomaly_score is not None:
            anomaly_score = f"{enrichment.anomaly_score:.1f}"
        else:
            anomaly_score = "N/A"

        item_title = f"{member_name} – {trade_type} {ticker} ({trade_date})"
        item_description = (
            f"Politician: {member_name} | "
            f"Ticker: {ticker} | "
            f"Type: {trade_type} | "
            f"Amount: {amount_range} | "
            f"Date: {trade_date} | "
            f"Anomaly Score: {anomaly_score}"
        )
        item_link = f"https://congress-trades.example.com/api/trades/{trade.trade_id}"

        # Use trade_date for pubDate if available, otherwise fall back to now
        if trade.trade_date:
            pub_dt = datetime(
                trade.trade_date.year,
                trade.trade_date.month,
                trade.trade_date.day,
                tzinfo=UTC,
            )
            pub_date = format_datetime(pub_dt, usegmt=True)
        else:
            pub_date = format_datetime(datetime.now(tz=UTC), usegmt=True)

        item = SubElement(channel, "item")
        SubElement(item, "title").text = item_title
        SubElement(item, "description").text = item_description
        SubElement(item, "link").text = item_link
        SubElement(item, "guid", isPermaLink="false").text = str(trade.trade_id)
        SubElement(item, "pubDate").text = pub_date

    xml_declaration = b'<?xml version="1.0" encoding="UTF-8"?>\n'
    return xml_declaration + tostring(rss, encoding="unicode").encode("utf-8")


@router.get("/rss", summary="RSS feed of latest 50 trades")
async def rss_feed(db: AsyncSession = Depends(get_db)) -> Response:
    """Return an RSS 2.0 feed containing the latest 50 congressional trades."""
    stmt = (
        select(Trade)
        .options(
            selectinload(Trade.member),
            selectinload(Trade.enrichment),
        )
        .order_by(Trade.trade_date.desc())
        .limit(50)
    )
    result = await db.execute(stmt)
    trades = result.scalars().unique().all()

    xml_bytes = _build_rss_feed(
        list(trades),
        title="Congress Trades – Latest Trades",
        description="The 50 most recent US congressional stock trades.",
    )
    return Response(content=xml_bytes, media_type=_RSS_CONTENT_TYPE)


@router.get("/rss/anomalies", summary="RSS feed of high-anomaly trades")
async def rss_anomalies_feed(db: AsyncSession = Depends(get_db)) -> Response:
    """Return an RSS 2.0 feed of high-anomaly trades (score above ANOMALY_ALERT_THRESHOLD)."""
    threshold: float = settings.ANOMALY_ALERT_THRESHOLD

    stmt = (
        select(Trade)
        .join(EnrichedTrade, Trade.trade_id == EnrichedTrade.trade_id)
        .where(EnrichedTrade.anomaly_score >= threshold)
        .options(
            selectinload(Trade.member),
            selectinload(Trade.enrichment),
        )
        .order_by(EnrichedTrade.anomaly_score.desc())
        .limit(50)
    )
    result = await db.execute(stmt)
    trades = result.scalars().unique().all()

    xml_bytes = _build_rss_feed(
        list(trades),
        title="Congress Trades – High-Anomaly Trades",
        description=f"Congressional trades with an anomaly score above {threshold:.0f}.",
    )
    return Response(content=xml_bytes, media_type=_RSS_CONTENT_TYPE)
