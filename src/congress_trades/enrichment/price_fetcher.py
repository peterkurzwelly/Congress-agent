"""Fetch historical and current price data using yfinance."""

import asyncio
import logging
from datetime import date, timedelta
from functools import lru_cache
from typing import Optional

import yfinance as yf

logger = logging.getLogger(__name__)

# Module-level cache: (ticker, trade_date) -> price dict
_price_cache: dict[tuple[str, date], dict] = {}


def _fetch_prices_sync(ticker: str, trade_date: date) -> dict:
    """Synchronous yfinance fetch -- run in a thread executor.

    Returns dict with keys:
        price_at_trade, price_current, return_1d, return_7d, return_30d, return_90d
    """
    result: dict = {
        "price_at_trade": None,
        "price_current": None,
        "return_1d": None,
        "return_7d": None,
        "return_30d": None,
        "return_90d": None,
        "sector": None,
        "industry": None,
    }

    try:
        stock = yf.Ticker(ticker)

        # Get sector/industry info from the stock info
        try:
            info = stock.info or {}
            result["sector"] = info.get("sector")
            result["industry"] = info.get("industry")
        except Exception:
            pass

        # Determine date range: from a few days before trade to 90 days after
        # (or today, whichever is earlier)
        start = trade_date - timedelta(days=5)
        today = date.today()
        end = min(trade_date + timedelta(days=95), today)

        hist = stock.history(start=str(start), end=str(end))
        if hist.empty:
            logger.debug("No price history for %s around %s", ticker, trade_date)
            return result

        # Find price at trade date (or nearest available trading day)
        trade_dt_str = str(trade_date)
        if trade_dt_str in hist.index.strftime("%Y-%m-%d").tolist():
            result["price_at_trade"] = float(
                hist.loc[hist.index.strftime("%Y-%m-%d") == trade_dt_str, "Close"].iloc[0]
            )
        else:
            # Use the nearest trading day before or on trade_date
            before_trade = hist[hist.index.date <= trade_date]
            if not before_trade.empty:
                result["price_at_trade"] = float(before_trade["Close"].iloc[-1])

        if result["price_at_trade"] is None:
            return result

        trade_price = result["price_at_trade"]

        # Helper to get price N days after trade date
        def _price_at_offset(days: int) -> Optional[float]:
            target = trade_date + timedelta(days=days)
            if target > today:
                return None
            after_target = hist[hist.index.date >= target]
            if not after_target.empty:
                return float(after_target["Close"].iloc[0])
            return None

        # Calculate returns
        for label, days in [
            ("return_1d", 1),
            ("return_7d", 7),
            ("return_30d", 30),
            ("return_90d", 90),
        ]:
            future_price = _price_at_offset(days)
            if future_price is not None:
                result[label] = round(
                    (future_price - trade_price) / trade_price * 100, 2
                )

        # Current price: use the last available close
        # Fetch separately in case the hist window doesn't cover today
        try:
            current_hist = stock.history(period="1d")
            if not current_hist.empty:
                result["price_current"] = float(current_hist["Close"].iloc[-1])
        except Exception:
            # Use last price from our history window
            result["price_current"] = float(hist["Close"].iloc[-1])

    except Exception as exc:
        logger.warning("yfinance fetch failed for %s: %s", ticker, exc)

    return result


async def fetch_trade_returns(ticker: str, trade_date: date) -> dict:
    """Fetch price data for a ticker at a given trade date.

    Runs yfinance in a thread executor since it is synchronous.
    Results are cached by (ticker, trade_date).

    Returns dict:
        price_at_trade, price_current, return_1d, return_7d,
        return_30d, return_90d, sector, industry
    """
    cache_key = (ticker.upper(), trade_date)
    if cache_key in _price_cache:
        return _price_cache[cache_key]

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, _fetch_prices_sync, ticker.upper(), trade_date
    )

    _price_cache[cache_key] = result
    return result
