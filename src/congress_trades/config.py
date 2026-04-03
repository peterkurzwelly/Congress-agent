"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All configuration is loaded from environment variables or a .env file."""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./congress_trades.db"

    # Anthropic API (for PDF parsing and anomaly analysis)
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"

    # Telegram Bot (for alerts)
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # Congress.gov API
    CONGRESS_API_KEY: str = ""

    # Scheduler
    ENABLE_SCHEDULER: bool = False

    # Scraping schedule
    SCRAPE_INTERVAL_HOURS: int = 6
    SENATE_SCRAPE_INTERVAL_HOURS: int = 4
    REQUEST_DELAY_SECONDS: float = 1.0

    # Anomaly thresholds
    ANOMALY_ALERT_THRESHOLD: int = 50
    LARGE_TRADE_THRESHOLD: int = 100_000

    # STOCK Act
    STOCK_ACT_DISCLOSURE_DAYS: int = 45


settings = Settings()
