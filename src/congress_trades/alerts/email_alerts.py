"""Email alert system for Congress trade notifications.

Sends HTML email alerts via stdlib smtplib (no extra deps) using
asyncio's thread executor so the blocking SMTP call doesn't block the
event loop.  Formatting mirrors the Telegram alert style but rendered
as a responsive HTML table.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
from datetime import UTC, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from congress_trades.config import settings
from congress_trades.db.models import Alert, EnrichedTrade, Filing, Member, Trade

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. HTML formatting
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: Arial, sans-serif; background: #0f172a;
          color: #e2e8f0; margin: 0; padding: 24px; }}
  .card {{ background: #1e293b; border-radius: 8px; max-width: 600px;
           margin: 0 auto; padding: 24px; }}
  h1 {{ font-size: 20px; margin: 0 0 16px; color: #f8fafc; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 16px; }}
  td {{ padding: 6px 0; vertical-align: top; }}
  td.label {{ color: #94a3b8; width: 40%; font-size: 13px; }}
  td.value {{ color: #e2e8f0; font-size: 13px; font-weight: 600; }}
  .badge {{ display: inline-block; background: #334155; border-radius: 4px;
            padding: 2px 8px; font-size: 12px; margin: 2px; }}
  .badge-buy {{ background: #166534; color: #bbf7d0; }}
  .badge-sell {{ background: #7f1d1d; color: #fecaca; }}
  .score-bar {{ background: #334155; border-radius: 4px; height: 8px; overflow: hidden; }}
  .score-fill {{ background: #f59e0b; height: 8px; border-radius: 4px; }}
  .flag {{ color: #fbbf24; font-size: 12px; margin: 2px 0; }}
  .footer {{ margin-top: 24px; font-size: 11px; color: #475569; text-align: center; }}
</style>
</head>
<body>
<div class="card">
  <h1>{header} Congress Trade Alert</h1>
  <table>
    <tr>
      <td class="label">Member</td>
      <td class="value">{member_name} ({party}-{state})</td>
    </tr>
    <tr>
      <td class="label">Ticker</td>
      <td class="value">{ticker}</td>
    </tr>
    <tr>
      <td class="label">Asset</td>
      <td class="value">{asset_description}</td>
    </tr>
    <tr>
      <td class="label">Action</td>
      <td class="value"><span class="badge {direction_class}">{direction}</span></td>
    </tr>
    <tr>
      <td class="label">Amount</td>
      <td class="value">{amount_range}</td>
    </tr>
    <tr>
      <td class="label">Trade Date</td>
      <td class="value">{trade_date}</td>
    </tr>
    {filing_rows}
    {enrichment_rows}
  </table>
  {flags_block}
  {returns_block}
  <div class="footer">Congress Trades Monitor &mdash; {now}</div>
</div>
</body>
</html>
"""


def _direction_info(trade_type: str) -> tuple[str, str, str]:
    """Return (header_emoji, direction_label, css_class)."""
    lower = trade_type.lower()
    if "purchase" in lower:
        return "\U0001f7e2", "PURCHASED", "badge-buy"
    if "sale" in lower:
        return "\U0001f534", "SOLD", "badge-sell"
    return "\U0001f535", trade_type.upper(), "badge"


def _score_html(score: float) -> str:
    pct = min(max(score, 0), 100)
    return (
        f'<div class="score-bar"><div class="score-fill" style="width:{pct:.0f}%"></div></div>'
        f"&nbsp;{pct:.0f}/100"
    )


def _return_row(value: float | None, label: str) -> str:
    if value is None:
        return ""
    sign = "+" if value >= 0 else ""
    color = "#4ade80" if value >= 0 else "#f87171"
    return (
        f'<tr><td class="label">{label} return</td>'
        f'<td class="value" style="color:{color}">{sign}{value:.2f}%</td></tr>'
    )


def format_trade_email(
    trade: Trade,
    member: Member,
    enrichment: EnrichedTrade | None,
    filing: Filing | None = None,
) -> tuple[str, str]:
    """Build (subject, html_body) for a trade alert email.

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

    Returns
    -------
    tuple[str, str]
        A ``(subject, html_body)`` pair ready to pass to
        :func:`send_email_alert`.
    """
    header_emoji, direction, direction_class = _direction_info(trade.trade_type)
    ticker = trade.ticker or "N/A"

    subject = (
        f"[Congress Trade] {member.name} {direction} {ticker} "
        f"({trade.amount_range})"
    )

    # Filing rows (optional)
    filing_rows = ""
    if filing:
        filing_rows = (
            f'<tr><td class="label">Filing Date</td>'
            f'<td class="value">{filing.filing_date}</td></tr>'
            f'<tr><td class="label">Disclosure Date</td>'
            f'<td class="value">{filing.disclosure_date}</td></tr>'
        )

    # Enrichment rows
    enrichment_rows = ""
    flags_block = ""
    returns_block = ""

    if enrichment:
        if enrichment.anomaly_score is not None:
            enrichment_rows += (
                f'<tr><td class="label">Anomaly Score</td>'
                f'<td class="value">{_score_html(enrichment.anomaly_score)}</td></tr>'
            )
        if enrichment.sector:
            enrichment_rows += (
                f'<tr><td class="label">Sector</td>'
                f'<td class="value">{enrichment.sector}</td></tr>'
            )
        if enrichment.industry:
            enrichment_rows += (
                f'<tr><td class="label">Industry</td>'
                f'<td class="value">{enrichment.industry}</td></tr>'
            )

        # Flags
        raw_flags = enrichment.flags if isinstance(enrichment.flags, list) else []
        if raw_flags:
            flag_items = "".join(
                f'<div class="flag">&#9888; {flag}</div>' for flag in raw_flags
            )
            flags_block = f"<div>{flag_items}</div>"

        # Returns table
        rows = (
            _return_row(enrichment.return_1d, "1-day")
            + _return_row(enrichment.return_7d, "7-day")
            + _return_row(enrichment.return_30d, "30-day")
            + _return_row(enrichment.return_90d, "90-day")
        )
        if rows:
            returns_block = (
                "<table><tr><td colspan='2' style='padding-bottom:4px;"
                "color:#94a3b8;font-size:13px'>Post-trade returns</td></tr>"
                f"{rows}</table>"
            )

    html_body = _HTML_TEMPLATE.format(
        header=header_emoji,
        member_name=member.name,
        party=member.party,
        state=member.state,
        ticker=ticker,
        asset_description=trade.asset_description[:120],
        direction=direction,
        direction_class=direction_class,
        amount_range=trade.amount_range,
        trade_date=trade.trade_date,
        filing_rows=filing_rows,
        enrichment_rows=enrichment_rows,
        flags_block=flags_block,
        returns_block=returns_block,
        now=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
    )

    return subject, html_body


# ---------------------------------------------------------------------------
# 2. Send a single email (blocking, called in executor)
# ---------------------------------------------------------------------------


def _send_email_sync(subject: str, html_body: str) -> None:
    """Blocking SMTP send — runs in a thread executor."""
    recipients = [r.strip() for r in settings.ALERT_EMAIL_TO.split(",") if r.strip()]
    if not recipients:
        raise ValueError("ALERT_EMAIL_TO is empty; cannot send email alert")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.ALERT_EMAIL_FROM
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        smtp.sendmail(settings.ALERT_EMAIL_FROM, recipients, msg.as_string())


async def send_email_alert(subject: str, html_body: str) -> bool:
    """Send an HTML email alert.

    Runs the blocking SMTP call in a thread executor so the async event
    loop is not blocked.

    Parameters
    ----------
    subject:
        Email subject line.
    html_body:
        Full HTML body of the email.

    Returns
    -------
    bool
        ``True`` on success, ``False`` on failure.
    """
    if not settings.SMTP_HOST:
        logger.warning("SMTP_HOST not configured; skipping email alert")
        return False

    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, _send_email_sync, subject, html_body)
        logger.info("Email alert sent: %s", subject)
        return True
    except Exception:
        logger.exception("Failed to send email alert: %s", subject)
        return False


# ---------------------------------------------------------------------------
# 3. Batch-process unalerted trades
# ---------------------------------------------------------------------------


async def process_email_alerts(session: AsyncSession) -> None:
    """Find enriched trades without email alerts, evaluate thresholds, and send.

    For each enriched trade that has not yet triggered an email alert,
    this function checks the same thresholds used by the Telegram alert
    system (:func:`~congress_trades.alerts.telegram.should_alert`) and
    sends an HTML email when any threshold is met.  A corresponding
    :class:`~congress_trades.db.models.Alert` row with
    ``channel="email"`` is persisted so the trade is not re-alerted on
    the next run.

    Parameters
    ----------
    session:
        An active async DB session.
    """
    from congress_trades.alerts.telegram import should_alert

    # Find enriched trades that don't yet have an email alert
    email_alerted_subq = (
        select(Alert.trade_id).where(Alert.channel == "email").scalar_subquery()
    )
    stmt = (
        select(Trade)
        .join(EnrichedTrade, Trade.trade_id == EnrichedTrade.trade_id)
        .options(
            selectinload(Trade.member),
            selectinload(Trade.filing),
            selectinload(Trade.enrichment),
        )
        .where(Trade.trade_id.not_in(email_alerted_subq))
    )
    result = await session.execute(stmt)
    trades = result.scalars().all()

    logger.info("process_email_alerts: evaluating %d unenriched trades", len(trades))

    now = datetime.now(UTC)
    for trade in trades:
        member = trade.member
        enrichment = trade.enrichment
        filing = trade.filing

        alert_types = should_alert(trade, enrichment, filing)
        if not alert_types:
            continue

        subject, html_body = format_trade_email(trade, member, enrichment, filing)

        # Append alert-type tags to the subject
        type_tags = " ".join(f"[{at.value}]" for at in alert_types)
        subject = f"{type_tags} {subject}"

        sent = await send_email_alert(subject, html_body)
        if not sent:
            continue

        for at in alert_types:
            session.add(
                Alert(
                    trade_id=trade.trade_id,
                    alert_type=at.value,
                    channel="email",
                    message=subject,
                    sent_at=now,
                )
            )

    await session.commit()
