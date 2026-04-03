"""Alert subsystem for Congress trade notifications (Telegram + Email)."""

from congress_trades.alerts.email_alerts import (
    format_trade_email,
    process_email_alerts,
    send_email_alert,
)
from congress_trades.alerts.telegram import (
    WATCHED_POLITICIANS,
    format_trade_message,
    process_new_filings,
    send_alert,
    should_alert,
)

__all__ = [
    # Telegram
    "WATCHED_POLITICIANS",
    "format_trade_message",
    "process_new_filings",
    "send_alert",
    "should_alert",
    # Email
    "format_trade_email",
    "process_email_alerts",
    "send_email_alert",
]
