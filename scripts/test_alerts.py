"""Test alert delivery for Congress Trades.

Sends a test Telegram message and/or a test email using the credentials
configured in .env (or the environment).  Use --dry-run to format the
message without actually sending anything.

Usage:
    uv run python scripts/test_alerts.py --telegram
    uv run python scripts/test_alerts.py --email
    uv run python scripts/test_alerts.py --telegram --email
    uv run python scripts/test_alerts.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import UTC, datetime

# Load .env before importing settings
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed; env vars must already be set

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Message formatting (standalone — no DB required)
# ---------------------------------------------------------------------------

_TEST_SUBJECT = "[Congress Trades] Alert System Test"

_TEST_TELEGRAM_MESSAGE = """\
*Congress Trades Alert System Test*

This is a test message from the Congress Trades pipeline.

If you received this, your Telegram alerts are configured correctly.

Sent at: {now}
"""

_TEST_HTML_BODY = """\
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
  p {{ color: #94a3b8; font-size: 14px; }}
  .footer {{ margin-top: 24px; font-size: 11px; color: #475569; text-align: center; }}
</style>
</head>
<body>
<div class="card">
  <h1>&#x2705; Congress Trades Alert System Test</h1>
  <p>This is a test email from the Congress Trades pipeline.</p>
  <p>If you received this, your email alerts are configured correctly.</p>
  <div class="footer">Sent at {now}</div>
</div>
</body>
</html>
"""


def _format_test_telegram() -> str:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    return _TEST_TELEGRAM_MESSAGE.format(now=now)


def _format_test_email() -> tuple[str, str]:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    return _TEST_SUBJECT, _TEST_HTML_BODY.format(now=now)


# ---------------------------------------------------------------------------
# Telegram test
# ---------------------------------------------------------------------------


async def _test_telegram(dry_run: bool) -> bool:
    """Send (or print) a test Telegram message.

    Returns True on success / dry-run, False on failure.
    """
    message = _format_test_telegram()

    if dry_run:
        print("\n--- DRY RUN: Telegram message ---")
        print(message)
        print("---------------------------------\n")
        return True

    try:
        from congress_trades.config import settings
    except ImportError as exc:
        print(
            f"ERROR: Could not import congress_trades.config: {exc}\n"
            "Make sure you run this script from the project root with `uv run`.",
            file=sys.stderr,
        )
        return False

    bot_token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID

    if not bot_token:
        print(
            "ERROR: TELEGRAM_BOT_TOKEN is not set.\n"
            "Run `uv run python scripts/setup_env.py` to configure it.",
            file=sys.stderr,
        )
        return False

    if not chat_id:
        print(
            "ERROR: TELEGRAM_CHAT_ID is not set.\n"
            "Run `uv run python scripts/setup_env.py` to configure it.",
            file=sys.stderr,
        )
        return False

    try:
        from telegram import Bot
        from telegram.constants import ParseMode
    except ImportError:
        print(
            "ERROR: python-telegram-bot is not installed.\n"
            "Run: uv add python-telegram-bot",
            file=sys.stderr,
        )
        return False

    print(f"Sending test Telegram message to chat_id={chat_id!r} ...")

    try:
        bot = Bot(token=bot_token)
        await bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode=ParseMode.MARKDOWN,
        )
        print("  Telegram test message sent successfully.")
        return True
    except Exception as exc:
        print(f"  ERROR sending Telegram message: {exc}", file=sys.stderr)
        logger.exception("Telegram test failed")
        return False


# ---------------------------------------------------------------------------
# Email test
# ---------------------------------------------------------------------------


async def _test_email(dry_run: bool) -> bool:
    """Send (or print) a test email alert.

    Returns True on success / dry-run, False on failure.
    """
    subject, html_body = _format_test_email()

    if dry_run:
        print("\n--- DRY RUN: Email ---")
        print(f"Subject : {subject}")
        print(f"Body    : {html_body[:300]}...")
        print("----------------------\n")
        return True

    try:
        from congress_trades.config import settings
    except ImportError as exc:
        print(
            f"ERROR: Could not import congress_trades.config: {exc}\n"
            "Make sure you run this script from the project root with `uv run`.",
            file=sys.stderr,
        )
        return False

    if not settings.SMTP_HOST:
        print(
            "ERROR: SMTP_HOST is not set.\n"
            "Run `uv run python scripts/setup_env.py` to configure email alerts.",
            file=sys.stderr,
        )
        return False

    if not settings.ALERT_EMAIL_TO:
        print(
            "ERROR: ALERT_EMAIL_TO is not set.\n"
            "Run `uv run python scripts/setup_env.py` to configure email alerts.",
            file=sys.stderr,
        )
        return False

    try:
        from congress_trades.alerts.email_alerts import send_email_alert
    except ImportError as exc:
        print(f"ERROR: Could not import email_alerts: {exc}", file=sys.stderr)
        return False

    recipients = settings.ALERT_EMAIL_TO
    print(f"Sending test email to {recipients!r} via {settings.SMTP_HOST}:{settings.SMTP_PORT} ...")

    try:
        sent = await send_email_alert(subject, html_body)
        if sent:
            print("  Email test message sent successfully.")
        else:
            print("  send_email_alert returned False — check logs for details.", file=sys.stderr)
        return sent
    except Exception as exc:
        print(f"  ERROR sending email: {exc}", file=sys.stderr)
        logger.exception("Email test failed")
        return False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def _main(args: argparse.Namespace) -> int:
    """Run selected tests; return exit code (0 = all passed)."""
    if not args.telegram and not args.email and not args.dry_run:
        print(
            "No test selected. Use --telegram, --email, or --dry-run.\n"
            "Run with --help for usage.",
            file=sys.stderr,
        )
        return 1

    if args.dry_run and not args.telegram and not args.email:
        # Default dry-run shows both
        args.telegram = True
        args.email = True

    results: list[bool] = []

    if args.telegram:
        ok = await _test_telegram(dry_run=args.dry_run)
        results.append(ok)

    if args.email:
        ok = await _test_email(dry_run=args.dry_run)
        results.append(ok)

    all_ok = all(results)
    if not all_ok:
        print("\nOne or more tests failed. Check the errors above.", file=sys.stderr)
    else:
        if not args.dry_run:
            print("\nAll alert tests passed.")
    return 0 if all_ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test Telegram and/or email alert delivery for Congress Trades.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  uv run python scripts/test_alerts.py --telegram\n"
            "  uv run python scripts/test_alerts.py --email\n"
            "  uv run python scripts/test_alerts.py --telegram --email\n"
            "  uv run python scripts/test_alerts.py --dry-run\n"
            "  uv run python scripts/test_alerts.py --telegram --dry-run\n"
        ),
    )
    parser.add_argument(
        "--telegram",
        action="store_true",
        help="Send a test Telegram message using TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID.",
    )
    parser.add_argument(
        "--email",
        action="store_true",
        help="Send a test email using the configured SMTP settings.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Format the alert message(s) and print them without sending.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable DEBUG logging.",
    )

    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")

    sys.exit(asyncio.run(_main(args)))


if __name__ == "__main__":
    main()
