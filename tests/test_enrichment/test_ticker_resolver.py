"""Tests for the ticker resolver module."""

import pytest

from congress_trades.enrichment.ticker_resolver import _resolve_cache, resolve_ticker


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    """Clear the module-level resolution cache before each test."""
    _resolve_cache.clear()


async def test_common_tickers_lookup() -> None:
    """'Apple Inc' resolves to AAPL via local dictionary."""
    result = await resolve_ticker("Apple Inc")
    assert result == "AAPL"


async def test_common_tickers_lookup_nvidia() -> None:
    """'NVIDIA Corporation' resolves to NVDA via local dictionary."""
    result = await resolve_ticker("NVIDIA Corporation")
    assert result == "NVDA"


async def test_known_ticker_passthrough() -> None:
    """If known_ticker is provided, return it immediately without lookup."""
    result = await resolve_ticker("Some Random Description", known_ticker="MSFT")
    assert result == "MSFT"


async def test_known_ticker_passthrough_strips_whitespace() -> None:
    """known_ticker is uppercased and stripped."""
    result = await resolve_ticker("whatever", known_ticker="  aapl  ")
    assert result == "AAPL"


async def test_direct_ticker_string() -> None:
    """A bare ticker symbol like 'AAPL' resolves directly."""
    result = await resolve_ticker("AAPL")
    assert result == "AAPL"


async def test_ticker_in_parens() -> None:
    """Description containing '(GOOGL)' resolves via parenthetical match."""
    result = await resolve_ticker("Alphabet Inc (GOOGL)")
    assert result == "GOOGL"
