"""Telegram alert system for Congress trade notifications.

Formats trade data into rich Markdown messages, determines which alerts
to trigger based on configurable thresholds, sends via python-telegram-bot,
and records every sent alert in the database.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from telegram import Bot
from telegram.constants import ParseMode

from congress_trades.api.schemas import AlertType
from congress_trades.config import settings
from congress_trades.db.models import Alert, EnrichedTrade, Filing, Member, Trade

logger = logging.getLogger(__name__)

# Politicians whose *every* new filing triggers an alert.
# Extend this list (or move it to config / DB) as needed.
WATCHED_POLITICIANS: set[str] = {
    "P000197",  # Nancy Pelosi
    "T000476",  # Tommy Tuberville
    "H001089",  # Dan Crenshaw
}


# ---------------------------------------------------------------------------
# 1. Message formatting
# ---------------------------------------------------------------------------


def _trade_type_emoji(trade_type: str) -> str:
    """Return an emoji reflecting the trade direction."""
    lower = trade_type.lower()
    if "purchase" in lower:
        return "\U0001f7e2"  # green circle
    if "sale" in lower:
        return "\U0001f534"  # red circle
    return "\U0001f535"  # blue circle (exchange / other)


def _anomaly_bar(score: float, width: int = 10) -> str:
    """Build a visual bar like [########--] 80/100."""
    filled = round(score / 100 * width)
    empty = width - filled
    return f"[{'#' * filled}{'-' * empty}] {score:.0f}/100"


def _format_return(value: float | None, label: str) -> str:
    if value is None:
        return ""
    sign = "+" if value >= 0 else ""
    return f"  {label}: {sign}{value:.2f}%\n"


def _escape_md(text: str) -> str:
    """Escape characters that have special meaning in Telegram Markdown v1."""
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text


def format_trade_message(
    trade: Trade,
    member: Member,
    enrichment: EnrichedTrade | None,
    filing: Filing | None = None,
) -> str:
    """Build a Markdown-formatted Telegram message for a single trade.

    Parameters
    ----------
    trade:
        The Trade ORM object.
    member:
        The associated Member ORM object.
    enrichment:
        Optional EnrichedTrade with anomaly / return data.
    filing:
        Optional Filing for date context.
    """
    emoji = _trade_type_emoji(trade.trade_type)
    ticker_display = trade.ticker or "N/A"
    direction = "PURCHASED" if "purchase" in trade.trade_type.lower() else "SOLD"

    lines: list[str] = []

    # Header
    lines.append(f"{emoji} *Congress Trade Alert*")
    lines.append("")

    # Politician
    lines.append(
        f"*{_escape_md(member.name)}* ({member.party}-{member.state})"
    )
    lines.append("")

    # Asset info
    lines.append(f"Ticker: `{ticker_display}`")
    lines.append(f"Asset: {_escape_md(trade.asset_description[:80])}")
    lines.append(f"Action: *{direction}*")
    lines.append(f"Amount: {trade.amount_range}")
    lines.append("")

    # Dates
    lines.append(f"Trade date: {trade.trade_date}")
    if filing:
        lines.append(f"Filing date: {filing.filing_date}")
        lines.append(f"Disclosure date: {filing.disclosure_date}")
    lines.append("")

    # Enrichment section
    if enrichment:
        score = enrichment.anomaly_score
        if score is not None:
            lines.append(f"Anomaly score: {_anomaly_bar(score)}")
            lines.append("")

        # Flags / concerns
        flags = enrichment.flags if isinstance(enrichment.flags, list) else []
        if flags:
            lines.append("Flags:")
            for flag in flags:
                lines.append(f"  - {_escape_md(str(flag))}")
            lines.append("")

        # Post-trade returns
        returns_block = ""
        returns_block += _format_return(enrichment.return_1d, "1-day")
        returns_block += _format_return(enrichment.return_7d, "7-day")
        returns_block += _format_return(enrichment.return_30d, "30-day")
        returns_block += _format_return(enrichment.return_90d, "90-day")
        if returns_block:
            lines.append("Post-trade return:")
            lines.append(returns_block.rstrip())
            lines.append("")

        if enrichment.sector:
            lines.append(f"Sector: {_escape_md(enrichment.sector)}")
        if enrichment.industry:
            lines.append(f"Industry: {_escape_md(enrichment.industry)}")

    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# 2. Alert-trigger logic
# ---------------------------------------------------------------------------


def should_alert(
    trade: Trade,
    enrichment: EnrichedTrade | None,
    filing: Filing | None,
) -> list[AlertType]:
    """Determine which alert types a trade triggers.

    Parameters
    ----------
    trade:
        The Trade ORM object.
    enrichment:
        Optional enrichment row (may be None if analyst hasn't run yet).
    filing:
        The Filing associated with the trade (needed for late-filing check).

    Returns
    -------
    list[AlertType]
        Possibly-empty list of triggered alert types.
    """
    alerts: list[AlertType] = []

    # HIGH_ANOMALY
    if enrichment and enrichment.anomaly_score is not None:
        if enrichment.anomaly_score > settings.ANOMALY_ALERT_THRESHOLD:
            alerts.append(AlertType.HIGH_ANOMALY)

    # LARGE_TRADE
    if trade.amount_max > settings.LARGE_TRADE_THRESHOLD:
        alerts.append(AlertType.LARGE_TRADE)

    # LATE_FILING (disclosure_date > trade_date + 45 days)
    if filing is not None:
        deadline = trade.trade_date + timedelta(days=settings.STOCK_ACT_DISCLOSURE_DAYS)
        if filing.disclosure_date > deadline:
            alerts.append(AlertType.LATE_FILING)

    # NEW_FILING — always for watched politicians
    if trade.member_id in WATCHED_POLITICIANS:
        alerts.append(AlertType.NEW_FILING)

    return alerts


# ---------------------------------------------------------------------------
# 3. Send a single alert
# ---------------------------------------------------------------------------


async def send_alert(
    trade_id: int,
    alert_types: list[AlertType],
    session: AsyncSession,
) -> None:
    """Fetch trade data, format a message, send it via Telegram, and persist.

    Parameters
    ----------
    trade_id:
        Primary key of the trade to alert on.
    alert_types:
        Which alert categories this message covers.
    session:
        An active async DB session.
    """
    # Fetch trade with related member, filing, and enrichment
    stmt = (
        select(Trade)
        .options(
            selectinload(Trade.member),
            selectinload(Trade.filing),
            selectinload(Trade.enrichment),
        )
        .where(Trade.trade_id == trade_id)
    )
    result = await session.execute(stmt)
    trade = result.scalar_one_or_none()

    if trade is None:
        logger.error("send_alert: trade_id=%s not found", trade_id)
        return

    member = trade.member
    enrichment = trade.enrichment
    filing = trade.filing

    message = format_trade_message(trade, member, enrichment, filing)

    # Append alert-type tags at the bottom
    type_tags = " ".join(f"#{at.value}" for at in alert_types)
    message = f"{message}\n\n{type_tags}"

    # Send via Telegram
    bot_token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID

    if not bot_token or not chat_id:
        logger.warning(
            "Telegram credentials not configured; skipping send for trade %s",
            trade_id,
        )
        return

    bot = Bot(token=bot_token)
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode=ParseMode.MARKDOWN,
        )
        logger.info("Telegram alert sent for trade %s", trade_id)
    except Exception:
        logger.exception("Failed to send Telegram alert for trade %s", trade_id)
        raise

    # Record each alert type in the DB
    now = datetime.now(timezone.utc)
    for at in alert_types:
        alert = Alert(
            trade_id=trade_id,
            alert_type=at.value,
            channel="telegram",
            message=message,
            sent_at=now,
        )
        session.add(alert)

    await session.commit()


# ---------------------------------------------------------------------------
# 4. Batch-process new filings
# ---------------------------------------------------------------------------


async def process_new_filings(
    filing_ids: Sequence[str],
    session: AsyncSession,
) -> None:
    """For each filing, evaluate every trade and send alerts as warranted.

    Parameters
    ----------
    filing_ids:
        The filing primary keys to process.
    session:
        An active async DB session.
    """
    for filing_id in filing_ids:
        stmt = (
            select(Filing)
            .options(
                selectinload(Filing.trades).selectinload(Trade.enrichment),
            )
            .where(Filing.filing_id == filing_id)
        )
        result = await session.execute(stmt)
        filing = result.scalar_one_or_none()

        if filing is None:
            logger.warning("process_new_filings: filing %s not found", filing_id)
            continue

        for trade in filing.trades:
            enrichment = trade.enrichment
            alert_types = should_alert(trade, enrichment, filing)

            if not alert_types:
                continue

            try:
                await send_alert(trade.trade_id, alert_types, session)
            except Exception:
                logger.exception(
                    "Failed to process alert for trade %s in filing %s",
                    trade.trade_id,
                    filing_id,
                )
