"""Tests for the PDF parser module."""

from congress_trades.scrapers.pdf_parser import (
    _extract_ticker,
    _normalize_owner,
    _parse_amount,
)


class TestParseAmountRange:
    """Tests for _parse_amount (called _parse_amount internally)."""

    def test_standard_range_1k_15k(self) -> None:
        display, low, high = _parse_amount("$1,001 - $15,000")
        assert display == "$1,001 - $15,000"
        assert low == 1_001
        assert high == 15_000

    def test_standard_range_15k_50k(self) -> None:
        display, low, high = _parse_amount("$15,001 - $50,000")
        assert low == 15_001
        assert high == 50_000

    def test_standard_range_1m_5m(self) -> None:
        display, low, high = _parse_amount("$1,000,001 - $5,000,000")
        assert low == 1_000_001
        assert high == 5_000_000

    def test_over_50m(self) -> None:
        display, low, high = _parse_amount("Over $50,000,000")
        assert low == 50_000_001
        assert high == 100_000_000

    def test_generic_range_with_dash(self) -> None:
        """A non-standard range still parses via regex."""
        display, low, high = _parse_amount("$500 - $1,000")
        assert low == 500
        assert high == 1_000


class TestNormalizeOwner:
    """Tests for _normalize_owner."""

    def test_sp_to_spouse(self) -> None:
        assert _normalize_owner("SP") == "Spouse"

    def test_jt_to_joint(self) -> None:
        assert _normalize_owner("JT") == "Joint"

    def test_dc_to_dependent_child(self) -> None:
        assert _normalize_owner("DC") == "Dependent Child"

    def test_self_passthrough(self) -> None:
        assert _normalize_owner("Self") == "Self"

    def test_empty_defaults_to_self(self) -> None:
        assert _normalize_owner("") == "Self"

    def test_unknown_passthrough(self) -> None:
        assert _normalize_owner("Other Person") == "Other Person"


class TestExtractTicker:
    """Tests for _extract_ticker."""

    def test_ticker_in_parens(self) -> None:
        assert _extract_ticker("NVIDIA Corporation (NVDA)") == "NVDA"

    def test_ticker_with_bracket(self) -> None:
        assert _extract_ticker("Apple Inc (AAPL) [ST]") == "AAPL"

    def test_no_ticker(self) -> None:
        assert _extract_ticker("US Treasury Bond") is None

    def test_lowercase_not_matched(self) -> None:
        """Only uppercase tickers in parentheses are extracted."""
        assert _extract_ticker("Some asset (abc)") is None

    def test_long_ticker(self) -> None:
        """Tickers up to 5 chars are valid."""
        assert _extract_ticker("Broadcom (AVGO)") == "AVGO"
